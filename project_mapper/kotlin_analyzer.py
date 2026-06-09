"""
core/project_mapper/kotlin_analyzer.py
Kotlin source-file analyzer using tree-sitter.

Entity kinds extracted:
  ""           — regular class
  "abstract"   — abstract class
  "data"       — data class
  "enum"       — enum class
  "interface"  — interface
  "object"     — Kotlin object declaration (singleton)
  "companion"  — companion object

Handles:
  - class / interface / data class / enum class / object / companion object
  - primary constructor parameters as class_vars
  - delegation specifiers (bases/interfaces)
  - function declarations (methods + top-level)
  - import directives

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-kotlin
"""

from __future__ import annotations

try:
    from tree_sitter import Language, Parser
    import tree_sitter_kotlin as _tskotlin
    _KOTLIN_LANGUAGE = Language(_tskotlin.language())
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
# kind detection
# ---------------------------------------------------------------------------


def _kotlin_class_kind(node, src: bytes) -> str:
    """Determine ClassInfo.kind from a class_declaration or object_declaration."""
    if node.type == "object_declaration":
        return "object"

    has_interface = False
    has_abstract = False
    has_data = False
    has_enum = False

    for c in node.children:
        ct = c.type
        raw = _t(c, src)
        if ct == "interface":
            has_interface = True
        elif ct == "modifiers":
            for m in c.children:
                mt = m.type
                mr = _t(m, src)
                if mt == "abstract_modifier" or mr == "abstract":
                    has_abstract = True
                elif mt == "data_modifier" or mr == "data":
                    has_data = True
                elif mr == "enum":
                    has_enum = True

    if has_interface:
        return "interface"
    if has_enum:
        return "enum"
    if has_abstract:
        return "abstract"
    if has_data:
        return "data"
    return ""


# ---------------------------------------------------------------------------
# parameter parsing
# ---------------------------------------------------------------------------


def _parse_kotlin_params(params_node, src: bytes) -> list[str]:
    """Extract names from function_value_parameters."""
    if params_node is None:
        return []
    names: list[str] = []
    for child in params_node.children:
        if child.type == "function_value_parameter":
            # parameter child has `name` field
            param_node = _first_child(child, "parameter")
            if param_node:
                name_node = param_node.child_by_field_name("name")
                if name_node:
                    names.append(_t(name_node, src))
    return names


def _parse_constructor_params(ctor_node, src: bytes) -> list[str]:
    """Extract parameter names from primary_constructor."""
    if ctor_node is None:
        return []
    names: list[str] = []
    # primary_constructor → class_parameters → class_parameter*
    for child in ctor_node.children:
        if child.type == "class_parameters":
            for param in child.children:
                if param.type == "class_parameter":
                    # identifier child for the name
                    for c in param.children:
                        if c.type == "simple_identifier":
                            names.append(_t(c, src))
                            break
    return names


def _first_child(node, *types):
    for c in node.children:
        if c.type in types:
            return c
    return None


# ---------------------------------------------------------------------------
# method parsing
# ---------------------------------------------------------------------------


