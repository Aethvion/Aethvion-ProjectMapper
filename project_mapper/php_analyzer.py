"""
core/project_mapper/php_analyzer.py
PHP source-file analyzer using tree-sitter.

Entity kinds extracted:
  ""          — regular class
  "abstract"  — abstract class
  "interface" — interface
  "enum"      — PHP 8.1+ backed enum
  "trait"     — trait

Handles:
  - class / abstract class / interface / enum / trait declarations
  - methods with visibility, static, abstract modifiers
  - inheritance (extends) and interfaces (implements)
  - namespace and use-statement imports
  - PHP enum cases as class_vars

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-php
"""

from __future__ import annotations

try:
    from tree_sitter import Language, Parser
    import tree_sitter_php as _tsphp
    _PHP_LANGUAGE = Language(_tsphp.language_php())
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


def _first_child(node, *types):
    for c in node.children:
        if c.type in types:
            return c
    return None


# ---------------------------------------------------------------------------
# modifier detection
# ---------------------------------------------------------------------------


def _has_modifier(node, mod_type: str) -> bool:
    """Check if a class/method node has a specific modifier child."""
    for c in node.children:
        if c.type == mod_type:
            return True
        # modifiers may be grouped in a 'modifier' node
        if c.type == "modifier" and _t(c, src=b"").startswith(mod_type):
            return True
    return False


def _class_kind(node, src: bytes) -> str:
    """Determine ClassInfo.kind from a PHP class node."""
    for c in node.children:
        if c.type == "abstract_modifier":
            return "abstract"
        if c.type == "final_modifier":
            return ""  # sealed class — treat as regular
    return ""


# ---------------------------------------------------------------------------
# parameter parsing
# ---------------------------------------------------------------------------


def _parse_php_params(params_node, src: bytes) -> list[str]:
    """Extract param names from formal_parameters; strips leading $."""
    if params_node is None:
        return []
    args: list[str] = []
    for child in params_node.children:
        if child.type in ("simple_parameter", "variadic_parameter",
                          "property_promotion_parameter"):
            name_node = child.child_by_field_name("name")
            if name_node:
                raw = _t(name_node, src)
                args.append(raw.lstrip("$"))
    return args


# ---------------------------------------------------------------------------
# method parsing
# ---------------------------------------------------------------------------


def _parse_method(node, src: bytes) -> MethodInfo | None:
    """Parse a method_declaration node."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    params_node = node.child_by_field_name("parameters")
    args = _parse_php_params(params_node, src)

    ret_node = node.child_by_field_name("return_type")
    return_type = _t(ret_node, src).lstrip(": ") if ret_node else ""

    is_static = any(c.type == "static_modifier" for c in node.children)
    is_async = False  # PHP has no async

    return MethodInfo(
        name=name, args=args, return_type=return_type,
        is_async=is_async, is_staticmethod=is_static,
    )


# ---------------------------------------------------------------------------
# class / interface / enum / trait parsing
# ---------------------------------------------------------------------------


def _parse_class(node, src: bytes, kind_override: str = "") -> ClassInfo | None:
    """Parse a class_declaration, interface_declaration, enum_declaration, or trait_declaration."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    # Determine kind
    if kind_override:
        kind = kind_override
    else:
        kind = _class_kind(node, src)

    # Bases: base_clause (extends) and class_interface_clause (implements)
    bases: list[str] = []
    for c in node.children:
        if c.type == "base_clause":
            for b in c.children:
                if b.type in ("named_type", "qualified_name", "name"):
                    bases.append(_t(b, src))
        elif c.type == "class_interface_clause":
            for b in c.children:
                if b.type == "name_list":
                    for n in b.children:
                        if n.type in ("named_type", "qualified_name", "name"):
                            bases.append(_t(n, src))
                elif b.type in ("named_type", "qualified_name", "name"):
                    bases.append(_t(b, src))

    # Body
    body = node.child_by_field_name("body")
    methods: list[MethodInfo] = []
    class_vars: list[str] = []

    if body:
        for child in body.children:
            if child.type == "method_declaration":
                m = _parse_method(child, src)
                if m:
                    methods.append(m)
            elif child.type == "enum_case":
                # PHP enum case
                cn = child.child_by_field_name("name")
                if cn:
                    class_vars.append(_t(cn, src))
            elif child.type in ("property_declaration",):
                # PHP class property — not extracted for now
                pass

    return ClassInfo(
        name=name, kind=kind, bases=bases, methods=methods, class_vars=class_vars,
        line_start=_line(node), line_end=_end_line(node),
    )


