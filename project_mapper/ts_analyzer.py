"""
project_mapper/ts_analyzer.py
TypeScript / JavaScript code structure extractor using tree-sitter.

Extracts the same CodeAnalysis structure as code_analyzer.py so the
ingestor can handle TypeScript and JavaScript files uniformly.

Supports:
  .ts   — TypeScript
  .tsx  — TypeScript + JSX
  .js   — JavaScript
  .jsx  — JavaScript + JSX
  .mjs  — ES Module JavaScript

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-typescript tree-sitter-javascript
"""

from __future__ import annotations

import re
from pathlib import Path

from .code_analyzer import (
    ArgInfo, ClassInfo, CodeAnalysis, FunctionInfo, ImportInfo, MethodInfo,
)

# ---------------------------------------------------------------------------
# tree-sitter availability — soft dependency
# ---------------------------------------------------------------------------

_TREESITTER_AVAILABLE = False
_TS_LANGUAGE  = None
_TSX_LANGUAGE = None
_JS_LANGUAGE  = None

try:
    from tree_sitter import Language, Parser
    import tree_sitter_typescript as _tsts
    import tree_sitter_javascript as _tsjs

    _TS_LANGUAGE  = Language(_tsts.language_typescript())
    _TSX_LANGUAGE = Language(_tsts.language_tsx())
    _JS_LANGUAGE  = Language(_tsjs.language())
    _TREESITTER_AVAILABLE = True
except Exception:
    pass  # tree-sitter not installed — analyze_typescript() returns stubs


# ---------------------------------------------------------------------------
# JS/TS built-ins and common globals to skip in call-graph extraction
# ---------------------------------------------------------------------------

_JS_IGNORE: frozenset[str] = frozenset({
    # Built-ins
    "Array", "Object", "String", "Number", "Boolean", "Symbol", "BigInt",
    "Math", "Date", "RegExp", "Error", "Map", "Set", "WeakMap", "WeakSet",
    "Promise", "Proxy", "Reflect", "JSON", "console", "process",
    "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "fetch", "URL", "URLSearchParams", "FormData", "Headers", "Request", "Response",
    "Event", "EventTarget", "CustomEvent", "AbortController", "AbortSignal",
    "ReadableStream", "WritableStream", "TransformStream",
    "Buffer", "Uint8Array", "Int32Array", "Float64Array", "ArrayBuffer",
    "parseInt", "parseFloat", "isNaN", "isFinite", "encodeURIComponent",
    "decodeURIComponent", "encodeURI", "decodeURI",
    # React
    "React", "Component", "PureComponent", "Fragment",
    "useState", "useEffect", "useContext", "useRef", "useMemo",
    "useCallback", "useReducer", "useLayoutEffect",
    # Common framework base classes
    "Controller", "Injectable", "Module", "Guard", "Pipe", "Interceptor",
    "Exception", "HttpException", "BaseEntity",
})


# ---------------------------------------------------------------------------
# Tree-sitter node helpers
# ---------------------------------------------------------------------------

def _text(node, src: bytes) -> str:
    """Extract UTF-8 text for a node."""
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _field(node, name: str):
    """Return named field child, or None."""
    try:
        return node.child_by_field_name(name)
    except Exception:
        return None


def _first(node, *types: str):
    """Return first child matching any of the given types."""
    for child in node.children:
        if child.type in types:
            return child
    return None


def _all(node, *types: str):
    """Return all children matching any of the given types."""
    return [c for c in node.children if c.type in types]


def _line(node) -> int:
    """1-indexed start line."""
    return node.start_point[0] + 1


def _end_line(node) -> int:
    """1-indexed end line."""
    return node.end_point[0] + 1