def _parse_function_decl(node, src: bytes) -> MethodInfo | None:
    """Parse a function_declaration node."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    # Check for suspend modifier (async equivalent)
    is_async = False
    for c in node.children:
        if c.type == "modifiers":
            for m in c.children:
                if _t(m, src) == "suspend":
                    is_async = True

    params_node = node.child_by_field_name("function_value_parameters")
    args = _parse_kotlin_params(params_node, src)

    ret_node = node.child_by_field_name("type")
    return_type = _t(ret_node, src) if ret_node else ""

    return MethodInfo(name=name, args=args, return_type=return_type, is_async=is_async)


# ---------------------------------------------------------------------------
# bases (delegation specifiers)
# ---------------------------------------------------------------------------


def _kotlin_bases(node, src: bytes) -> list[str]:
    """Extract base class / interface names from delegation_specifiers."""
    bases: list[str] = []
    for c in node.children:
        if c.type == "delegation_specifiers":
            for spec in c.children:
                if spec.type in ("delegation_specifier", "constructor_delegation_call"):
                    for t in spec.children:
                        if t.type in ("simple_identifier", "user_type"):
                            bases.append(_t(t, src))
                            break
                elif spec.type == "simple_identifier":
                    bases.append(_t(spec, src))
    return bases


# ---------------------------------------------------------------------------
# class body parsing
# ---------------------------------------------------------------------------


def _parse_class_body(body_node, src: bytes) -> tuple[list[MethodInfo], list[str]]:
    """Extract methods and class_vars from a class_body or enum_class_body."""
    methods: list[MethodInfo] = []
    class_vars: list[str] = []

    if body_node is None:
        return methods, class_vars

    for child in body_node.children:
        nt = child.type
        if nt == "function_declaration":
            m = _parse_function_decl(child, src)
            if m:
                methods.append(m)
        elif nt in ("class_declaration", "object_declaration"):
            # Nested class / companion object — skip for now (avoid recursion depth)
            pass
        elif nt == "enum_entry":
            name_node = child.child_by_field_name("name")
            if name_node:
                class_vars.append(_t(name_node, src))

    return methods, class_vars


# ---------------------------------------------------------------------------
# class / object parsing
# ---------------------------------------------------------------------------


def _parse_class(node, src: bytes) -> ClassInfo | None:
    """Parse a class_declaration or object_declaration."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    kind = _kotlin_class_kind(node, src)
    bases = _kotlin_bases(node, src)

    # Primary constructor parameters → class_vars
    ctor = _first_child(node, "primary_constructor")
    ctor_params = _parse_constructor_params(ctor, src) if ctor else []

    body = _first_child(node, "class_body", "enum_class_body")
    methods, enum_vars = _parse_class_body(body, src)

    class_vars = ctor_params + enum_vars

    return ClassInfo(
        name=name, kind=kind, bases=bases, methods=methods, class_vars=class_vars,
        line_start=_line(node), line_end=_end_line(node),
    )


# ---------------------------------------------------------------------------
# import parsing
# ---------------------------------------------------------------------------


def _parse_import(node, src: bytes) -> ImportInfo | None:
    """Parse an `import` node (Kotlin import_header)."""
    # `import` node has a `qualified_identifier` child
    qi = None
    for c in node.children:
        if c.type == "qualified_identifier":
            qi = c
            break
    if qi is None:
        # fallback: read full text
        text = _t(node, src)
        module = text.removeprefix("import").strip()
    else:
        module = _t(qi, src)

    # Check for trailing wildcard (star is a sibling of qualified_identifier)
    is_star = any(c.type == "*" for c in node.children)
    parts = module.split(".")
    symbol = parts[-1] if parts else module

    return ImportInfo(
        module=".".join(parts[:-1]) if len(parts) > 1 else module,
        names=[] if is_star else [symbol],
        is_from=True,
        is_relative=False,
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
        if nt in ("class_declaration", "object_declaration"):
            cls = _parse_class(child, src)
            if cls:
                classes.append(cls)
        elif nt == "function_declaration":
            m = _parse_function_decl(child, src)
            if m:
                functions.append(FunctionInfo(
                    name=m.name,
                    args=[ArgInfo(name=a) for a in m.args],
                    return_type=m.return_type,
                    is_async=m.is_async,
                    line_start=_line(child),
                    line_end=_end_line(child),
                ))
        elif nt == "import":
            imp = _parse_import(child, src)
            if imp:
                imports.append(imp)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_kotlin(path: str, content: str) -> CodeAnalysis:
    """Parse a Kotlin source file and return a CodeAnalysis. Never raises."""
    line_count = content.count("\n") + 1

    if not _AVAILABLE:
        return CodeAnalysis(
            path=path, language="kotlin", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                'tree-sitter-kotlin not installed — run: '
                'pip install "tree-sitter>=0.23.0" tree-sitter-kotlin'
            ],
        )

    try:
        parser = Parser(_KOTLIN_LANGUAGE)
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
            path=path, language="kotlin", line_count=line_count,
            module_docstring="", classes=classes, functions=functions,
            imports=imports, all_exports=[], constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="kotlin", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"kotlin_analyzer internal error: {exc}"],
        )