# ---------------------------------------------------------------------------
# top-level functions
# ---------------------------------------------------------------------------


def _parse_function(node, src: bytes) -> FunctionInfo | None:
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    params_node = node.child_by_field_name("parameters")
    args = _parse_php_params(params_node, src)

    ret_node = node.child_by_field_name("return_type")
    return_type = _t(ret_node, src).lstrip(": ") if ret_node else ""

    return FunctionInfo(
        name=name,
        args=[ArgInfo(name=a) for a in args],
        return_type=return_type,
        line_start=_line(node),
        line_end=_end_line(node),
    )


# ---------------------------------------------------------------------------
# import / namespace parsing
# ---------------------------------------------------------------------------


def _parse_namespace(node, src: bytes) -> str:
    """Extract namespace name from namespace_definition."""
    name_node = node.child_by_field_name("name")
    return _t(name_node, src) if name_node else ""


def _parse_use(node, src: bytes) -> ImportInfo | None:
    """Parse a namespace_use_declaration (use App\\Models\\User;)."""
    # Collect all qualified_name / name children
    parts: list[str] = []
    for c in node.children:
        if c.type in ("qualified_name", "name", "namespace_use_clause"):
            text = _t(c, src)
            # strip leading backslash
            parts.append(text.lstrip("\\"))

    if not parts:
        return None

    module = parts[0]
    symbol = module.split("\\")[-1]
    return ImportInfo(
        module=module.replace("\\", "."),
        names=[symbol],
        is_from=False,
        is_relative=False,
    )


# ---------------------------------------------------------------------------
# recursive body walker (handles nested/multi-level namespaces)
# ---------------------------------------------------------------------------


def _walk_body(node, src: bytes, classes, functions, namespace: str = "") -> None:
    for child in node.children:
        nt = child.type
        if nt == "class_declaration":
            cls = _parse_class(child, src)
            if cls:
                classes.append(cls)
        elif nt == "interface_declaration":
            cls = _parse_class(child, src, kind_override="interface")
            if cls:
                classes.append(cls)
        elif nt == "enum_declaration":
            cls = _parse_class(child, src, kind_override="enum")
            if cls:
                classes.append(cls)
        elif nt == "trait_declaration":
            cls = _parse_class(child, src, kind_override="trait")
            if cls:
                classes.append(cls)
        elif nt == "function_definition":
            fn = _parse_function(child, src)
            if fn:
                functions.append(fn)
        elif nt == "namespace_definition":
            body = child.child_by_field_name("body")
            if body:
                _walk_body(body, src, classes, functions)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_php(path: str, content: str) -> CodeAnalysis:
    """Parse a PHP source file and return a CodeAnalysis. Never raises."""
    line_count = content.count("\n") + 1

    if not _AVAILABLE:
        return CodeAnalysis(
            path=path, language="php", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                'tree-sitter-php not installed — run: '
                'pip install "tree-sitter>=0.23.0" tree-sitter-php'
            ],
        )

    try:
        parser = Parser(_PHP_LANGUAGE)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        imports: list[ImportInfo] = []
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []
        namespace = ""

        # Walk the program node (tree root for PHP is `program`)
        program = root
        for node in program.children:
            nt = node.type
            if nt == "namespace_definition":
                ns_name = _parse_namespace(node, src)
                if ns_name:
                    namespace = ns_name
                body = node.child_by_field_name("body")
                if body:
                    _walk_body(body, src, classes, functions, namespace)
                else:
                    # file-scoped namespace (no braces) — rest of file is the body
                    pass
            elif nt == "namespace_use_declaration":
                imp = _parse_use(node, src)
                if imp:
                    imports.append(imp)

        # Walk top-level (outside any namespace)
        _walk_body(program, src, classes, functions, namespace)

        return CodeAnalysis(
            path=path, language="php", line_count=line_count,
            module_docstring=namespace, classes=classes, functions=functions,
            imports=imports, all_exports=[], constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="php", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"php_analyzer internal error: {exc}"],
        )
