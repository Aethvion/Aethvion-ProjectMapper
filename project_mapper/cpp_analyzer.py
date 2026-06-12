"""
project_mapper/cpp_analyzer.py
C++ source-file analyzer using tree-sitter.

Entity kinds extracted:
  ""        — class (default)
  "struct"  — struct_specifier
  "enum"    — enum_specifier / enum class

Handles:
  - class / struct inheritance (base_class_clause)
  - inline method definitions (function_definition in class body)
  - method declarations (field_declaration with function_declarator)
  - top-level functions
  - namespace traversal
  - #include imports + using declarations

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-cpp
"""

from __future__ import annotations

import re

try:
    from tree_sitter import Language, Parser
    import tree_sitter_cpp as _tscpp
    _CPP_LANGUAGE = Language(_tscpp.language())
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False

from .code_analyzer import (
    ArgInfo, ClassInfo, CodeAnalysis, FunctionInfo, ImportInfo, MethodInfo,
)

# ---------------------------------------------------------------------------
# Macro pre-processing
# ---------------------------------------------------------------------------
# Strip well-known attribute macros that tree-sitter-cpp cannot parse.
# These are all annotation-only — removing them preserves code structure.
#
# Pattern: visibility export macros placed INSIDE declarations, e.g.
#   class LEVELDB_EXPORT Cache {   →   class Cache {
# This pattern appears in virtually every cross-platform C++ library
# (leveldb, Qt, WebKit, WxWidgets, Chromium, etc.) and causes tree-sitter
# to fail the entire class_specifier node, yielding 0 extracted entities.
_RE_CPP_EXPORT = re.compile(r'\b[A-Z][A-Z0-9_]+_EXPORT\b')

# Clang Thread-Safety Analysis (TSA) annotations, used by leveldb, Abseil,
# Chromium, and others.  Covers both class-level qualifiers (LOCKABLE) and
# method/member-level annotations (GUARDED_BY, EXCLUSIVE_LOCKS_REQUIRED, etc.)
_RE_THREAD_ANNOT = re.compile(
    r'\b(?:GUARDED_BY|PT_GUARDED_BY|'
    r'LOCKS_EXCLUDED|LOCKS_REQUIRED|EXCLUSIVE_LOCKS_REQUIRED|SHARED_LOCKS_REQUIRED|'
    r'EXCLUSIVE_LOCK_FUNCTION|SHARED_LOCK_FUNCTION|UNLOCK_FUNCTION|'
    r'ASSERT_EXCLUSIVE_LOCK|ASSERT_SHARED_LOCK|'
    r'ACQUIRED_BEFORE|ACQUIRED_AFTER|NO_THREAD_SAFETY_ANALYSIS|'
    r'LOCKABLE|SCOPED_LOCKABLE)'
    r'(?:\s*\([^)]*\))?'
)

# Misc GCC/GLib per-parameter or per-function attribute macros
_RE_CPP_ATTRS = re.compile(r'\b(?:G_GNUC_UNUSED|ATTRIBUTE_TARGET_\w+)\b')

# Raw GCC __attribute__((...)) with up to 3 levels of paren nesting.
# Handles: __attribute__((__format__(__printf__, 2, 3)))
_RE_GNU_ATTR = re.compile(
    r'__attribute__\s*'
    r'\((?:[^()]*|\((?:[^()]*|\([^()]*\))*\))*\)'
)


def _strip_macros_cpp(content: str) -> str:
    """Remove known attribute macros before handing content to tree-sitter."""
    content = _RE_CPP_EXPORT.sub('', content)
    content = _RE_THREAD_ANNOT.sub('', content)
    content = _RE_CPP_ATTRS.sub('', content)
    content = _RE_GNU_ATTR.sub('', content)
    return content

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_CPP_SKIP_NAMESPACES: frozenset[str] = frozenset({"std", "boost", "Eigen", "cv", "llvm", "clang"})


