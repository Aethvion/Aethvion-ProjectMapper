"""
project_mapper/c_analyzer.py
C source-file analyzer using tree-sitter.

Entity kinds extracted:
  "struct"  — typedef struct { ... } Name;
  "enum"    — typedef enum { ... } Name;

C has no classes. Structs and enums are stored as ClassInfo with the
appropriate kind. Top-level functions are stored as FunctionInfo.

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-c
"""

from __future__ import annotations

import re

try:
    from tree_sitter import Language, Parser
    import tree_sitter_c as _tsc
    _C_LANGUAGE = Language(_tsc.language())
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False

from .code_analyzer import (
    ArgInfo, ClassInfo, CodeAnalysis, FunctionInfo, ImportInfo, MethodInfo,
)

# ---------------------------------------------------------------------------
# Macro pre-processing
# ---------------------------------------------------------------------------
# Strip GCC/GLib attribute macros that tree-sitter-c cannot parse.
# These are annotation-only — removing them preserves code structure.
#
# GLib/GTK per-parameter annotation:
#   void fn(int x G_GNUC_UNUSED)  →  void fn(int x)
_RE_C_ATTRS = re.compile(r'\b(?:G_GNUC_UNUSED|ATTRIBUTE_TARGET_\w+)\b')


def _strip_macros_c(content: str) -> str:
    """Remove known attribute macros before handing content to tree-sitter."""
    return _RE_C_ATTRS.sub('', content)

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
# declarator traversal (resolves pointer chains to function_declarator)
# ---------------------------------------------------------------------------


def _resolve_func_decl(node):
    """Walk pointer/array wrappers to find the actual function_declarator."""
    if node is None:
        return None
    if node.type == "function_declarator":
        return node
    for c in node.children:
        result = _resolve_func_decl(c)
        if result:
            return result
    return None


def _func_decl_name(func_decl, src: bytes) -> str:
    """Extract the function name from a function_declarator node."""
    for c in func_decl.children:
        if c.type == "identifier":
            return _t(c, src)
    return ""


# ---------------------------------------------------------------------------
# parameter extraction
# ---------------------------------------------------------------------------


def _find_field_name(node, src: bytes) -> str:
    """Recursively find field_identifier inside a field_declaration."""
    for c in node.children:
        if c.type == "field_identifier":
            return _t(c, src)
        if c.type in ("pointer_declarator", "array_declarator"):
            name = _find_field_name(c, src)
            if name:
                return name
    return ""


def _find_param_name(node, src: bytes) -> str:
    """Recursively locate the innermost identifier in a parameter declarator."""
    for c in reversed(node.children):
        if c.type == "identifier":
            return _t(c, src)
        if c.type in ("pointer_declarator", "array_declarator", "abstract_declarator"):
            name = _find_param_name(c, src)
            if name:
                return name
    return ""


def _parse_c_params(param_list_node, src: bytes) -> list[str]:
    if param_list_node is None:
        return []
    names: list[str] = []
    for child in param_list_node.children:
        if child.type == "parameter_declaration":
            name = _find_param_name(child, src)
            if name and name != "void":
                names.append(name)
    return names


# ---------------------------------------------------------------------------
# typedef parsing
# ---------------------------------------------------------------------------


