"""
project_mapper/ingestor.py
Translates CodeAnalysis results into AethvionDB entities.

Static ingestion (instant, no AI):
  - Creates or updates a module entity for the file.
  - Creates class entities for every top-level class.
  - Creates function entities for every top-level public function.
  - Wires structural relations (contains, imports, depends_on, extends).
  - Records source provenance in entity.sections.source_files + FileManifest.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .code_analyzer import CodeAnalysis, ImportInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class IngestResult:
    module_entity_id:    Optional[str] = None
    class_entity_ids:    list[str] = field(default_factory=list)
    function_entity_ids: list[str] = field(default_factory=list)
    relations_created:   int = 0
    was_created:         bool = False    # True if module entity was new
    entities_pruned:     int = 0         # removed symbols (set by scanner, not ingestor)
    errors:              list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _top_level_packages(project_root: Path) -> frozenset[str]:
    """Return the set of top-level directory names in the project root."""
    try:
        return frozenset(
            d.name for d in project_root.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__"
        )
    except Exception:
        return frozenset()


def _is_internal_import(imp: ImportInfo, top_pkgs: frozenset[str]) -> bool:
    """Return True if this import is likely an intra-project module."""
    if imp.is_relative:
        return True
    if not imp.module:
        return False
    return imp.module.split(".")[0] in top_pkgs


def _module_path_from_file(rel_path: str) -> str:
    """'core/auth/service.py'  → 'core.auth.service'
       'src/auth/service.ts'   → 'src.auth.service'
       'com/example/Foo.java'  → 'com.example.Foo'"""
    p = rel_path.replace("\\", "/")
    for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs",
                ".java", ".go", ".cs", ".rs", ".cpp", ".cc", ".cxx",
                ".c", ".h", ".hpp", ".rb", ".php", ".kt", ".swift"):
        if p.endswith(ext):
            p = p[: -len(ext)]
            break
    # Strip /index suffix (common in TS: src/auth/index.ts → src.auth)
    if p.endswith("/index"):
        p = p[:-6]
    return p.replace("/", ".")


def _import_to_file_candidates(
    module: str,
    level: int,
    current_file: str,
) -> list[str]:
    """
    Return candidate file-path strings for an import statement.

    Given the module name and relative level, produce the ordered list of
    file paths we should look up in the name index to find the real entity.

    Examples
    --------
    Absolute  : module="core.companions.engine.history", level=0
                → ["core/companions/engine/history.py",
                   "core/companions/engine/history/__init__.py"]

    Relative  : module="engine", level=1, current="core/companions/companion_engine.py"
                → ["core/companions/engine.py",
                   "core/companions/engine/__init__.py"]

    Relative  : module="", level=1, current="core/companions/companion_engine.py"
                → ["core/companions/__init__.py"]
    """
    _TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs")

    candidates: list[str] = []

    if level == 0:
        # Absolute import
        if not module:
            return candidates
        base = module.replace(".", "/")
        # Python-style dotted path
        candidates.append(base + ".py")
        candidates.append(base + "/__init__.py")
        # TypeScript/JS bare specifier (e.g. "components/Button")
        for ext in _TS_EXTS:
            candidates.append(base + ext)
        candidates.append(base + "/index.ts")
        candidates.append(base + "/index.js")
        # Java: dotted package path → directory/ClassName.java
        # e.g. "com.example.service" → "com/example/service.java"
        candidates.append(base + ".java")
    else:
        # Relative import — resolve against the current file's directory
        parts = current_file.replace("\\", "/").split("/")
        pkg_parts = parts[:-level]
        if module:
            # TypeScript relative: './utils' → module='./utils' (already stripped by caller)
            # but module here is the bare name after the dots
            sub = module.replace(".", "/").lstrip("/")
            base = "/".join(pkg_parts + [sub]) if sub else "/".join(pkg_parts)
            candidates.append(base + ".py")
            candidates.append(base + "/__init__.py")
            for ext in _TS_EXTS:
                candidates.append(base + ext)
            candidates.append(base + "/index.ts")
            candidates.append(base + "/index.js")
        else:
            # "from . import X" — the module name is empty; point at the package
            base = "/".join(pkg_parts)
            candidates.append(base + "/__init__.py")
            candidates.append(base + "/index.ts")
            candidates.append(base + "/index.js")

    return candidates


# ---------------------------------------------------------------------------
# Ingestor
# ---------------------------------------------------------------------------

class ProjectIngestor:
    """
    Translates CodeAnalysis objects into AethvionDB entities.

    Parameters
    ----------
    db_root      : Path to the database root directory.
    writer       : EntityWriter for the target DB.
    index        : NameIndex for the target DB.
    file_manifest: FileManifest for provenance tracking.
    """

    def __init__(
        self,
        db_root:       Path,
        writer:        Any,
        index:         Any,
        file_manifest: Any,
    ) -> None:
        self._db_root       = db_root
        self._writer        = writer
        self._index         = index
        self._file_manifest = file_manifest

    # ------------------------------------------------------------------
    # Static ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        analysis:      CodeAnalysis,
        project_root:  Path,
        file_hash:     str = "",
        file_size:     int = 0,
    ) -> IngestResult:
        """
        Ingest a CodeAnalysis synchronously.
        Creates/updates all entities and relations. Records provenance.
        Returns an IngestResult with entity IDs for optional Phase 2 enrichment.
        """
        result = IngestResult()
        top_pkgs = _top_level_packages(project_root)

        # ---- 1. Module entity ----------------------------------------
        module_entity, was_created = self._upsert_module(
            analysis, file_hash, file_size
        )
        result.module_entity_id = module_entity["id"]
        result.was_created      = was_created

        # ---- 2. Class entities ---------------------------------------
        for cls_info in analysis.classes:
            cls_entity, _ = self._upsert_class(cls_info, analysis.path)
            result.class_entity_ids.append(cls_entity["id"])
            # Module contains class
            result.relations_created += self._add_relation(
                module_entity["id"], "contains", cls_entity["id"],
                note=f"defined in {analysis.path}",
            )

        # ---- 3. Top-level function entities --------------------------
        for fn_info in analysis.functions:
            fn_entity, _ = self._upsert_function(fn_info, analysis.path)
            result.function_entity_ids.append(fn_entity["id"])
            # Module contains function
            result.relations_created += self._add_relation(
                module_entity["id"], "contains", fn_entity["id"],
                note=f"defined in {analysis.path}",
            )

        # ---- 4. Import relations -------------------------------------
        internal_imports = [i for i in analysis.imports if _is_internal_import(i, top_pkgs)]
        external_imports = [i for i in analysis.imports if not _is_internal_import(i, top_pkgs)]

        for imp in internal_imports:
            # Try to resolve the import to an already-scanned file entity
            # before falling back to a dotted-name stub.
            target_id: Optional[str] = None
            for candidate in _import_to_file_candidates(
                imp.module, imp.level, analysis.path
            ):
                target_id = self._index.get(candidate)
                if target_id:
                    break

            if target_id:
                # Wire directly to the real module entity — no stub needed
                result.relations_created += self._add_relation(
                    module_entity["id"], "imports", target_id,
                )
            else:
                # Target not scanned yet — create a stub for the stub resolver
                # to re-wire at end-of-scan.
                target_name = imp.module or ("." * imp.level)
                if target_name and target_name != ".":
                    target_entity, _ = self._writer.create(
                        name=target_name,
                        entity_type="module",
                        source="stub",
                        kind="software.module",
                        status="stub",
                    )
                    result.relations_created += self._add_relation(
                        module_entity["id"], "imports", target_entity["id"],
                    )

        for imp in external_imports:
            if not imp.module:
                continue
            pkg_name = imp.module.split(".")[0]
            dep_entity, _ = self._writer.create(
                name=pkg_name,
                entity_type="dependency",
                source="stub",
                kind="software.dependency",
                status="stub",
            )
            result.relations_created += self._add_relation(
                module_entity["id"], "depends_on", dep_entity["id"],
            )

        # ---- 5. Class inheritance relations --------------------------
        for cls_info, cls_id in zip(analysis.classes, result.class_entity_ids):
            for base in cls_info.bases:
                if base in ("object", "ABC", "BaseModel"):
                    continue
                base_entity, _ = self._writer.create(
                    name=base,
                    entity_type="class",
                    source="stub",
                    kind="software.class",
                    status="stub",
                )
                result.relations_created += self._add_relation(
                    cls_id, "extends", base_entity["id"],
                )

        # ---- 6. Class calls relations (static call graph) -----------
        # For each class, try to resolve its extracted callee names to known
        # entities.  Only uppercase names (class/object names) are wired —
        # raw attribute names that the call-extractor couldn't resolve to a
        # class are skipped.  Uses the same stub-creation pattern as extends.
        for cls_info, cls_id in zip(analysis.classes, result.class_entity_ids):
            for callee_name, via_method in cls_info.calls:
                # Only wire uppercase-first names (class names, not attr names)
                if not callee_name or not callee_name[0].isupper():
                    continue
                # Skip ALL_CAPS names — these are module-level constants,
                # not classes (e.g. WORKSPACE_ROOT, PROVIDER_CLASSES)
                if callee_name.isupper():
                    continue
                # Try existing index first (entity already scanned)
                target_id = self._index.get(callee_name)
                if not target_id:
                    # Create a stub so forward-references are captured even if
                    # the target file hasn't been scanned yet.
                    stub, _ = self._writer.create(
                        name=callee_name,
                        entity_type="class",
                        source="stub",
                        kind="software.class",
                        status="stub",
                    )
                    target_id = stub["id"]
                if target_id and target_id != cls_id:
                    result.relations_created += self._add_relation(
                        cls_id, "calls", target_id,
                        note=f"via {via_method}" if via_method else "",
                    )

        # ---- 7. Function calls relations (static call graph) --------
        # Mirror of step 6 but for top-level functions.  Functions cannot
        # have self-attribute assignments, so only direct instantiations and
        # factory-function patterns are captured.
        for fn_info, fn_id in zip(analysis.functions, result.function_entity_ids):
            for callee_name, via_method in fn_info.calls:
                if not callee_name or not callee_name[0].isupper():
                    continue
                if callee_name.isupper():
                    continue
                target_id = self._index.get(callee_name)
                if not target_id:
                    stub, _ = self._writer.create(
                        name=callee_name,
                        entity_type="class",
                        source="stub",
                        kind="software.class",
                        status="stub",
                    )
                    target_id = stub["id"]
                if target_id and target_id != fn_id:
                    result.relations_created += self._add_relation(
                        fn_id, "calls", target_id,
                        note=f"via {via_method}" if via_method else "",
                    )

        # ---- 8. Provenance -------------------------------------------
        from datetime import datetime, timezone
        scanned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sf_entry = {
            "path":       analysis.path,
            "lines":      [1, analysis.line_count],
            "language":   analysis.language,
            "scanned_at": scanned_at,
        }
        if file_hash:
            sf_entry["hash"] = file_hash
        if file_size:
            sf_entry["size"] = file_size
        try:
            self._writer.update(
                module_entity["id"],
                {"sections": {"source_files": [sf_entry]}},
            )
            self._file_manifest.add_entity(
                path=analysis.path,
                entity_id=module_entity["id"],
                file_hash=file_hash,
                size=file_size,
                language=analysis.language,
            )
        except Exception as exc:
            result.errors.append(f"Provenance error: {exc}")

        return result

    def _upsert_module(
        self,
        analysis:  CodeAnalysis,
        file_hash: str,
        file_size: int,
    ) -> tuple[dict[str, Any], bool]:
        module_path = _module_path_from_file(analysis.path)
        entity, was_created = self._writer.create(
            name=analysis.path,
            entity_type="module",
            source="project_mapper",
            kind="software.module",
            sections_override={
                "core": {
                    "aliases":    [module_path],
                    "tags":       [analysis.language],
                    "categories": ["Source Code"],
                },
                "properties": {
                    "language":       analysis.language,
                    "file_path":      analysis.path,
                    "module_path":    module_path,
                    "line_count":     str(analysis.line_count),
                    "class_count":    str(len(analysis.classes)),
                    "function_count": str(len(analysis.functions)),
                },
            },
        )
        if not was_created:
            # Refresh structural properties on re-scan
            self._writer.update(entity["id"], {
                "sections": {
                    "properties": {
                        "language":       analysis.language,
                        "line_count":     str(analysis.line_count),
                        "class_count":    str(len(analysis.classes)),
                        "function_count": str(len(analysis.functions)),
                    },
                },
            })
        return entity, was_created

    def _upsert_class(
        self,
        cls_info: Any,
        file_path: str,
    ) -> tuple[dict[str, Any], bool]:
        # Map cls_info.kind → entity kind and tag
        # e.g. kind="interface" → "software.interface" / tag "interface"
        #      kind=""          → "software.class"      / tag "class"
        cls_kind    = getattr(cls_info, "kind", "") or ""
        entity_kind = f"software.{cls_kind}" if cls_kind else "software.class"
        tag         = cls_kind if cls_kind else "class"

        entity, was_created = self._writer.create(
            name=cls_info.name,
            entity_type="class",
            source="project_mapper",
            kind=entity_kind,
            sections_override={
                "core": {
                    "summary": cls_info.docstring[:200] if cls_info.docstring else "",
                    "tags":    [tag],
                },
                "properties": {
                    "file_path":    file_path,
                    "base_classes": ", ".join(cls_info.bases) if cls_info.bases else "",
                    "method_count": str(len(cls_info.methods)),
                    "line_start":   str(cls_info.line_start),
                    "line_end":     str(cls_info.line_end),
                    "methods":      ", ".join(m.name for m in cls_info.methods[:15]),
                    "decorators":   ", ".join(cls_info.decorators) if cls_info.decorators else "",
                },
            },
        )
        return entity, was_created

    def _upsert_function(
        self,
        fn_info:   Any,
        file_path: str,
    ) -> tuple[dict[str, Any], bool]:
        arg_strs = []
        for a in fn_info.args[:6]:
            s = a.name
            if a.annotation:
                s += f": {a.annotation}"
            arg_strs.append(s)
        signature = f"{fn_info.name}({', '.join(arg_strs)})"
        if fn_info.return_type:
            signature += f" -> {fn_info.return_type}"

        entity, was_created = self._writer.create(
            name=fn_info.name,
            entity_type="function",
            source="project_mapper",
            kind="software.function",
            sections_override={
                "core": {
                    "summary": fn_info.docstring[:150] if fn_info.docstring else "",
                    "tags":    ["async" if fn_info.is_async else "sync"],
                },
                "properties": {
                    "file_path":  file_path,
                    "signature":  signature,
                    "is_async":   str(fn_info.is_async).lower(),
                    "line_start": str(fn_info.line_start),
                    "line_end":   str(fn_info.line_end),
                    "decorators": ", ".join(fn_info.decorators) if fn_info.decorators else "",
                },
            },
        )
        return entity, was_created

    def _add_relation(
        self,
        source_id:  str,
        kind:       str,
        target_id:  str,
        note:       str = "",
    ) -> int:
        """Add a relation to the source entity (deduplication via merge_sections)."""
        try:
            source = self._writer.get(source_id)
            if not source:
                return 0
            existing_rels = source.get("sections", {}).get("relations", [])
            for rel in existing_rels:
                if rel.get("kind") == kind and rel.get("target_id") == target_id:
                    return 0  # already exists
            new_rel: dict[str, Any] = {"kind": kind, "target_id": target_id}
            if note:
                new_rel["note"] = note
            self._writer.update(source_id, {"sections": {"relations": [new_rel]}})
            return 1
        except Exception as exc:
            logger.debug(f"[Ingestor] Could not add relation {kind}: {exc}")
            return 0

