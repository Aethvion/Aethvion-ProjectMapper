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

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..analyzers import CodeAnalysis, ImportInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class IngestResult:
    module_entity_id: str | None = None
    class_entity_ids: list[str] = field(default_factory=list)
    function_entity_ids: list[str] = field(default_factory=list)
    relations_created: int = 0
    was_created: bool = False  # True if module entity was new
    entities_pruned: int = 0  # removed symbols (set by scanner, not ingestor)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _top_level_packages(project_root: Path) -> frozenset[str]:
    """Return the set of names that indicate an intra-project import.

    Includes top-level directory names plus subdirectory names of lib/ (Ruby
    convention) and src/ (PHP/Java convention), since those languages resolve
    require/use paths relative to those roots rather than the project root.
    """
    try:
        pkgs: set[str] = set()
        for d in project_root.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__":
                pkgs.add(d.name)
        # Ruby: lib/jekyll/... → "jekyll" is the importable name, not "lib"
        # PHP/Java: src/App/... → "App" (or "app") is importable
        for subdir in ("lib", "src"):
            sub = project_root / subdir
            if sub.is_dir():
                for d in sub.iterdir():
                    if d.is_dir() and not d.name.startswith("."):
                        pkgs.add(d.name)
        return frozenset(pkgs)
    except Exception:
        return frozenset()


def _is_internal_import(imp: ImportInfo, top_pkgs: frozenset[str]) -> bool:
    """Return True if this import is likely an intra-project module."""
    if imp.is_relative:
        return True
    if not imp.module:
        return False
    # Dot-separated first component (Python, JS/TS, Go, PHP-normalized)
    first = imp.module.split(".")[0]
    if first in top_pkgs:
        return True
    # Case-insensitive: PHP PSR-4 namespaces are PascalCase but dirs are lowercase
    # e.g. "App.Models.User" (from App\Models\User) → matches "app/" directory
    if first.lower() in {p.lower() for p in top_pkgs}:
        return True
    # Slash-separated first component (Ruby require "jekyll/drops/drop")
    first_slash = imp.module.split("/")[0]
    if first_slash and first_slash != first and first_slash in top_pkgs:
        return True
    return False