def _preceding_jsdoc(node, src: bytes) -> str:
    """Extract a /** … */ JSDoc comment immediately before a node.

    Strips trailing JS wrapper keywords (export, default, async, declare,
    abstract) so that exported declarations find their JSDoc correctly.
    """
    before = src[:node.start_byte].decode("utf-8", errors="replace")
    # Strip keyword tokens that may appear between the JSDoc and this node
    before = re.sub(r"\s*\b(export|default|async|declare|abstract)\b\s*$", "", before.rstrip(), count=3)
    before = before.rstrip()
    if not before.endswith("*/"):
        return ""
    start = before.rfind("/**")
    if start < 0:
        return ""
    inner = before[start + 3:]       # skip leading /**
    if inner.endswith("*/"):
        inner = inner[:-2]            # strip trailing */
    lines = inner.split("\n")
    text = " ".join(l.strip().lstrip("*").strip() for l in lines if l.strip().lstrip("*").strip())
    return text[:200]


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------

def _extract_imports(root, src: bytes) -> list[ImportInfo]:
    imports: list[ImportInfo] = []

    def _walk(node):
        if node.type == "import_statement":
            _parse_import(node, src, imports)
        else:
            for child in node.children:
                _walk(child)

    _walk(root)
    return imports


def _parse_import(node, src: bytes, out: list[ImportInfo]) -> None:
    # Source string (the module path)
    source = _field(node, "source") or _first(node, "string")
    if not source:
        return
    module_path = _text(source, src).strip("\"'`")
    is_relative = module_path.startswith(".")
    level = len(module_path) - len(module_path.lstrip("."))

    clause = _first(node, "import_clause")
    if not clause:
        out.append(ImportInfo(module=module_path, names=[], is_from=True,
                              is_relative=is_relative, level=level))
        return

    names: list[str] = []
    for child in clause.children:
        if child.type == "identifier":
            names.append(_text(child, src))
        elif child.type == "named_imports":
            for spec in _all(child, "import_specifier"):
                name_node = _field(spec, "name") or _first(spec, "identifier")
                if name_node:
                    names.append(_text(name_node, src))
        elif child.type == "namespace_import":
            id_node = _first(child, "identifier")
            if id_node:
                names.append(f"* as {_text(id_node, src)}")

    out.append(ImportInfo(module=module_path, names=names, is_from=True,
                          is_relative=is_relative, level=level))


# ---------------------------------------------------------------------------
# Class extraction
# ---------------------------------------------------------------------------

_CLASS_TYPES = {"class_declaration", "abstract_class_declaration"}


def _extract_classes(root, src: bytes) -> list[ClassInfo]:
    classes: list[ClassInfo] = []

    def _walk(node, in_class: bool = False):
        ntype = node.type

        if ntype == "export_statement":
            for child in node.children:
                if child.type in _CLASS_TYPES:
                    _parse_class(child, src, classes, is_abstract="abstract" in _text(child, src)[:10])
                else:
                    _walk(child, in_class)
            return

        if ntype in _CLASS_TYPES and not in_class:
            _parse_class(node, src, classes, is_abstract=ntype == "abstract_class_declaration")
            return

        for child in node.children:
            _walk(child, in_class or ntype in _CLASS_TYPES)

    _walk(root)
    return classes


