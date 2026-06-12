"""
project_mapper/delta.py
Delta analysis — compares the current filesystem state against the FileManifest.

This module is **read-only**: it never modifies the database or the manifest.
Use it to preview what a scan would change, or to drive the cleanup pipeline.

Primary entry point
-------------------
    result = compute_delta(project_root, file_manifest)
    # result.new_files      — on disk, not in manifest
    # result.modified_files — on disk, hash changed
    # result.deleted_files  — in manifest, not on disk
    # result.unchanged_count

Pass the result to cleanup.run_deletion_cleanup() to apply mutations for
deleted files, or start a scan with incremental=True to re-process changed ones.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .scanner import SUPPORTED_EXTENSIONS, _EXCLUDED_DIRS

if TYPE_CHECKING:
    from .db.file_manifest import FileManifest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FileStatus:
    """Describes the state of a single source file relative to the manifest."""
    path:       str              # relative path (forward-slash normalised)
    abs_path:   str              # absolute path on disk
    hash:       str              # current content hash  ("sha256:…") or "" if not computed
    old_hash:   str = ""         # hash stored in manifest (empty if file is new)
    entity_ids: list[str] = field(default_factory=list)   # entity IDs from manifest


@dataclass
class DeltaResult:
    """Full filesystem-vs-manifest diff for one project root."""
    project_root:      str
    new_files:         list[FileStatus]   # present on disk, absent from manifest
    modified_files:    list[FileStatus]   # present on disk AND in manifest, but hash changed
    deleted_files:     list[str]          # in manifest, no longer on disk (rel paths)
    unchanged_count:   int                # files present on disk with matching hash
    total_on_disk:     int                # total supported files found on disk
    total_in_manifest: int                # total entries currently in manifest

    # Convenience
    @property
    def has_changes(self) -> bool:
        return bool(self.new_files or self.modified_files or self.deleted_files)

    def summary(self) -> dict[str, Any]:
        return {
            "project_root":      self.project_root,
            "new_files":         len(self.new_files),
            "modified_files":    len(self.modified_files),
            "deleted_files":     len(self.deleted_files),
            "unchanged_files":   self.unchanged_count,
            "total_on_disk":     self.total_on_disk,
            "total_in_manifest": self.total_in_manifest,
            "has_changes":       self.has_changes,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_hash(fp: Path) -> str:
    """
    Return 'sha256:<hex>' for the file at *fp*, or '' on read error.

    Reads via text mode (UTF-8, error-replace) so that newline normalisation
    (CRLF → LF on Windows) matches the hash produced by the scanner, which
    also reads text before hashing.
    """
    try:
        text = fp.read_text(encoding="utf-8", errors="replace")
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    except OSError as exc:
        logger.debug(f"[Delta] Could not hash {fp}: {exc}")
        return ""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def compute_delta(
    project_root:   "str | Path",
    file_manifest:  "FileManifest",
    *,
    compute_hashes: bool = True,
) -> DeltaResult:
    """
    Walk *project_root* and compare every supported file against the manifest.

    Parameters
    ----------
    project_root    : Absolute path to the project directory.
    file_manifest   : FileManifest for the target database.
    compute_hashes  : When True (default), compute SHA-256 for every file.
                      This accurately identifies modified files but reads every
                      file.  When False, any file already in the manifest is
                      counted as unchanged and only absent/new files are flagged
                      (fast, useful for large projects where you only need a
                      file-count estimate).

    Returns
    -------
    DeltaResult
    """
    root = Path(project_root)
    if not root.exists():
        raise FileNotFoundError(f"Project root does not exist: {project_root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {project_root}")

    # Snapshot the manifest once (thread-safe: list_all() holds the lock)
    manifest_entries: dict[str, dict[str, Any]] = {
        e["path"]: e for e in file_manifest.list_all()
    }

    new_files:      list[FileStatus] = []
    modified_files: list[FileStatus] = []
    unchanged       = 0
    seen_paths:     set[str] = set()

    for dirpath, dirs, files in os.walk(root):
        # Skip hidden directories and known non-source folders
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in _EXCLUDED_DIRS
        ]
        for fn in sorted(files):
            fp  = Path(dirpath) / fn
            ext = fp.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            # Mirror scanner.py's size filter so minified bundles don't show
            # up as perpetual "new files" after every scan
            try:
                st = fp.stat()
            except OSError:
                st = None
            if st is not None and st.st_size > 250_000:
                continue

            rel = str(fp.relative_to(root)).replace("\\", "/")
            seen_paths.add(rel)

            manifest_entry = manifest_entries.get(rel)

            if manifest_entry is None:
                # File has never been scanned
                new_files.append(FileStatus(
                    path=rel,
                    abs_path=str(fp),
                    hash=_file_hash(fp) if compute_hashes else "",
                ))
                continue

            # Stat fast path: stored size+mtime both match → unchanged without
            # reading the file. Entries without stat data (older manifests)
            # fall through to the hash comparison.
            if (st is not None
                    and manifest_entry.get("size", 0)
                    and manifest_entry.get("mtime", 0.0)
                    and manifest_entry["size"] == st.st_size
                    and manifest_entry["mtime"] == st.st_mtime):
                unchanged += 1
                continue

            stored_hash  = manifest_entry.get("hash", "")
            entity_ids   = manifest_entry.get("entity_ids", [])
            current_hash = _file_hash(fp) if compute_hashes else ""

            if compute_hashes and current_hash and stored_hash and current_hash != stored_hash:
                # Content changed since last scan
                modified_files.append(FileStatus(
                    path=rel,
                    abs_path=str(fp),
                    hash=current_hash,
                    old_hash=stored_hash,
                    entity_ids=list(entity_ids),
                ))
            else:
                # Not hashing, or hash matches → treat as unchanged
                unchanged += 1

    # Files recorded in the manifest that no longer exist on disk
    deleted_files = [rel for rel in manifest_entries if rel not in seen_paths]

    total_on_disk = len(new_files) + len(modified_files) + unchanged

    return DeltaResult(
        project_root=str(root),
        new_files=new_files,
        modified_files=modified_files,
        deleted_files=deleted_files,
        unchanged_count=unchanged,
        total_on_disk=total_on_disk,
        total_in_manifest=len(manifest_entries),
    )
