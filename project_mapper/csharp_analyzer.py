"""
project_mapper/csharp_analyzer.py
C# code structure extractor using tree-sitter.

Extracts the same CodeAnalysis structure as code_analyzer.py so the
ingestor can handle C# files uniformly.

Supports:
  .cs — C# source files (including C# 8–12 features)

Entity kinds:
  ""           — regular class
  "abstract"   — abstract class
  "static"     — static utility / extension class
  "sealed"     — sealed class
  "interface"  — interface
  "struct"     — value-type struct
  "enum"       — enumeration
  "record"     — C# 9+ positional record class
  "record struct" — C# 10+ positional record struct
  "delegate"   — delegate type

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-c-sharp
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
_CS_LANGUAGE = None

try:
    from tree_sitter import Language, Parser
    import tree_sitter_c_sharp as _tscs

    _CS_LANGUAGE = Language(_tscs.language())
    _TREESITTER_AVAILABLE = True
except Exception:
    pass


# ---------------------------------------------------------------------------
# C# standard-library types to skip in call graphs
# ---------------------------------------------------------------------------

_CS_IGNORE: frozenset[str] = frozenset({
    # System
    "Object", "String", "Int32", "Int64", "Double", "Boolean", "Char",
    "Byte", "Decimal", "DateTime", "DateTimeOffset", "TimeSpan", "Guid",
    "Array", "List", "Dictionary", "HashSet", "Queue", "Stack",
    "IEnumerable", "IList", "ICollection", "IReadOnlyList", "IReadOnlyCollection",
    "IReadOnlyDictionary", "IDictionary", "ISet",
    "Task", "ValueTask", "CancellationToken", "CancellationTokenSource",
    "Exception", "InvalidOperationException", "ArgumentException",
    "ArgumentNullException", "ArgumentOutOfRangeException",
    "NotImplementedException", "NotSupportedException",
    "StringBuilder", "Stream", "MemoryStream", "StreamReader", "StreamWriter",
    "Nullable", "Lazy", "Tuple", "ValueTuple",
    # ASP.NET Core common base types
    "Controller", "ControllerBase", "PageModel", "Hub", "BackgroundService",
    "Middleware", "FilterAttribute",
    # Microsoft.Extensions
    "ILogger", "IConfiguration", "IServiceCollection", "IServiceProvider",
    "IOptions", "IHostedService",
})


# ---------------------------------------------------------------------------
# Tree-sitter node helpers
# ---------------------------------------------------------------------------

def _text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _first(node, *types: str):
    for child in node.children:
        if child.type in types:
            return child
    return None


def _all(node, *types: str):
    return [c for c in node.children if c.type in types]


def _line(node) -> int:
    return node.start_point[0] + 1


def _end_line(node) -> int:
    return node.end_point[0] + 1


def _has_modifier(node, *keywords: str) -> bool:
    """Return True if any keyword appears as a modifier child."""
    for child in node.children:
        if child.type == "modifier":
            for kw in child.children:
                if kw.type in keywords:
                    return True
    return False


def _collect_modifiers(node) -> set[str]:
    """Return the set of modifier keywords on this declaration."""
    mods: set[str] = set()
    for child in node.children:
        if child.type == "modifier":
            for kw in child.children:
                mods.add(kw.type)
    return mods


def _collect_attributes(node, src: bytes) -> list[str]:
    """Extract attribute names (e.g. Obsolete, HttpGet, Authorize)."""
    attrs: list[str] = []
    for child in node.children:
        if child.type == "attribute_list":
            for attr in _all(child, "attribute"):
                name_node = _first(attr, "identifier", "qualified_name")
                if name_node:
                    attrs.append(_text(name_node, src).split(".")[-1])
    return attrs


# ---------------------------------------------------------------------------
# Type name helpers
# ---------------------------------------------------------------------------

_RETURN_TYPE_NODES = {
    "predefined_type", "identifier", "generic_name", "qualified_name",
    "nullable_type", "array_type", "tuple_type", "void_keyword",
}


def _type_text(node, src: bytes) -> str:
    """Get a readable type string, stripping generics for base names."""
    if node is None:
        return ""
    t = node.type
    if t == "generic_name":
        id_node = _first(node, "identifier")
        return _text(id_node, src) if id_node else _text(node, src)
    if t == "nullable_type":
        inner = node.children[0] if node.children else None
        return (_type_text(inner, src) + "?") if inner else "?"
    if t == "qualified_name":
        return _text(node, src)
    return _text(node, src)


def _base_list_names(node, src: bytes) -> list[str]:
    """Extract all names from a base_list (: BaseClass, IFace1, IFace2)."""
    if node is None:
        return []
    names: list[str] = []
    for child in node.children:
        if child.type in ("identifier", "generic_name", "qualified_name"):
            names.append(_type_text(child, src))
    return names


# ---------------------------------------------------------------------------
# Namespace extraction
# ---------------------------------------------------------------------------

def _extract_namespace(root, src: bytes) -> str:
    """Return the namespace name (file-scoped or block-style)."""
    for child in root.children:
        if child.type in ("file_scoped_namespace_declaration", "namespace_declaration"):
            name_node = _first(child, "qualified_name", "identifier")
            if name_node:
                return _text(name_node, src)
    return ""


# ---------------------------------------------------------------------------
# Import (using directive) extraction
# ---------------------------------------------------------------------------

def _extract_imports(root, src: bytes) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for child in root.children:
        if child.type == "using_directive":
            _parse_using(child, src, imports)
    # Also inside namespace blocks
    for child in root.children:
        if child.type == "namespace_declaration":
            body = _first(child, "declaration_list")
            if body:
                for sub in body.children:
                    if sub.type == "using_directive":
                        _parse_using(sub, src, imports)
    return imports


def _parse_using(node, src: bytes, out: list[ImportInfo]) -> None:
    is_static = any(c.type == "static" for c in node.children)
    name_node = _first(node, "qualified_name", "identifier", "generic_name")
    if not name_node:
        return
    full = _text(name_node, src)
    parts = full.split(".")
    module = ".".join(parts[:-1]) if len(parts) > 1 else full
    name = parts[-1] if parts else full
    out.append(ImportInfo(
        module=module, names=[name], is_from=True,
        is_relative=False, level=0,
    ))


# ---------------------------------------------------------------------------
# Type declaration extraction
# ---------------------------------------------------------------------------

_TYPE_DECL_TYPES = {
    "class_declaration", "interface_declaration", "struct_declaration",
    "enum_declaration", "record_declaration", "delegate_declaration",
}


def _extract_type_declarations(root, src: bytes) -> list[ClassInfo]:
    classes: list[ClassInfo] = []
    _walk_decls(root, src, classes)
    return classes


def _walk_decls(node, src: bytes, out: list[ClassInfo]) -> None:
    """Recursively walk looking for type declarations at any nesting level."""
    for child in node.children:
        ntype = child.type
        if ntype == "class_declaration":
            _parse_class(child, src, out)
        elif ntype == "interface_declaration":
            _parse_interface(child, src, out)
        elif ntype == "struct_declaration":
            _parse_struct(child, src, out)
        elif ntype == "enum_declaration":
            _parse_enum(child, src, out)
        elif ntype == "record_declaration":
            _parse_record(child, src, out)
        elif ntype == "delegate_declaration":
            _parse_delegate(child, src, out)
        elif ntype in ("declaration_list", "namespace_declaration",
                       "file_scoped_namespace_declaration"):
            _walk_decls(child, src, out)


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------

def _parse_class(node, src: bytes, out: list[ClassInfo]) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    mods = _collect_modifiers(node)
    if "abstract" in mods:
        kind = "abstract"
    elif "static" in mods:
        kind = "static"
    elif "sealed" in mods:
        kind = "sealed"
    else:
        kind = ""

    attrs = _collect_attributes(node, src)
    bases = _base_list_names(_first(node, "base_list"), src)
    body = _first(node, "declaration_list")
    methods, class_vars, calls = _parse_declaration_list(body, src, name) if body else ([], [], [])

    out.append(ClassInfo(
        name=name, bases=bases, methods=methods, class_vars=class_vars,
        decorators=attrs, docstring="",
        line_start=_line(node), line_end=_end_line(node),
        calls=calls, kind=kind,
    ))

    # Recurse into nested types
    if body:
        _walk_decls(body, src, out)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

def _parse_interface(node, src: bytes, out: list[ClassInfo]) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    attrs = _collect_attributes(node, src)
    bases = _base_list_names(_first(node, "base_list"), src)
    body = _first(node, "declaration_list")
    methods: list[MethodInfo] = []
    if body:
        for child in body.children:
            if child.type == "method_declaration":
                m = _parse_method(child, src)
                if m:
                    methods.append(m)
            elif child.type == "property_declaration":
                p = _parse_property(child, src)
                if p:
                    methods.append(p)

    out.append(ClassInfo(
        name=name, bases=bases, methods=methods, class_vars=[],
        decorators=attrs, docstring="",
        line_start=_line(node), line_end=_end_line(node),
        calls=[], kind="interface",
    ))

    if body:
        _walk_decls(body, src, out)


# ---------------------------------------------------------------------------
# Struct
# ---------------------------------------------------------------------------

def _parse_struct(node, src: bytes, out: list[ClassInfo]) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    attrs = _collect_attributes(node, src)
    bases = _base_list_names(_first(node, "base_list"), src)
    body = _first(node, "declaration_list")
    methods, class_vars, calls = _parse_declaration_list(body, src, name) if body else ([], [], [])

    out.append(ClassInfo(
        name=name, bases=bases, methods=methods, class_vars=class_vars,
        decorators=attrs, docstring="",
        line_start=_line(node), line_end=_end_line(node),
        calls=calls, kind="struct",
    ))

    if body:
        _walk_decls(body, src, out)


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

def _parse_enum(node, src: bytes, out: list[ClassInfo]) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    member_list = _first(node, "enum_member_declaration_list")
    members: list[str] = []
    if member_list:
        for m in _all(member_list, "enum_member_declaration"):
            id_node = _first(m, "identifier")
            if id_node:
                members.append(_text(id_node, src))

    attrs = _collect_attributes(node, src)
    out.append(ClassInfo(
        name=name, bases=[], methods=[], class_vars=members,
        decorators=attrs, docstring="",
        line_start=_line(node), line_end=_end_line(node),
        calls=[], kind="enum",
    ))


# ---------------------------------------------------------------------------
# Record (class and struct variants)
# ---------------------------------------------------------------------------

def _parse_record(node, src: bytes, out: list[ClassInfo]) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    # record struct if `struct` keyword is a direct child
    is_record_struct = any(c.type == "struct" for c in node.children)
    kind = "record struct" if is_record_struct else "record"

    attrs = _collect_attributes(node, src)
    bases = _base_list_names(_first(node, "base_list"), src)

    # Positional parameters become class_vars
    params_node = _first(node, "parameter_list")
    components: list[str] = []
    if params_node:
        for p in _all(params_node, "parameter"):
            id_node = p.child_by_field_name("name")
            if id_node:
                components.append(_text(id_node, src))

    body = _first(node, "declaration_list")
    methods: list[MethodInfo] = []
    if body:
        for child in body.children:
            if child.type == "method_declaration":
                m = _parse_method(child, src)
                if m:
                    methods.append(m)
        _walk_decls(body, src, out)

    out.append(ClassInfo(
        name=name, bases=bases, methods=methods, class_vars=components,
        decorators=attrs, docstring="",
        line_start=_line(node), line_end=_end_line(node),
        calls=[], kind=kind,
    ))


# ---------------------------------------------------------------------------
# Delegate
# ---------------------------------------------------------------------------

def _parse_delegate(node, src: bytes, out: list[ClassInfo]) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    params_node = _first(node, "parameter_list")
    components: list[str] = []
    if params_node:
        for p in _all(params_node, "parameter"):
            id_node = p.child_by_field_name("name")
            if id_node:
                components.append(_text(id_node, src))

    out.append(ClassInfo(
        name=name, bases=[], methods=[], class_vars=components,
        decorators=[], docstring="",
        line_start=_line(node), line_end=_end_line(node),
        calls=[], kind="delegate",
    ))


# ---------------------------------------------------------------------------
# Declaration list (shared body parser for classes, structs)
# ---------------------------------------------------------------------------

def _parse_declaration_list(body, src: bytes, own_name: str):
    methods: list[MethodInfo] = []
    class_vars: list[str] = []
    calls: list[tuple[str, str]] = []
    seen_calls: set[tuple[str, str]] = set()

    for child in body.children:
        if child.type == "method_declaration":
            m = _parse_method(child, src)
            if m:
                methods.append(m)
                _collect_method_calls(child, src, m.name, calls, seen_calls, own_name)
        elif child.type == "constructor_declaration":
            c = _parse_constructor(child, src)
            if c:
                methods.append(c)
        elif child.type == "property_declaration":
            p = _parse_property(child, src)
            if p:
                methods.append(p)
        elif child.type == "field_declaration":
            # Capture const and static readonly fields with UPPER_CASE names
            mods = _collect_modifiers(child)
            if "const" in mods or ("static" in mods and "readonly" in mods):
                var_decl = _first(child, "variable_declaration")
                if var_decl:
                    for decl in _all(var_decl, "variable_declarator"):
                        id_node = _first(decl, "identifier")
                        if id_node:
                            fname = _text(id_node, src)
                            if re.match(r"^[A-Z][A-Z0-9_]*$", fname) or "const" in mods:
                                class_vars.append(fname)

    return methods, class_vars, calls


# ---------------------------------------------------------------------------
# Method / property / constructor parsing
# ---------------------------------------------------------------------------

def _parse_method(node, src: bytes) -> MethodInfo | None:
    # Use named field to avoid confusing the return-type identifier with the name.
    # e.g. "Dog Create(...)" — field "name" is "Create", not "Dog"
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _text(name_node, src)

    mods = _collect_modifiers(node)
    is_static   = "static" in mods
    is_async    = "async" in mods
    is_abstract = "abstract" in mods
    is_override = "override" in mods
    attrs       = _collect_attributes(node, src)

    params_node = _first(node, "parameter_list")
    args = _parse_params(params_node, src) if params_node else []

    # Return type: first type-ish node before the identifier
    return_type = ""
    for child in node.children:
        if child == name_node:
            break
        if child.type in _RETURN_TYPE_NODES | {"generic_name", "nullable_type", "array_type"}:
            return_type = _type_text(child, src)

    return MethodInfo(
        name=name, args=args, return_type=return_type,
        decorators=attrs, is_async=is_async,
        is_property=False,
        is_classmethod=is_static, is_staticmethod=is_static,
    )


def _parse_property(node, src: bytes) -> MethodInfo | None:
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _text(name_node, src)

    type_node = node.child_by_field_name("type")
    return_type = _type_text(type_node, src) if type_node else ""

    return MethodInfo(
        name=name, args=[], return_type=return_type,
        decorators=[], is_async=False,
        is_property=True, is_classmethod=False, is_staticmethod=False,
    )


def _parse_constructor(node, src: bytes) -> MethodInfo | None:
    name_node = _first(node, "identifier")
    if not name_node:
        return None
    params_node = _first(node, "parameter_list")
    args = _parse_params(params_node, src) if params_node else []
    return MethodInfo(
        name="<ctor>", args=args, return_type="",
        decorators=[], is_async=False,
        is_property=False, is_classmethod=False, is_staticmethod=False,
    )


def _parse_params(params_node, src: bytes) -> list[str]:
    args: list[str] = []
    for child in params_node.children:
        if child.type == "parameter":
            # Use the named "name" field so we get the parameter name, not its type.
            # e.g. "Dog owner" → "owner", not "Dog"
            id_node = child.child_by_field_name("name")
            if id_node:
                args.append(_text(id_node, src))
    return args


# ---------------------------------------------------------------------------
# Call graph
# ---------------------------------------------------------------------------

def _collect_method_calls(method_node, src: bytes, method_name: str,
                          out: list[tuple[str, str]], seen: set[tuple[str, str]],
                          own_name: str) -> None:
    body = _first(method_node, "block", "arrow_expression_clause")
    if body:
        _scan_calls(body, src, method_name, out, seen, own_name)


def _scan_calls(node, src: bytes, ctx: str,
                out: list[tuple[str, str]], seen: set[tuple[str, str]],
                own_name: str) -> None:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in ("object_creation_expression", "implicit_object_creation_expression"):
            type_node = _first(current, "identifier", "generic_name", "qualified_name")
            if type_node:
                cname = _type_text(type_node, src).split(".")[0]
                if (cname and cname[0].isupper() and cname not in _CS_IGNORE
                        and cname != own_name):
                    pair = (cname, ctx)
                    if pair not in seen:
                        seen.add(pair)
                        out.append(pair)
        if current.child_count > 0:
            stack.extend(reversed(current.children))


# ---------------------------------------------------------------------------
# Top-level functions — C# has none (all methods are in types)
# ---------------------------------------------------------------------------

def _extract_functions(root, src: bytes) -> list[FunctionInfo]:
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_csharp(path: str, content: str) -> CodeAnalysis:
    """
    Parse a C# source file and return a CodeAnalysis.
    Falls back to a stub with explanatory parse_error if tree-sitter-c-sharp
    is not installed.  Never raises.
    """
    line_count = content.count("\n") + 1

    if not _TREESITTER_AVAILABLE:
        return CodeAnalysis(
            path=path, language="csharp", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                "tree-sitter-c-sharp not installed — run: "
                "pip install \"tree-sitter>=0.23.0\" tree-sitter-c-sharp"
            ],
        )

    try:
        parser = Parser(_CS_LANGUAGE)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        namespace  = _extract_namespace(root, src)
        imports    = _extract_imports(root, src)
        classes    = _extract_type_declarations(root, src)
        functions  = _extract_functions(root, src)

        return CodeAnalysis(
            path=path,
            language="csharp",
            line_count=line_count,
            module_docstring=namespace,
            classes=classes,
            functions=functions,
            imports=imports,
            all_exports=[],
            constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="csharp", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"AnalysisError: {exc}"],
        )