def _parse_class(node, src: bytes, out: list[ClassInfo], is_abstract: bool = False) -> None:
    name_node = _field(node, "name") or _first(node, "type_identifier", "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    # Bases (extends)
    bases: list[str] = []
    heritage = _first(node, "class_heritage")
    if heritage:
        ext_clause = _first(heritage, "extends_clause")
        if ext_clause:
            for child in ext_clause.children:
                if child.type in ("identifier", "type_identifier", "member_expression"):
                    bases.append(_text(child, src).split("<")[0])  # strip generics

    # Body
    body = _field(node, "body") or _first(node, "class_body")
    methods: list[MethodInfo] = []
    class_vars: list[str] = []

    if body:
        for child in body.children:
            if child.type == "method_definition":
                m = _parse_method(child, src)
                if m:
                    methods.append(m)
            elif child.type in ("public_field_definition", "field_definition"):
                fname_node = (_field(child, "name")
                              or _first(child, "property_identifier", "identifier"))
                if fname_node:
                    fname = _text(fname_node, src)
                    if re.match(r"^[A-Z][A-Z0-9_]*$", fname):
                        class_vars.append(fname)

    # Call graph — new_expression nodes inside the class body
    calls = _extract_class_calls(body, src, name) if body else []

    out.append(ClassInfo(
        name=name,
        bases=bases,
        methods=methods,
        class_vars=class_vars,
        decorators=[],
        docstring=_preceding_jsdoc(node, src),
        line_start=_line(node),
        line_end=_end_line(node),
        calls=calls,
        kind="abstract" if is_abstract else "",
    ))


def _parse_method(node, src: bytes):
    name_node = (_field(node, "name")
                 or _first(node, "property_identifier", "identifier",
                            "private_property_identifier"))
    if not name_node:
        return None
    name = _text(name_node, src)

    is_async  = any(c.type == "async" for c in node.children)
    is_static = any(c.type == "static" for c in node.children)
    is_getter = any(c.type == "get" for c in node.children)
    is_setter = any(c.type == "set" for c in node.children)

    params_node = _field(node, "parameters") or _first(node, "formal_parameters")
    args = _parse_params(params_node, src) if params_node else []

    ret_node = _field(node, "return_type")
    return_type = ""
    if ret_node:
        inner = _first(ret_node, "type_identifier", "predefined_type",
                       "union_type", "array_type", "generic_type", "void_type")
        return_type = _text(inner, src) if inner else _text(ret_node, src).lstrip(":").strip()

    return MethodInfo(
        name=name,
        args=args,
        return_type=return_type,
        decorators=[],
        is_async=is_async,
        is_property=(is_getter or is_setter),
        is_classmethod=is_static,
        is_staticmethod=is_static,
    )


def _parse_params(params_node, src: bytes) -> list[str]:
    """Return a flat list of parameter name strings."""
    args: list[str] = []
    for child in params_node.children:
        if child.type == "identifier":
            args.append(_text(child, src))
        elif child.type in ("required_parameter", "optional_parameter",
                            "rest_parameter", "assignment_pattern"):
            name_node = _first(child, "identifier", "object_pattern", "array_pattern")
            if name_node:
                suffix = "?" if child.type == "optional_parameter" else ""
                args.append(_text(name_node, src) + suffix)
    return args


def _extract_class_calls(body, src: bytes, own_name: str) -> list[tuple[str, str]]:
    """Extract new_expression and uppercase-function calls from a class body."""
    results: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _scan(node, method_name: str = ""):
        for child in node.children:
            if child.type == "method_definition":
                mname_node = _field(child, "name") or _first(child, "property_identifier", "identifier")
                mname = _text(mname_node, src) if mname_node else ""
                _scan(child, mname)
                continue

            if child.type == "new_expression":
                callee = _first(child, "identifier", "member_expression")
                if callee:
                    cname = _text(callee, src).split(".")[0]
                    if (cname and cname[0].isupper() and cname not in _JS_IGNORE
                            and cname != own_name):
                        pair = (cname, method_name)
                        if pair not in seen:
                            seen.add(pair)
                            results.append(pair)

            elif child.type == "call_expression":
                func = _field(child, "function") or _first(child, "identifier", "member_expression")
                if func and func.type == "identifier":
                    cname = _text(func, src)
                    if (cname and cname[0].isupper() and cname not in _JS_IGNORE
                            and cname != own_name):
                        pair = (cname, method_name)
                        if pair not in seen:
                            seen.add(pair)
                            results.append(pair)
                elif func and func.type == "member_expression":
                    cname = _text(func, src).split(".")[0]
                    if (cname and cname[0].isupper() and cname not in _JS_IGNORE
                            and cname != own_name):
                        pair = (cname, method_name)
                        if pair not in seen:
                            seen.add(pair)
                            results.append(pair)

            _scan(child, method_name)

    _scan(body)
    return results


# ---------------------------------------------------------------------------
# Interface extraction (TypeScript only)
# ---------------------------------------------------------------------------

def _extract_interfaces(root, src: bytes) -> list[ClassInfo]:
    interfaces: list[ClassInfo] = []

    def _walk(node):
        if node.type == "interface_declaration":
            _parse_interface(node, src, interfaces)
            return
        if node.type == "export_statement":
            for child in node.children:
                if child.type == "interface_declaration":
                    _parse_interface(child, src, interfaces)
                else:
                    _walk(child)
            return
        for child in node.children:
            _walk(child)

    _walk(root)
    return interfaces


def _parse_interface(node, src: bytes, out: list[ClassInfo]) -> None:
    name_node = _field(node, "name") or _first(node, "type_identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    bases: list[str] = []
    ext_clause = _first(node, "extends_type_clause")
    if ext_clause:
        for child in ext_clause.children:
            if child.type in ("type_identifier", "generic_type"):
                bases.append(_text(child, src).split("<")[0])

    body = _first(node, "interface_body")
    methods: list[MethodInfo] = []
    if body:
        for child in body.children:
            if child.type in ("method_signature", "call_signature"):
                n = _field(child, "name") or _first(child, "property_identifier", "identifier")
                if n:
                    params_node = (_field(child, "parameters")
                                   or _first(child, "formal_parameters"))
                    args = _parse_params(params_node, src) if params_node else []
                    is_async = any(c.type == "async" for c in child.children)
                    methods.append(MethodInfo(name=_text(n, src), args=args,
                                              is_async=is_async))
            elif child.type == "property_signature":
                # Interface properties (not methods) — record as class vars equivalent
                pass

    out.append(ClassInfo(
        name=name,
        bases=bases,
        methods=methods,
        class_vars=[],
        decorators=[],
        docstring=_preceding_jsdoc(node, src),
        line_start=_line(node),
        line_end=_end_line(node),
        calls=[],
        kind="interface",
    ))


# ---------------------------------------------------------------------------
# Function extraction
# ---------------------------------------------------------------------------

_FUNC_DECL_TYPES = {"function_declaration", "generator_function_declaration"}


def _extract_functions(root, src: bytes) -> list[FunctionInfo]:
    functions: list[FunctionInfo] = []

    def _walk(node):
        ntype = node.type

        if ntype == "export_statement":
            for child in node.children:
                if child.type in _FUNC_DECL_TYPES:
                    _parse_named_function(child, src, functions)
                elif child.type == "lexical_declaration":
                    _parse_arrow_declarations(child, src, functions)
                else:
                    _walk(child)
            return

        if ntype in _FUNC_DECL_TYPES:
            _parse_named_function(node, src, functions)
            return

        if ntype == "lexical_declaration":
            _parse_arrow_declarations(node, src, functions)
            return

        # Don't recurse into class bodies
        if ntype not in _CLASS_TYPES:
            for child in node.children:
                _walk(child)

    _walk(root)
    return functions


def _parse_named_function(node, src: bytes, out: list[FunctionInfo]) -> None:
    name_node = _field(node, "name") or _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)
    if name.startswith("_"):
        return

    is_async = any(c.type == "async" for c in node.children)
    params_node = _field(node, "parameters") or _first(node, "formal_parameters")
    args = [ArgInfo(name=p) for p in (_parse_params(params_node, src) if params_node else [])]

    ret_node = _field(node, "return_type")
    return_type = _text(ret_node, src).lstrip(":").strip() if ret_node else ""

    out.append(FunctionInfo(
        name=name, args=args, return_type=return_type, decorators=[],
        docstring=_preceding_jsdoc(node, src), is_async=is_async,
        line_start=_line(node), line_end=_end_line(node),
        calls=_extract_function_calls(node, src, name),
    ))


def _parse_arrow_declarations(node, src: bytes, out: list[FunctionInfo]) -> None:
    """Parse top-level: const foo = (...) => {} or const foo = async function() {}"""
    # JSDoc lives before the const/let declaration (node), not the declarator
    jsdoc = _preceding_jsdoc(node, src)
    for decl in _all(node, "variable_declarator"):
        name_node = _field(decl, "name") or _first(decl, "identifier")
        value_node = _field(decl, "value")
        if not name_node or not value_node:
            continue
        if value_node.type not in ("arrow_function", "function_expression",
                                   "generator_function"):
            continue
        name = _text(name_node, src)
        if name.startswith("_"):
            continue

        is_async = any(c.type == "async" for c in value_node.children)
        params_node = (_field(value_node, "parameters")
                       or _first(value_node, "formal_parameters"))
        if params_node:
            args = [ArgInfo(name=p) for p in _parse_params(params_node, src)]
        else:
            # Single bare param arrow: const fn = x => ...
            single = _first(value_node, "identifier")
            args = [ArgInfo(name=_text(single, src))] if single else []

        ret_node = _field(value_node, "return_type")
        return_type = _text(ret_node, src).lstrip(":").strip() if ret_node else ""

        out.append(FunctionInfo(
            name=name, args=args, return_type=return_type, decorators=[],
            docstring=jsdoc, is_async=is_async,
            line_start=_line(decl), line_end=_end_line(decl),
            calls=_extract_function_calls(value_node, src, name),
        ))


def _extract_function_calls(node, src: bytes, fn_name: str) -> list[tuple[str, str]]:
    """Extract new X() and UppercaseFn() calls from a function body."""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _scan(n):
        if n.type == "new_expression":
            callee = _first(n, "identifier", "member_expression")
            if callee:
                cname = _text(callee, src).split(".")[0]
                if cname and cname[0].isupper() and cname not in _JS_IGNORE and cname not in seen:
                    seen.add(cname)
                    results.append((cname, fn_name))
        elif n.type == "call_expression":
            func = _field(n, "function") or _first(n, "identifier", "member_expression")
            if func and func.type == "identifier":
                cname = _text(func, src)
                if (cname and cname[0].isupper() and cname not in _JS_IGNORE
                        and cname not in seen):
                    seen.add(cname)
                    results.append((cname, fn_name))
            elif func and func.type == "member_expression":
                cname = _text(func, src).split(".")[0]
                if (cname and cname[0].isupper() and cname not in _JS_IGNORE
                        and cname not in seen):
                    seen.add(cname)
                    results.append((cname, fn_name))
        for child in n.children:
            _scan(child)

    _scan(node)
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_EXT_TO_LANG = {
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
}


def _pick_language(ext: str, declared: str):
    """Return the tree-sitter Language object for the given extension."""
    if ext in (".tsx",):
        return _TSX_LANGUAGE
    if ext in (".ts",):
        return _TS_LANGUAGE
    return _JS_LANGUAGE


def analyze_typescript(path: str, content: str, language: str = "") -> CodeAnalysis:
    """
    Parse a TypeScript or JavaScript file and return a CodeAnalysis.
    Falls back to a stub with an explanatory parse_error if tree-sitter
    is not installed.  Never raises.
    """
    ext = Path(path).suffix.lower()
    lang_name = language or _EXT_TO_LANG.get(ext, "javascript")
    line_count = content.count("\n") + 1

    if not _TREESITTER_AVAILABLE:
        return CodeAnalysis(
            path=path, language=lang_name, line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                "tree-sitter not installed — run: "
                "pip install \"tree-sitter>=0.23.0\" "
                "tree-sitter-typescript tree-sitter-javascript"
            ],
        )

    ts_lang = _pick_language(ext, lang_name)
    if ts_lang is None:
        ts_lang = _JS_LANGUAGE

    try:
        parser = Parser(ts_lang)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        imports    = _extract_imports(root, src)
        classes    = _extract_classes(root, src)
        interfaces = _extract_interfaces(root, src) if lang_name == "typescript" else []
        functions  = _extract_functions(root, src)

        return CodeAnalysis(
            path=path,
            language=lang_name,
            line_count=line_count,
            module_docstring="",
            classes=classes + interfaces,
            functions=functions,
            imports=imports,
            all_exports=[],
            constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language=lang_name, line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"AnalysisError: {exc}"],
        )
