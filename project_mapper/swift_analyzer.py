"""
core/project_mapper/swift_analyzer.py
Swift source-file analyzer using tree-sitter.

Entity kinds extracted:
  ""           — class (default)
  "struct"     — struct declaration
  "enum"       — enum declaration
  "actor"      — actor declaration
  "protocol"   — protocol declaration
  "extension"  — extension (methods attached to the extended type name)
  "typealias"  — typealias declaration

Note: In tree-sitter-swift, ALL of class / struct / enum / actor / extension
use the `class_declaration` node type. The leading keyword distinguishes them.
Protocol declarations use `protocol_declaration`.

Handles:
  - class / struct / enum / actor / extension / protocol / typealias
  - inheritance specifiers (`: BaseClass, Protocol`)
  - instance methods (func) and initializers (init)
  - enum cases as class_vars
  - import declarations

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-swift
"""

from __future__ import annotations

try:
    from tree_sitter import Language, Parser
    import tree_sitter_swift as _tsswift
    _SWIFT_LANGUAGE = Language(_tsswift.language())
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False

from .code_analyzer import (
    ArgInfo, ClassInfo, CodeAnalysis, FunctionInfo, ImportInfo, MethodInfo,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _t(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _ft(node, field: str, src: bytes) -> str:
    child = node.child_by_field_name(field)
    return _t(child, src) if child else ""


def _line(node) -> int:
    return node.start_point[0] + 1


def _end_line(node) -> int:
    return node.end_point[0] + 1


# ---------------------------------------------------------------------------
# kind detection (class_declaration covers class / struct / enum / actor / extension)
# ---------------------------------------------------------------------------


def _swift_kind(node, src: bytes) -> str:
    """Determine kind from the leading keyword of a class_declaration."""
    for c in node.children:
        ct = c.type
        if ct == "struct":
            return "struct"
        if ct == "enum":
            return "enum"
        if ct == "actor":
            return "actor"
        if ct == "extension":
            return "extension"
        if ct == "class":
            return ""   # regular class
    return ""


# ---------------------------------------------------------------------------
# name extraction
# ---------------------------------------------------------------------------


def _swift_class_name(node, src: bytes) -> str:
    """
    Extract type name from a class_declaration.
    Extension uses user_type as name field; class/struct/enum/actor use type_identifier.
    """
    name_node = node.child_by_field_name("name")
    if name_node:
        return _t(name_node, src)
    # Fallback: find first type_identifier or user_type child
    for c in node.children:
        if c.type in ("type_identifier", "user_type"):
            return _t(c, src)
    return ""


# ---------------------------------------------------------------------------
# inheritance
# ---------------------------------------------------------------------------


def _swift_bases(node, src: bytes) -> list[str]:
    """Extract base / protocol names from inheritance_specifier children."""
    bases: list[str] = []
    for c in node.children:
        if c.type == "inheritance_specifier":
            # user_type → type_identifier
            for cc in c.children:
                if cc.type == "user_type":
                    for t in cc.children:
                        if t.type == "type_identifier":
                            bases.append(_t(t, src))
                            break
                    break
                elif cc.type == "type_identifier":
                    bases.append(_t(cc, src))
                    break
    return bases


# ---------------------------------------------------------------------------
# parameter parsing
# ---------------------------------------------------------------------------


def _parse_swift_params(node, src: bytes) -> list[str]:
    """
    Extract parameter names from function parameters.
    Swift parameters look like: `(label name: Type)`.
    The `name` field of a `parameter` node is the internal name.
    """
    if node is None:
        return []
    names: list[str] = []
    for child in node.children:
        if child.type == "parameter":
            name_node = child.child_by_field_name("name")
            if name_node:
                raw = _t(name_node, src)
                # skip wildcard labels ("_")
                if raw != "_":
                    names.append(raw)
    return names


# ---------------------------------------------------------------------------
# method / init parsing
# ---------------------------------------------------------------------------


def _parse_func_decl(node, src: bytes) -> MethodInfo | None:
    """Parse a function_declaration node."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    # Detect async: look for `async` keyword sibling
    is_async = any(c.type == "async" for c in node.children)

    # Parameters: find the `(...)` block (no named field — walk children)
    args: list[str] = []
    for c in node.children:
        # parameters group is unnamed; it contains `parameter` nodes
        if c.type == "parameter":
            # This is a top-level parameter (no wrapping node in some grammar versions)
            name_node2 = c.child_by_field_name("name")
            if name_node2:
                raw = _t(name_node2, src)
                if raw != "_":
                    args.append(raw)
        # Some grammar versions wrap params in a node type containing "()"
    # Better: gather all `parameter` children at any depth inside the function header
    # Walk the function node's non-body children for `parameter` nodes
    if not args:
        args = _collect_params_from_func(node, src)

    ret_node = node.child_by_field_name("return_type")
    return_type = _t(ret_node, src) if ret_node else ""

    # Class-level method: check for `class` or `static` modifier before `func`
    is_class = False
    for c in node.children:
        if c.type in ("class", "static"):
            is_class = True
            break

    return MethodInfo(
        name=name, args=args, return_type=return_type,
        is_async=is_async, is_classmethod=is_class,
    )


def _collect_params_from_func(func_node, src: bytes) -> list[str]:
    """Walk a function declaration (excluding body) to collect parameter names."""
    names: list[str] = []
    body = func_node.child_by_field_name("body")
    for c in func_node.children:
        if c is body:
            break
        if c.type == "parameter":
            name_node = c.child_by_field_name("name")
            if name_node:
                raw = _t(name_node, src)
                if raw and raw != "_":
                    names.append(raw)
    return names


def _parse_init_decl(node, src: bytes) -> MethodInfo | None:
    """Parse an init_declaration node as a constructor method."""
    # Collect params
    args = _collect_params_from_func(node, src)
    return MethodInfo(name="init", args=args)


# ---------------------------------------------------------------------------
# class / protocol body parsing
# ---------------------------------------------------------------------------


def _parse_class_body(body_node, src: bytes, kind: str) -> tuple[list[MethodInfo], list[str]]:
    """Extract methods and class_vars from a class_body or enum_class_body."""
    methods: list[MethodInfo] = []
    class_vars: list[str] = []

    if body_node is None:
        return methods, class_vars

    for child in body_node.children:
        nt = child.type
        if nt == "function_declaration":
            m = _parse_func_decl(child, src)
            if m:
                methods.append(m)
        elif nt == "init_declaration":
            m = _parse_init_decl(child, src)
            if m:
                methods.append(m)
        elif nt == "enum_entry":
            # enum cases
            name_node = child.child_by_field_name("name")
            if name_node:
                class_vars.append(_t(name_node, src))

    return methods, class_vars


def _parse_protocol_body(body_node, src: bytes) -> list[MethodInfo]:
    """Extract method signatures from a protocol_body."""
    methods: list[MethodInfo] = []
    if body_node is None:
        return methods
    for child in body_node.children:
        if child.type == "protocol_function_declaration":
            name_node = child.child_by_field_name("name")
            if name_node:
                name = _t(name_node, src)
                # collect params
                args = _collect_params_from_func(child, src)
                ret_node = child.child_by_field_name("return_type")
                return_type = _t(ret_node, src) if ret_node else ""
                methods.append(MethodInfo(name=name, args=args, return_type=return_type))
    return methods


# ---------------------------------------------------------------------------
# top-level parsing
# ---------------------------------------------------------------------------


def _parse_class_decl(node, src: bytes) -> ClassInfo | None:
    """Parse any class_declaration (class/struct/enum/actor/extension)."""
    name = _swift_class_name(node, src)
    if not name:
        return None
    kind = _swift_kind(node, src)
    bases = _swift_bases(node, src)

    body_node = node.child_by_field_name("body")
    methods, class_vars = _parse_class_body(body_node, src, kind)

    return ClassInfo(
        name=name, kind=kind, bases=bases, methods=methods, class_vars=class_vars,
        line_start=_line(node), line_end=_end_line(node),
    )


def _parse_protocol_decl(node, src: bytes) -> ClassInfo | None:
    """Parse a protocol_declaration."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    body_node = node.child_by_field_name("body")
    methods = _parse_protocol_body(body_node, src)

    return ClassInfo(
        name=name, kind="protocol", bases=[], methods=methods, class_vars=[],
        line_start=_line(node), line_end=_end_line(node),
    )


# ---------------------------------------------------------------------------
# recursive walker
# ---------------------------------------------------------------------------


def _walk(node, src: bytes,
          classes: list[ClassInfo],
          functions: list[FunctionInfo],
          imports: list[ImportInfo]) -> None:
    for child in node.children:
        nt = child.type
        if nt == "class_declaration":
            cls = _parse_class_decl(child, src)
            if cls:
                classes.append(cls)
        elif nt == "protocol_declaration":
            cls = _parse_protocol_decl(child, src)
            if cls:
                classes.append(cls)
        elif nt == "typealias_declaration":
            name_node = child.child_by_field_name("name")
            if name_node:
                classes.append(ClassInfo(
                    name=_t(name_node, src), kind="typealias", bases=[], methods=[],
                    class_vars=[], line_start=_line(child), line_end=_end_line(child),
                ))
        elif nt == "function_declaration":
            m = _parse_func_decl(child, src)
            if m:
                functions.append(FunctionInfo(
                    name=m.name,
                    args=[ArgInfo(name=a) for a in m.args],
                    return_type=m.return_type,
                    is_async=m.is_async,
                    line_start=_line(child),
                    line_end=_end_line(child),
                ))
        elif nt == "import_declaration":
            # import Foundation  /  import UIKit
            # The module name is after the `import` keyword
            parts: list[str] = []
            for c in child.children:
                if c.type in ("identifier", "simple_identifier"):
                    parts.append(_t(c, src))
            if parts:
                module = ".".join(parts)
                imports.append(ImportInfo(
                    module=module, names=[], is_from=False, is_relative=False,
                ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_swift(path: str, content: str) -> CodeAnalysis:
    """Parse a Swift source file and return a CodeAnalysis. Never raises."""
    line_count = content.count("\n") + 1

    if not _AVAILABLE:
        return CodeAnalysis(
            path=path, language="swift", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                'tree-sitter-swift not installed — run: '
                'pip install "tree-sitter>=0.23.0" tree-sitter-swift'
            ],
        )

    try:
        parser = Parser(_SWIFT_LANGUAGE)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        imports: list[ImportInfo] = []
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []

        _walk(root, src, classes, functions, imports)

        return CodeAnalysis(
            path=path, language="swift", line_count=line_count,
            module_docstring="", classes=classes, functions=functions,
            imports=imports, all_exports=[], constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="swift", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"swift_analyzer internal error: {exc}"],
        )