def _parse_typedef(node, src: bytes) -> ClassInfo | None:
    """Parse a type_definition node; return ClassInfo for struct/enum typedefs."""
    struct_spec = None
    enum_spec = None
    typedef_name: str | None = None

    for c in node.children:
        if c.type == "struct_specifier":
            struct_spec = c
        elif c.type == "enum_specifier":
            enum_spec = c
        elif c.type == "type_identifier":
            typedef_name = _t(c, src)  # last type_identifier = typedef name

    if not typedef_name:
        return None

    if struct_spec:
        body = struct_spec.child_by_field_name("body")
        class_vars: list[str] = []
        if body:
            for child in body.children:
                if child.type == "field_declaration":
                    name = _find_field_name(child, src)
                    if name:
                        class_vars.append(name)
        return ClassInfo(
            name=typedef_name, kind="struct", bases=[], methods=[], class_vars=class_vars,
            line_start=_line(node), line_end=_end_line(node),
        )

    if enum_spec:
        body = enum_spec.child_by_field_name("body")
        class_vars = []
        if body:
            for child in body.children:
                if child.type == "enumerator":
                    en = child.child_by_field_name("name")
                    if en:
                        class_vars.append(_t(en, src))
        return ClassInfo(
            name=typedef_name, kind="enum", bases=[], methods=[], class_vars=class_vars,
            line_start=_line(node), line_end=_end_line(node),
        )

    return None


# ---------------------------------------------------------------------------
# call graph extraction
# ---------------------------------------------------------------------------


def _collect_calls_c(body_node, src: bytes) -> list[tuple[str, str]]:
    """Walk a compound_statement body and return (callee_name, "") for each call."""
    if body_node is None:
        return []
    calls: list[tuple[str, str]] = []

    def _walk(node):
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn:
                if fn.type == "identifier":
                    name = _t(fn, src)
                    if name and name.isidentifier():
                        calls.append((name, ""))
                elif fn.type == "field_expression":
                    # obj->method() or obj.method()
                    f = fn.child_by_field_name("field")
                    if f and f.type == "field_identifier":
                        name = _t(f, src)
                        if name and name.isidentifier():
                            calls.append((name, ""))
        for c in node.children:
            _walk(c)

    _walk(body_node)
    return calls


# ---------------------------------------------------------------------------
# function parsing
# ---------------------------------------------------------------------------


def _parse_c_function(node, src: bytes) -> FunctionInfo | None:
    """Parse a function_definition node into a FunctionInfo."""
    decl_node = node.child_by_field_name("declarator")
    func_decl = _resolve_func_decl(decl_node)
    if not func_decl:
        return None

    name = _func_decl_name(func_decl, src)
    if not name:
        return None

    param_list = func_decl.child_by_field_name("parameters")
    args_names = _parse_c_params(param_list, src)

    ret_node = node.child_by_field_name("type")
    return_type = _t(ret_node, src) if ret_node else ""

    body_node = node.child_by_field_name("body")
    calls = _collect_calls_c(body_node, src)

    return FunctionInfo(
        name=name,
        args=[ArgInfo(name=a) for a in args_names],
        return_type=return_type,
        calls=calls,
        line_start=_line(node),
        line_end=_end_line(node),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_c(path: str, content: str) -> CodeAnalysis:
    """Parse a C source file and return a CodeAnalysis. Never raises."""
    line_count = content.count("\n") + 1

    if not _AVAILABLE:
        return CodeAnalysis(
            path=path, language="c", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                'tree-sitter-c not installed — run: '
                'pip install "tree-sitter>=0.23.0" tree-sitter-c'
            ],
        )

    try:
        content = _strip_macros_c(content)
        parser = Parser(_C_LANGUAGE)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        imports: list[ImportInfo] = []
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []

        for node in root.children:
            nt = node.type
            if nt == "preproc_include":
                path_node = node.child_by_field_name("path")
                if path_node:
                    raw = _t(path_node, src)
                    is_rel = raw.startswith('"')
                    module = raw.strip('"<>')
                    imports.append(ImportInfo(
                        module=module, names=[], is_from=False, is_relative=is_rel,
                    ))
            elif nt == "type_definition":
                cls = _parse_typedef(node, src)
                if cls:
                    classes.append(cls)
            elif nt == "function_definition":
                fn = _parse_c_function(node, src)
                if fn:
                    functions.append(fn)

        return CodeAnalysis(
            path=path, language="c", line_count=line_count,
            module_docstring="", classes=classes, functions=functions,
            imports=imports, all_exports=[], constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="c", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"c_analyzer internal error: {exc}"],
        )
