"""
project_mapper/db/file_manifest.py
File-to-entity reverse index for AethvionDB.

Tracks which files have been scanned and which entities were derived from each.
The stored hash of each file enables the incremental-update pipeline to skip
unchanged files on subsequent scans.

Storage: per-database sidecar  AethvionDB.FILEMANIFEST
Format : JSON { version, files: { rel_path: FileEntry } }

Thread-safe via a per-instance lock (same pattern as NameIndex).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .utils import get_logger

logger = get_logger(__name__)

SIDECAR = "AethvionDB.FILEMANIFEST"


# ---------------------------------------------------------------------------
# Language detection — lightweight, no external deps
# ---------------------------------------------------------------------------

_LANGUAGE_BY_EXT: dict[str, str] = {
    ".py":    "python",
    ".js":    "javascript",  ".mjs": "javascript",
    ".ts":    "typescript",
    ".jsx":   "javascript",  ".tsx": "typescript",
    ".java":  "java",
    ".cpp":   "cpp",   ".cc": "cpp",   ".cxx": "cpp",
    ".c":     "c",     ".h":  "c",     ".hpp": "cpp",
    ".rb":    "ruby",
    ".go":    "go",
    ".rs":    "rust",
    ".php":   "php",
    ".cs":    "csharp",
    ".swift": "swift",
    ".kt":    "kotlin",   ".kts": "kotlin",
    ".sh":    "shell",    ".bash": "shell",  ".zsh": "shell",  ".fish": "shell",
    ".sql":   "sql",
    ".r":     "r",
    ".lua":   "lua",
    ".md":    "markdown", ".markdown": "markdown",
    ".rst":   "rst",
    ".html":  "html",     ".htm": "html",
    ".json":  "json",
    ".yaml":  "yaml",     ".yml": "yaml",
    ".toml":  "toml",
    ".xml":   "xml",
    ".csv":   "csv",      ".tsv": "csv",
    ".txt":   "text",
}


def detect_language(path: str) -> str:
    """Return a language slug for the given file path, or empty string if unknown."""
    return _LANGUAGE_BY_EXT.get(Path(path).suffix.lower(), "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FileManifest:
    """
    Per-database file manifest backed by AethvionDB.FILEMANIFEST sidecar.

    Each entry maps a file path (relative to the scanned folder) to:
      - hash         : SHA-256 content hash ("sha256:<hex>") for change detection
      - entity_ids   : list of entity IDs derived from this file
      - language     : detected language slug
      - size         : file size in bytes at scan time
      - last_scanned : ISO-8601 timestamp of the most recent scan

    Parameters
    ----------
    db_root : Path
        Root directory of the database (same level as entities/, chunks/, etc.).
    """

    def __init__(self, db_root: Path) -> None:
        self._path = db_root / SIDECAR
        self._lock = threading.Lock()
        self._data = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"[FileManifest] Could not read {self._path}: {exc}")
        return {"version": 1, "files": {}}

    def _save(self) -> None:
        tmp = self._path.with_suffix(".FILEMANIFEST.tmp")
        try:
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except Exception as exc:
            logger.error(f"[FileManifest] Could not save {self._path}: {exc}")
            tmp.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, path: str, file_hash: str, entity_ids: list[str]) -> None:
        """Record a file and its associated entity IDs in the manifest directly."""
        lang = detect_language(path)
        with self._lock:
            self._data["files"][path] = {
                "path":         path,
                "hash":         file_hash,
                "entity_ids":   list(entity_ids),
                "language":     lang,
                "size":         0,
                "last_scanned": _now_iso(),
            }
            self._save()

    def get(self, path: str) -> Optional[dict[str, Any]]:
        """Return the manifest entry for *path*, or None if not known."""
        with self._lock:
            return self._data["files"].get(path)

    def add_entity(
        self,
        path: str,
        entity_id: str,
        *,
        file_hash: str = "",
        size: int = 0,
        language: str = "",
    ) -> dict[str, Any]:
        """
        Record that *entity_id* was derived from *path*.

        Creates the entry if it doesn't exist yet; adds the entity_id to an
        existing entry (deduplicating). Updates hash, size, language, and
        last_scanned timestamp each time.

        Returns the updated entry.
        """
        lang = language or detect_language(path)
        with self._lock:
            entry = self._data["files"].get(path)
            if entry is None:
                entry = {
                    "path":         path,
                    "hash":         file_hash,
                    "entity_ids":   [],
                    "language":     lang,
                    "size":         size,
                    "last_scanned": _now_iso(),
                }
                self._data["files"][path] = entry
            else:
                if file_hash:
                    entry["hash"] = file_hash
                if size:
                    entry["size"] = size
                if lang:
                    entry["language"] = lang
                entry["last_scanned"] = _now_iso()

            if entity_id not in entry["entity_ids"]:
                entry["entity_ids"].append(entity_id)

            self._save()
        return entry

    def entity_ids_for(self, path: str) -> list[str]:
        """Return entity IDs known to have been derived from *path*."""
        with self._lock:
            entry = self._data["files"].get(path)
        return entry["entity_ids"] if entry else []

    def files_for_entity(self, entity_id: str) -> list[dict[str, Any]]:
        """Return all file entries that map to *entity_id*."""
        with self._lock:
            files = list(self._data["files"].values())
        return [f for f in files if entity_id in f.get("entity_ids", [])]

    def needs_rescan(self, path: str, current_hash: str) -> bool:
        """
        Return True if *path* should be re-scanned.
        Returns True when the file is unknown or its stored hash differs
        from *current_hash*.
        """
        with self._lock:
            entry = self._data["files"].get(path)
        if entry is None:
            return True
        return entry.get("hash", "") != current_hash

    def remove_entity(self, entity_id: str) -> int:
        """
        Remove *entity_id* from all file entries.
        File entries with no remaining entity_ids are also pruned.
        Returns the number of file entries that were modified.
        """
        modified = 0
        with self._lock:
            to_delete: list[str] = []
            for path, entry in self._data["files"].items():
                if entity_id in entry.get("entity_ids", []):
                    entry["entity_ids"].remove(entity_id)
                    modified += 1
                    if not entry["entity_ids"]:
                        to_delete.append(path)
            for path in to_delete:
                del self._data["files"][path]
            if modified:
                self._save()
        return modified

    def remove_file(self, path: str) -> bool:
        """Remove a file entry from the manifest directly."""
        with self._lock:
            if path in self._data["files"]:
                del self._data["files"][path]
                self._save()
                return True
        return False

    def list_all(self, prefix: str = "") -> list[dict[str, Any]]:
        """
        Return all file entries, optionally filtered by path prefix.
        Sorted by path.
        """
        with self._lock:
            entries = list(self._data["files"].values())
        if prefix:
            entries = [e for e in entries if e["path"].startswith(prefix)]
        return sorted(entries, key=lambda e: e["path"])

    def rebuild_from_entities(self, writer: Any) -> dict[str, Any]:
        """
        Rebuild the manifest by walking all entities' source_files sections.
        Replaces any existing manifest data. Returns a summary.
        """
        new_files: dict[str, Any] = {}
        count = 0
        for entity in writer.list_all():
            eid = entity["id"]
            for sf in entity.get("sections", {}).get("source_files", []):
                path = sf.get("path", "")
                if not path:
                    continue
                if path not in new_files:
                    new_files[path] = {
                        "path":         path,
                        "hash":         sf.get("hash", ""),
                        "entity_ids":   [],
                        "language":     sf.get("language", detect_language(path)),
                        "size":         sf.get("size", 0),
                        "last_scanned": sf.get("scanned_at", ""),
                    }
                if eid not in new_files[path]["entity_ids"]:
                    new_files[path]["entity_ids"].append(eid)
                    count += 1

        with self._lock:
            self._data = {"version": 1, "files": new_files}
            self._save()

        logger.info(
            f"[FileManifest] Rebuilt: {len(new_files)} files, {count} entity mappings"
        )
        return {"files": len(new_files), "entity_mappings": count}

    def stats(self) -> dict[str, Any]:
        """Return a summary of manifest coverage."""
        with self._lock:
            files = list(self._data["files"].values())
        total_files    = len(files)
        total_mappings = sum(len(f.get("entity_ids", [])) for f in files)
        by_language: dict[str, int] = {}
        for f in files:
            lang = f.get("language") or "unknown"
            by_language[lang] = by_language.get(lang, 0) + 1
        return {
            "total_files":    total_files,
            "total_mappings": total_mappings,
            "by_language":    dict(sorted(by_language.items(), key=lambda x: -x[1])),
        }