def _t(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _ft(node, field: str, src: bytes) -> str:
    child = node.child_by_field_name(field)
    return _t(child, src) if child else ""


def _line(node) -> int:
    return node.start_point[0] + 1


def _end_line(node) -> int:
    return node.end_point[0] + 1


def _preceding_cpp_doc(node, src: bytes) -> str:
    before = src[:node.start_byte].decode("utf-8", errors="replace").rstrip()
    lines = before.split("\n")
    doc_lines = []
    for line in reversed(lines):
        line_stripped = line.strip()
        if line_stripped.startswith("///"):
            doc_lines.append(line_stripped.removeprefix("///").strip())
        elif line_stripped.startswith("//!"):
            doc_lines.append(line_stripped.removeprefix("//!").strip())
        elif line_stripped.startswith("//"):
            doc_lines.append(line_stripped.removeprefix("//").strip())
        elif not line_stripped:
            break
        elif line_stripped.startswith("/**") or line_stripped.startswith("/*!") or line_stripped.startswith("/*"):
            inner = line_stripped
            if inner.startswith("/**"):
                inner = inner.removeprefix("/**")
            elif inner.startswith("/*!"):
                inner = inner.removeprefix("/*!")
            else:
                inner = inner.removeprefix("/*")
            if inner.endswith("*/"):
                inner = inner.removesuffix("*/")
            doc_lines.append(inner.strip())
            break
        elif line_stripped.startswith("template"):
            continue
        elif line_stripped.startswith("public:") or line_stripped.startswith("private:") or line_stripped.startswith("protected:"):
            continue
        else:
            break
    if not doc_lines:
        return ""
    doc_lines.reverse()
    text = " ".join(doc_lines)
    return text[:200]


# ---------------------------------------------------------------------------
# call graph extraction
# ---------------------------------------------------------------------------


def _collect_calls_cpp(body_node, src: bytes) -> list[tuple[str, str]]:
    """Walk a C++ compound_statement body and return (callee_name, "") for each call."""
    if body_node is None:
        return []
    calls: list[tuple[str, str]] = []

    def _walk(node):
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn:
                fnt = fn.type
                if fnt == "identifier":
                    name = _t(fn, src)
                    if name and name.isidentifier():
                        calls.append((name, ""))
                elif fnt == "field_expression":
                    f = fn.child_by_field_name("field")
                    if f and f.type in ("field_identifier", "identifier"):
                        name = _t(f, src)
                        if name and name.isidentifier():
                            calls.append((name, ""))
                elif fnt == "qualified_identifier":
                    # e.g. Foo::bar or std::make_shared
                    raw = _t(fn, src)
                    parts = [p.strip() for p in raw.split("::") if p.strip()]
                    if parts and parts[0] not in _CPP_SKIP_NAMESPACES:
                        first = parts[0]
                        if first and first[0].isupper() and first.isidentifier():
                            calls.append((first, ""))
        for c in node.children:
            _walk(c)

    _walk(body_node)
    return calls


# ---------------------------------------------------------------------------
# declarator traversal
# ---------------------------------------------------------------------------


def _resolve_func_decl(node):
    """Walk pointer/reference/abstract wrappers to find function_declarator."""
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
    """Extract the function / method name from a function_declarator."""
    for c in func_decl.children:
        if c.type in ("identifier", "field_identifier",
                      "destructor_name", "operator_name",
                      "qualified_identifier"):
            return _t(c, src)
    return ""


# ---------------------------------------------------------------------------
# parameter extraction
# ---------------------------------------------------------------------------


def _find_param_name(node, src: bytes) -> str:
    """Find innermost identifier in a parameter declarator."""
    for c in reversed(node.children):
        if c.type == "identifier":
            return _t(c, src)
        if c.type in ("pointer_declarator", "reference_declarator",
                      "array_declarator", "abstract_declarator"):
            name = _find_param_name(c, src)
            if name:
                return name
    return ""


def _parse_params(param_list_node, src: bytes) -> list[str]:
    if param_list_node is None:
        return []
    names: list[str] = []
    for child in param_list_node.children:
        if child.type == "parameter_declaration":
            name = _find_param_name(child, src)
            if name and name not in ("void", "..."):
                names.append(name)
    return names


# ---------------------------------------------------------------------------
# method extraction from class / struct body
# ---------------------------------------------------------------------------


def _extract_methods(body_node, src: bytes) -> list[MethodInfo]:
    """Extract methods from a field_declaration_list (class body)."""
    methods: list[MethodInfo] = []
    if body_node is None:
        return methods

    for child in body_node.children:
        if child.type == "function_definition":
            m = _method_from_func_def(child, src)
            if m:
                methods.append(m)
        elif child.type in ("declaration", "field_declaration"):
            # Forward declaration / pure virtual: field_declaration containing
            # a function_declarator
            m = _method_from_declaration(child, src)
            if m:
                methods.append(m)

    return methods


def _method_from_func_def(node, src: bytes) -> MethodInfo | None:
    decl = node.child_by_field_name("declarator")
    func_decl = _resolve_func_decl(decl)
    if not func_decl:
        return None
    name = _func_decl_name(func_decl, src)
    if not name:
        return None
    param_list = func_decl.child_by_field_name("parameters")
    args = _parse_params(param_list, src)
    ret_node = node.child_by_field_name("type")
    return_type = _t(ret_node, src) if ret_node else ""
    is_async = False
    return MethodInfo(name=name, args=args, return_type=return_type, is_async=is_async)


def _method_from_declaration(node, src: bytes) -> MethodInfo | None:
    """Extract a method from a declaration/field_declaration (e.g. pure virtual)."""
    # Walk children to find a function_declarator
    func_decl = None
    for c in node.children:
        fd = _resolve_func_decl(c)
        if fd:
            func_decl = fd
            break
    if not func_decl:
        return None
    name = _func_decl_name(func_decl, src)
    if not name:
        return None
    param_list = func_decl.child_by_field_name("parameters")
    args = _parse_params(param_list, src)
    ret_node = node.child_by_field_name("type")
    return_type = _t(ret_node, src) if ret_node else ""
    return MethodInfo(name=name, args=args, return_type=return_type)


# ---------------------------------------------------------------------------
# base class extraction
# ---------------------------------------------------------------------------


def _extract_bases(node, src: bytes) -> list[str]:
    """Extract base class / struct names from base_class_clause."""
    bases: list[str] = []
    for c in node.children:
        if c.type == "base_class_clause":
            for b in c.children:
                if b.type == "type_identifier":
                    bases.append(_t(b, src))
    return bases


# ---------------------------------------------------------------------------
# class / struct / enum parsing
# ---------------------------------------------------------------------------


def _parse_class_or_struct(node, src: bytes, kind: str) -> ClassInfo | None:
    """Parse a class_specifier or struct_specifier."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    body = node.child_by_field_name("body")
    if body is None:
        # Forward declaration (class Foo;) — no body, skip to avoid noise.
        return None

    bases = _extract_bases(node, src)
    methods = _extract_methods(body, src)

    # Aggregate call graph from all inline method bodies
    calls: list[tuple[str, str]] = []
    for child in body.children:
        if child.type == "function_definition":
            calls.extend(_collect_calls_cpp(child.child_by_field_name("body"), src))

    return ClassInfo(
        name=name, kind=kind, bases=bases, methods=methods, class_vars=[],
        calls=calls,
        line_start=_line(node), line_end=_end_line(node),
        docstring=_preceding_cpp_doc(node, src),
    )


def _parse_enum(node, src: bytes) -> ClassInfo | None:
    """Parse an enum_specifier or enum class."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    body = node.child_by_field_name("body")
    class_vars: list[str] = []
    if body:
        for child in body.children:
            if child.type == "enumerator":
                en = child.child_by_field_name("name")
                if en:
                    class_vars.append(_t(en, src))

    return ClassInfo(
        name=name, kind="enum", bases=[], methods=[], class_vars=class_vars,
        line_start=_line(node), line_end=_end_line(node),
        docstring=_preceding_cpp_doc(node, src),
    )


# ---------------------------------------------------------------------------
# top-level function parsing
# ---------------------------------------------------------------------------


def _parse_function(node, src: bytes) -> FunctionInfo | None:
    decl = node.child_by_field_name("declarator")
    func_decl = _resolve_func_decl(decl)
    if not func_decl:
        return None
    name = _func_decl_name(func_decl, src)
    if not name:
        return None
    param_list = func_decl.child_by_field_name("parameters")
    args = _parse_params(param_list, src)
    ret_node = node.child_by_field_name("type")
    return_type = _t(ret_node, src) if ret_node else ""
    body_node = node.child_by_field_name("body")
    calls = _collect_calls_cpp(body_node, src)
    return FunctionInfo(
        name=name,
        args=[ArgInfo(name=a) for a in args],
        return_type=return_type,
        calls=calls,
        line_start=_line(node),
        line_end=_end_line(node),
        docstring=_preceding_cpp_doc(node, src),
    )


# ---------------------------------------------------------------------------
# recursive walker
# ---------------------------------------------------------------------------


def _walk_scope(node, src: bytes,
                classes: list[ClassInfo],
                functions: list[FunctionInfo],
                top_level: bool = True) -> None:
    """Recursively walk a translation unit, namespace body, or preproc block."""
    for child in node.children:
        nt = child.type
        if nt == "class_specifier":
            cls = _parse_class_or_struct(child, src, kind="")
            if cls:
                classes.append(cls)
        elif nt == "struct_specifier":
            cls = _parse_class_or_struct(child, src, kind="struct")
            if cls:
                classes.append(cls)
        elif nt == "enum_specifier":
            cls = _parse_enum(child, src)
            if cls:
                classes.append(cls)
        elif nt == "namespace_definition":
            body = child.child_by_field_name("body")
            if body:
                _walk_scope(body, src, classes, functions, top_level=False)
        elif nt == "type_definition":
            # C-style typedef struct: typedef struct Foo { ... } Bar;
            # Common in C headers that the C++ analyzer handles (.h files).
            # Collect the typedef alias (last type_identifier child) and parse
            # the struct/enum body; use the alias as the canonical entity name.
            alias = None
            for c in child.children:
                if c.type == "type_identifier":
                    alias = _t(c, src)   # last one wins = typedef alias name
            for c in child.children:
                if c.type in ("struct_specifier", "class_specifier"):
                    cls = _parse_class_or_struct(c, src, kind="struct")
                    if cls:
                        ename = alias or cls.name
                        if ename:
                            classes.append(ClassInfo(
                                name=ename, kind="struct",
                                bases=cls.bases, methods=cls.methods,
                                class_vars=cls.class_vars, calls=cls.calls,
                                line_start=cls.line_start, line_end=cls.line_end,
                                docstring=cls.docstring,
                            ))
                elif c.type == "enum_specifier":
                    cls = _parse_enum(c, src)
                    if cls:
                        ename = alias or cls.name
                        if ename:
                            classes.append(ClassInfo(
                                name=ename, kind="enum",
                                bases=[], methods=[], class_vars=cls.class_vars,
                                calls=[], line_start=cls.line_start,
                                line_end=cls.line_end, docstring=cls.docstring,
                            ))
        elif nt in ("preproc_ifdef", "preproc_ifndef", "preproc_if",
                    "preproc_else", "preproc_elif", "preproc_elifdef"):
            # Recurse into preprocessor conditional blocks.
            # This handles the extremely common #ifndef / #define header guard
            # pattern — without this, ALL header files return 0 classes.
            _walk_scope(child, src, classes, functions, top_level=top_level)
        elif nt == "function_definition" and top_level:
            fn = _parse_function(child, src)
            if fn:
                functions.append(fn)
        elif nt == "declaration":
            # May contain a class / struct specifier (e.g. forward declaration)
            for c in child.children:
                if c.type == "class_specifier":
                    cls = _parse_class_or_struct(c, src, kind="")
                    if cls:
                        classes.append(cls)
                elif c.type == "struct_specifier":
                    cls = _parse_class_or_struct(c, src, kind="struct")
                    if cls:
                        classes.append(cls)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_cpp(path: str, content: str) -> CodeAnalysis:
    """Parse a C++ source file and return a CodeAnalysis. Never raises."""
    line_count = content.count("\n") + 1

    if not _AVAILABLE:
        return CodeAnalysis(
            path=path, language="cpp", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                'tree-sitter-cpp not installed — run: '
                'pip install "tree-sitter>=0.23.0" tree-sitter-cpp'
            ],
        )

    try:
        content = _strip_macros_cpp(content)
        parser = Parser(_CPP_LANGUAGE)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        imports: list[ImportInfo] = []
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []

        # Collect imports from root-level preprocessor includes and using decls
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
            elif nt == "using_declaration":
                # using namespace std; or using std::string;
                text = _t(node, src)
                module = text.replace("using", "").replace("namespace", "").rstrip(";").strip()
                if module:
                    imports.append(ImportInfo(
                        module=module, names=[], is_from=False, is_relative=False,
                    ))

        _walk_scope(root, src, classes, functions, top_level=True)

        return CodeAnalysis(
            path=path, language="cpp", line_count=line_count,
            module_docstring="", classes=classes, functions=functions,
            imports=imports, all_exports=[], constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="cpp", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"cpp_analyzer internal error: {exc}"],
        )