def _module_path_from_file(rel_path: str) -> str:
    """'core/auth/service.py'  → 'core.auth.service'
    'src/auth/service.ts'   → 'src.auth.service'
    'com/example/Foo.java'  → 'com.example.Foo'"""
    p = rel_path.replace("\\", "/")
    for ext in (
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".java",
        ".go",
        ".cs",
        ".rs",
        ".cpp",
        ".cc",
        ".cxx",
        ".c",
        ".h",
        ".hpp",
        ".rb",
        ".php",
        ".kt",
        ".swift",
        ".unity",
        ".prefab",
        ".asset",
    ):
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
        # Rust: module path → module.rs or module/mod.rs
        candidates.append(base + ".rs")
        candidates.append(base + "/mod.rs")
        # Ruby: module path → module.rb (for absolute require paths)
        candidates.append(base + ".rb")
        # Also try with last component dropped (Type import: crate::module::Type → module.rs)
        base_no_last = "/".join(base.split("/")[:-1])
        if base_no_last:
            candidates.append(base_no_last + ".rs")
            candidates.append(base_no_last + "/mod.rs")
            candidates.append("lib/" + base_no_last + ".rb")
        # Ruby lib/ prefix convention: require "jekyll/drops/drop" → lib/jekyll/drops/drop.rb
        candidates.append("lib/" + base + ".rb")
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
            # Rust relative: use crate::module::Type (level=1 set by rust_analyzer)
            # Try anchored from current file's dir (self::module)
            candidates.append(base + ".rs")
            candidates.append(base + "/mod.rs")
            base_no_last = "/".join(base.split("/")[:-1])
            if base_no_last:
                candidates.append(base_no_last + ".rs")
                candidates.append(base_no_last + "/mod.rs")
            # Also try anchored from src/ (crate:: always refers to crate root)
            if current_file.endswith(".rs"):
                rust_sub = module.replace(".", "/")
                candidates.append("src/" + rust_sub + ".rs")
                candidates.append("src/" + rust_sub + "/mod.rs")
                rust_no_last = "/".join(rust_sub.split("/")[:-1])
                if rust_no_last:
                    candidates.append("src/" + rust_no_last + ".rs")
                    candidates.append("src/" + rust_no_last + "/mod.rs")
            # Ruby require_relative
            candidates.append(base + ".rb")
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
    writer       : PMEntityStore for the target DB.
    index        : NameIndex for the target DB.
    file_manifest: FileManifest for provenance tracking.
    """

    def __init__(
        self,
        db_root: Path,
        writer: Any,
        index: Any,
        file_manifest: Any,
    ) -> None:
        self._db_root = db_root
        self._writer = writer
        self._index = index
        self._file_manifest = file_manifest

    # ------------------------------------------------------------------
    # Static ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        analysis: CodeAnalysis,
        project_root: Path,
        file_hash: str = "",
        file_size: int = 0,
    ) -> IngestResult:
        """
        Ingest a CodeAnalysis synchronously.
        Creates/updates all entities and relations. Records provenance.
        Returns an IngestResult with entity IDs for optional Phase 2 enrichment.
        """
        result = IngestResult()
        top_pkgs = _top_level_packages(project_root)

        # ---- 1. Module entity ----------------------------------------
        from ..analyzers.unity import read_meta_guid_for_file

        meta_guid = read_meta_guid_for_file(project_root / analysis.path)
        module_entity, was_created = self._upsert_module(analysis, file_hash, file_size, meta_guid)
        result.module_entity_id = module_entity["id"]
        result.was_created = was_created

        # ---- 2. Class entities ---------------------------------------
        stem_lower = Path(analysis.path).stem.lower()
        primary_cls_id: str | None = None
        for cls_info in analysis.classes:
            cls_entity, _ = self._upsert_class(cls_info, analysis.path)
            result.class_entity_ids.append(cls_entity["id"])
            if primary_cls_id is None or cls_info.name.lower() == stem_lower:
                primary_cls_id = cls_entity["id"]
            # Module contains class
            result.relations_created += self._add_relation(
                module_entity["id"],
                "contains",
                cls_entity["id"],
                note=f"defined in {analysis.path}",
            )

        # Register Unity .meta GUID alias on the primary class (for .cs scripts)
        # or on the module entity (for .prefab / .unity / .asset files).
        if meta_guid:
            guid_owner_id = primary_cls_id or module_entity["id"]
            self._index.register_aliases(guid_owner_id, [f"guid:{meta_guid}"])
            if primary_cls_id:
                self._writer.update(
                    primary_cls_id,
                    {"sections": {"properties": {"unity_guid": meta_guid}}},
                )

        # ---- 3. Top-level function entities --------------------------
        for fn_info in analysis.functions:
            fn_entity, _ = self._upsert_function(fn_info, analysis.path)
            result.function_entity_ids.append(fn_entity["id"])
            # Module contains function
            result.relations_created += self._add_relation(
                module_entity["id"],
                "contains",
                fn_entity["id"],
                note=f"defined in {analysis.path}",
            )

        # ---- 4. Import relations -------------------------------------
        internal_imports = [i for i in analysis.imports if _is_internal_import(i, top_pkgs)]
        external_imports = [i for i in analysis.imports if not _is_internal_import(i, top_pkgs)]

        for imp in internal_imports:
            # Try to resolve the import to an already-scanned file entity
            # before falling back to a dotted-name stub.
            target_id: str | None = None
            for candidate in _import_to_file_candidates(imp.module, imp.level, analysis.path):
                target_id = self._index.get(candidate)
                if target_id:
                    break

            if target_id:
                # Wire directly to the real module entity — no stub needed
                result.relations_created += self._add_relation(
                    module_entity["id"],
                    "imports",
                    target_id,
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
                        module_entity["id"],
                        "imports",
                        target_entity["id"],
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
                module_entity["id"],
                "depends_on",
                dep_entity["id"],
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
                    cls_id,
                    "extends",
                    base_entity["id"],
                )

        # ---- 5b. Typed & [SerializeField] field reference relations --
        for cls_info, cls_id in zip(analysis.classes, result.class_entity_ids):
            for field_name, field_type, is_serialized in getattr(cls_info, "field_refs", []):
                if not field_type or field_type.isupper() or field_type == cls_info.name:
                    continue
                target_id = self._index.get(field_type)
                if not target_id and field_type[0].isupper():
                    stub, _ = self._writer.create(
                        name=field_type,
                        entity_type="class",
                        source="stub",
                        kind="software.class",
                        status="stub",
                    )
                    target_id = stub["id"]
                if target_id and target_id != cls_id:
                    note = f"[SerializeField] {field_name}" if is_serialized else f"field {field_name}"
                    result.relations_created += self._add_relation(
                        cls_id,
                        "uses",
                        target_id,
                        note=note,
                    )

        # ---- 6. Class calls relations (static call graph) -----------
        # Wire extracted callee names to known entities.  Uppercase names also
        # get stubs (forward-reference support); lowercase names are only wired
        # if the entity already exists in the index (no stub creation for them).
        for cls_info, cls_id in zip(analysis.classes, result.class_entity_ids):
            method_calls_list = getattr(cls_info, "method_calls", [])
            by_receiver: dict[str, list[str]] = {}
            for recv, mname, _via in method_calls_list:
                if recv and mname:
                    lst = by_receiver.setdefault(recv, [])
                    if mname not in lst:
                        lst.append(mname)

            for callee_name, via_method in cls_info.calls:
                if not callee_name:
                    continue
                # Skip ALL_CAPS names — module-level constants, not classes
                if callee_name.isupper():
                    continue
                target_id = self._index.get(callee_name)
                if not target_id and callee_name[0].isupper():
                    # Create stubs only for uppercase (class/type) names so
                    # forward-references are captured even before the target
                    # file is scanned.  Lowercase function names get no stub —
                    # we only wire them if they already exist.
                    stub, _ = self._writer.create(
                        name=callee_name,
                        entity_type="class",
                        source="stub",
                        kind="software.class",
                        status="stub",
                    )
                    target_id = stub["id"]
                if target_id and target_id != cls_id:
                    cm = by_receiver.get(callee_name, [])
                    result.relations_created += self._add_relation(
                        cls_id,
                        "calls",
                        target_id,
                        note=f"via {via_method}" if via_method else "",
                        called_methods=cm,
                    )

            # Wire method calls whose receiver or method name already resolves in store
            result.relations_created += self._wire_method_calls(cls_id, method_calls_list)

        # ---- 7. Function calls relations (static call graph) --------
        # Same logic as step 6 but for top-level functions.
        for fn_info, fn_id in zip(analysis.functions, result.function_entity_ids):
            fn_mcalls = getattr(fn_info, "method_calls", [])
            for callee_name, via_method in fn_info.calls:
                if not callee_name:
                    continue
                if callee_name.isupper():
                    continue
                target_id = self._index.get(callee_name)
                if not target_id and callee_name[0].isupper():
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
                        fn_id,
                        "calls",
                        target_id,
                        note=f"via {via_method}" if via_method else "",
                    )
            if fn_mcalls:
                result.relations_created += self._wire_method_calls(fn_id, fn_mcalls)

        # ---- 8. Module-level calls & Unity asset references ----------
        # Wire calls made at module scope (outside any function/class body).
        # Only wires to already-indexed entities — no stubs for module-level calls.
        for callee_name, _ in analysis.module_calls:
            if not callee_name or callee_name.isupper():
                continue
            target_id = self._index.get(callee_name)
            if target_id and target_id != module_entity["id"]:
                result.relations_created += self._add_relation(
                    module_entity["id"],
                    "calls",
                    target_id,
                )

        # Wire Unity scene/prefab/asset GUID references that are already indexed
        for ref_guid in getattr(analysis, "unity_guid_refs", []):
            target_id = self._index.get(f"guid:{ref_guid}")
            if target_id and target_id != module_entity["id"]:
                result.relations_created += self._add_relation(
                    module_entity["id"],
                    "uses",
                    target_id,
                    note=f"attached in {Path(analysis.path).name}",
                )

        # Wire UnityEvent persistent method calls from scene/prefab
        unity_events = getattr(analysis, "unity_event_calls", [])
        if unity_events:
            result.relations_created += self._wire_method_calls(
                module_entity["id"], unity_events
            )

        # ---- 9. Provenance -------------------------------------------
        from datetime import datetime, timezone

        scanned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sf_entry = {
            "path": analysis.path,
            "lines": [1, analysis.line_count],
            "language": analysis.language,
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
                save=False,
            )
        except Exception as exc:
            result.errors.append(f"Provenance error: {exc}")

        return result

    def _upsert_module(
        self,
        analysis: CodeAnalysis,
        file_hash: str,
        file_size: int,
        meta_guid: str = "",
    ) -> tuple[dict[str, Any], bool]:
        module_path = _module_path_from_file(analysis.path)
        mod_kind = getattr(analysis, "entity_kind_override", "") or "software.module"
        aliases = [module_path]
        fname = Path(analysis.path).name
        if fname != analysis.path and fname not in aliases:
            aliases.append(fname)

        mod_props: dict[str, Any] = {
            "language": analysis.language,
            "file_path": analysis.path,
            "module_path": module_path,
            "line_count": str(analysis.line_count),
            "class_count": str(len(analysis.classes)),
            "function_count": str(len(analysis.functions)),
        }
        if meta_guid:
            mod_props["unity_guid"] = meta_guid
        guid_refs = getattr(analysis, "unity_guid_refs", [])
        if guid_refs:
            mod_props["referenced_guids"] = guid_refs
        event_calls = getattr(analysis, "unity_event_calls", [])
        if event_calls:
            mod_props["called_methods"] = [list(x) for x in event_calls]

        entity, was_created = self._writer.create(
            name=analysis.path,
            entity_type="module",
            source="project_mapper",
            kind=mod_kind,
            sections_override={
                "core": {
                    "aliases": aliases,
                    "tags": [analysis.language, mod_kind] if mod_kind != "software.module" else [analysis.language],
                    "categories": ["Source Code"],
                },
                "properties": mod_props,
            },
        )
        if not was_created:
            # Refresh AST-derived fields on re-scan
            self._writer.update(
                entity["id"],
                {
                    "kind": mod_kind,
                    "sections": {
                        "core": {
                            "summary": analysis.module_docstring[:200]
                            if analysis.module_docstring
                            else "",
                            "aliases": aliases,
                        },
                        "properties": mod_props,
                    },
                },
            )
        return entity, was_created

    def _upsert_class(
        self,
        cls_info: Any,
        file_path: str,
    ) -> tuple[dict[str, Any], bool]:
        # Map cls_info.kind → entity kind and tag
        # e.g. kind="interface" → "software.interface" / tag "interface"
        #      kind=""          → "software.class"      / tag "class"
        cls_kind = getattr(cls_info, "kind", "") or ""
        entity_kind = f"software.{cls_kind}" if cls_kind else "software.class"
        tag = cls_kind if cls_kind else "class"

        method_details: list[dict[str, Any]] = []
        for m in cls_info.methods:
            sig = f"{m.name}({', '.join(m.args)})"
            if getattr(m, "return_type", ""):
                sig += f" -> {m.return_type}"
            md: dict[str, Any] = {"name": m.name, "signature": sig}
            if getattr(m, "line_start", 0):
                md["line_start"] = m.line_start
            if getattr(m, "line_end", 0):
                md["line_end"] = m.line_end
            method_details.append(md)

        method_calls = getattr(cls_info, "method_calls", [])
        field_refs = getattr(cls_info, "field_refs", [])
        serialized_str = ", ".join(
            f"{fn}: {ft}" for fn, ft, is_ser in field_refs if is_ser
        )

        cls_props: dict[str, Any] = {
            "file_path": file_path,
            "base_classes": ", ".join(cls_info.bases) if cls_info.bases else "",
            "method_count": str(len(cls_info.methods)),
            "line_start": str(cls_info.line_start),
            "line_end": str(cls_info.line_end),
            "methods": ", ".join(m.name for m in cls_info.methods),
            "method_details": method_details,
            "decorators": ", ".join(cls_info.decorators) if cls_info.decorators else "",
        }
        if method_calls:
            cls_props["called_methods"] = [list(mc) for mc in method_calls]
        if serialized_str:
            cls_props["serialized_fields"] = serialized_str

        entity, was_created = self._writer.create(
            name=cls_info.name,
            entity_type="class",
            source="project_mapper",
            kind=entity_kind,
            sections_override={
                "core": {
                    "summary": cls_info.docstring[:200] if cls_info.docstring else "",
                    "tags": [tag],
                },
                "properties": cls_props,
            },
        )
        if not was_created:
            # Refresh AST-derived fields on re-scan. pm_contribute data lives in
            # sections.properties (custom keys) and sections.timeline — not touched here.
            self._writer.update(
                entity["id"],
                {
                    "sections": {
                        "core": {
                            "summary": cls_info.docstring[:200] if cls_info.docstring else "",
                            "tags": [tag],
                        },
                        "properties": cls_props,
                    },
                },
            )
        return entity, was_created

    def _upsert_function(
        self,
        fn_info: Any,
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

        fn_mcalls = getattr(fn_info, "method_calls", [])
        fn_props: dict[str, Any] = {
            "file_path": file_path,
            "signature": signature,
            "is_async": str(fn_info.is_async).lower(),
            "line_start": str(fn_info.line_start),
            "line_end": str(fn_info.line_end),
            "decorators": ", ".join(fn_info.decorators) if fn_info.decorators else "",
        }
        if fn_mcalls:
            fn_props["called_methods"] = [list(mc) for mc in fn_mcalls]

        entity, was_created = self._writer.create(
            name=fn_info.name,
            entity_type="function",
            source="project_mapper",
            kind="software.function",
            sections_override={
                "core": {
                    "summary": fn_info.docstring[:150] if fn_info.docstring else "",
                    "tags": ["async" if fn_info.is_async else "sync"],
                },
                "properties": fn_props,
            },
        )
        if not was_created:
            self._writer.update(
                entity["id"],
                {
                    "sections": {
                        "core": {
                            "summary": fn_info.docstring[:150] if fn_info.docstring else "",
                            "tags": ["async" if fn_info.is_async else "sync"],
                        },
                        "properties": fn_props,
                    },
                },
            )
        return entity, was_created

    def _wire_method_calls(
        self,
        source_id: str,
        method_calls: list[tuple[str, str, str]],
    ) -> int:
        """
        Attempt to resolve method calls against already-indexed class entities.
        Calls to classes scanned later are resolved by cleanup.resolve_stubs().
        Never creates class stubs for unresolved method names.
        """
        if not method_calls:
            return 0
        created = 0
        # Build quick lookup of active class entities and their methods
        all_entities = self._writer.list_all(include_deleted=False)
        methods_to_classes: dict[str, list[str]] = {}
        for ent in all_entities:
            if ent.get("status") != "active" or ent.get("type") != "class":
                continue
            eid = ent["id"]
            m_str = ent.get("sections", {}).get("properties", {}).get("methods", "")
            if m_str:
                for m in m_str.split(","):
                    mn = m.strip().lower()
                    if mn:
                        methods_to_classes.setdefault(mn, []).append(eid)

        for recv_hint, mname, via in method_calls:
            if not mname:
                continue
            target_ids: list[str] = []
            if recv_hint:
                tid = self._index.get(recv_hint)
                if tid and tid != source_id:
                    target_ent = self._writer.get(tid)
                    if target_ent and target_ent.get("status") == "active":
                        target_ids.append(tid)
            if not target_ids:
                cands = [
                    cid
                    for cid in methods_to_classes.get(mname.lower(), [])
                    if cid != source_id
                ]
                if 1 <= len(cands) <= 3:
                    target_ids.extend(cands)

            for tid in target_ids:
                note = f"via {via} -> {mname}" if via else f"calls {mname}"
                created += self._add_relation(
                    source_id,
                    "calls",
                    tid,
                    note=note,
                    called_methods=[mname],
                )
        return created

    def _add_relation(
        self,
        source_id: str,
        kind: str,
        target_id: str,
        note: str = "",
        called_methods: list[str] | None = None,
    ) -> int:
        """Add or enrich a relation on the source entity."""
        try:
            source = self._writer.get(source_id)
            if not source:
                return 0
            existing_rels = source.get("sections", {}).get("relations", [])
            for rel in existing_rels:
                if rel.get("kind") == kind and rel.get("target_id") == target_id:
                    changed = False
                    if called_methods:
                        existing_cm = list(rel.get("called_methods", []))
                        for cm in called_methods:
                            if cm and cm not in existing_cm:
                                existing_cm.append(cm)
                                changed = True
                        if changed:
                            rel["called_methods"] = existing_cm
                    if note and not rel.get("note"):
                        rel["note"] = note
                        changed = True
                    if changed:
                        self._writer.update(
                            source_id,
                            {"sections": {"relations": existing_rels}},
                            merge_sections=False,
                        )
                    return 0  # already existed
            new_rel: dict[str, Any] = {"kind": kind, "target_id": target_id}
            if note:
                new_rel["note"] = note
            if called_methods:
                new_rel["called_methods"] = [cm for cm in called_methods if cm]
            self._writer.update(source_id, {"sections": {"relations": [new_rel]}})
            return 1
        except Exception as exc:
            logger.debug(f"[Ingestor] Could not add relation {kind}: {exc}")
            return 0
