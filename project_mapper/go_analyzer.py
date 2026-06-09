"""
project_mapper/go_analyzer.py
Go code structure extractor using tree-sitter.

Extracts the same CodeAnalysis structure as code_analyzer.py so the
ingestor can handle Go files uniformly.

Supports:
  .go — Go source files (including generics, Go 1.18+)

Go has no classes; structs + interfaces are the main structural entities.
Methods are file-level declarations with a receiver parameter — this
requires a two-pass approach: collect types first, then attach methods.

Entity kinds:
  ""          — struct (Go's primary aggregate type)
  "interface" — interface
  "type"      — named type over a primitive (e.g. type Role int)
  "alias"     — type alias (type Writer = io.Writer)

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-go
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
_GO_LANGUAGE = None

try:
    from tree_sitter import Language, Parser
    import tree_sitter_go as _tsgo

    _GO_LANGUAGE = Language(_tsgo.language())
    _TREESITTER_AVAILABLE = True
except Exception:
    pass


# ---------------------------------------------------------------------------
# Go standard-library and built-in identifiers to skip in call graphs
# ---------------------------------------------------------------------------

_GO_IGNORE: frozenset[str] = frozenset({
    # Built-in functions
    "make", "new", "len", "cap", "append", "copy", "delete", "close",
    "panic", "recover", "print", "println", "real", "imag", "complex",
    # Common stdlib types
    "error", "string", "int", "int64", "int32", "float64", "bool", "byte",
    "rune", "uint", "uint64", "uint32", "any", "interface",
    # fmt
    "Sprintf", "Printf", "Fprintf", "Errorf", "Println", "Fprintln",
    # errors
    "New", "As", "Is", "Unwrap",
    # context
    "Background", "TODO", "WithCancel", "WithTimeout", "WithDeadline",
    # sync
    "Mutex", "RWMutex", "WaitGroup", "Once",
    # testing
    "T", "B", "M", "F",
})


# ---------------------------------------------------------------------------
# Tree-sitter node helpers
# ---------------------------------------------------------------------------

def _text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _field(node, name: str):
    try:
        return node.child_by_field_name(name)
    except Exception:
        return None


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


# ---------------------------------------------------------------------------
# Type name helpers
# ---------------------------------------------------------------------------

_TYPE_NODES = {
    "type_identifier", "qualified_type", "pointer_type", "slice_type",
    "array_type", "map_type", "channel_type", "generic_type",
    "interface_type", "struct_type", "func_type",
}


def _type_name(node, src: bytes) -> str:
    """Extract a readable type name, stripping pointer / slice decorators."""
    if node is None:
        return ""
    t = node.type
    if t == "pointer_type":
        inner = _first(node, "type_identifier", "generic_type", "qualified_type")
        return _text(inner, src).split("[")[0] if inner else ""
    if t == "generic_type":
        inner = _first(node, "type_identifier")
        return _text(inner, src) if inner else _text(node, src).split("[")[0]
    if t == "qualified_type":
        # e.g. io.Writer → just return full text
        return _text(node, src)
    return _text(node, src).split("[")[0]


def _receiver_type_name(param_list_node, src: bytes) -> str:
    """Extract the bare receiver type name from (d *Dog) or (c Config)."""
    for child in param_list_node.children:
        if child.type == "parameter_declaration":
            # type is the last significant child
            for n in reversed(child.children):
                if n.type in _TYPE_NODES:
                    return _type_name(n, src)
    return ""


# ---------------------------------------------------------------------------
# Package extraction
# ---------------------------------------------------------------------------

def _extract_package(root, src: bytes) -> str:
    pkg = _first(root, "package_clause")
    if pkg:
        name = _first(pkg, "package_identifier")
        if name:
            return _text(name, src)
    return ""


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------

def _extract_imports(root, src: bytes) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for node in root.children:
        if node.type == "import_declaration":
            _parse_import_decl(node, src, imports)
    return imports


def _parse_import_spec(spec, src: bytes) -> ImportInfo | None:
    # find the string literal (module path)
    str_node = _first(spec, "interpreted_string_literal", "raw_string_literal")
    if not str_node:
        return None
    path = _text(str_node, src).strip('"').strip('`')
    alias_node = _first(spec, "package_identifier", "blank_identifier", "dot")
    alias = _text(alias_node, src) if alias_node else ""
    # Simple name = last path component
    parts = path.split("/")
    name = alias if alias and alias not in (".", "_") else (parts[-1] if parts else path)
    module = "/".join(parts[:-1]) if len(parts) > 1 else path
    is_relative = path.startswith(".")
    return ImportInfo(
        module=module,
        names=[name],
        is_from=False,
        is_relative=is_relative,
        level=0,
        alias=alias,
    )


def _parse_import_decl(node, src: bytes, out: list[ImportInfo]) -> None:
    spec_list = _first(node, "import_spec_list")
    if spec_list:
        for spec in _all(spec_list, "import_spec"):
            imp = _parse_import_spec(spec, src)
            if imp:
                out.append(imp)
    else:
        spec = _first(node, "import_spec")
        if spec:
            imp = _parse_import_spec(spec, src)
            if imp:
                out.append(imp)


# ---------------------------------------------------------------------------
# Constant extraction (package-level, exported / iota)
# ---------------------------------------------------------------------------

def _extract_constants(root, src: bytes) -> list[str]:
    constants: list[str] = []
    for node in root.children:
        if node.type == "const_declaration":
            spec_list = _first(node, "const_spec")
            specs = _all(node, "const_spec") if not spec_list else []
            if spec_list:
                specs = [spec_list]
            # group or single
            for spec in _all(node, "const_spec"):
                name_node = _first(spec, "identifier")
                if name_node:
                    name = _text(name_node, src)
                    if name[0].isupper():  # exported only
                        constants.append(name)
    return constants


# ---------------------------------------------------------------------------
# Type declaration extraction (structs, interfaces, named types)
# Two-pass: first collect types, then attach methods.
# ---------------------------------------------------------------------------

def _extract_types(root, src: bytes) -> tuple[list[ClassInfo], dict[str, int]]:
    """
    Returns (classes, name_to_index) where name_to_index maps type name → index
    in classes list.  Methods are attached in a second pass.
    """
    classes: list[ClassInfo] = []
    name_to_idx: dict[str, int] = {}

    for node in root.children:
        if node.type != "type_declaration":
            continue
        # type_spec or type_alias
        spec = _first(node, "type_spec")
        alias = _first(node, "type_alias")

        if spec:
            name_node = _first(spec, "type_identifier")
            if not name_node:
                continue
            name = _text(name_node, src)

            # Check struct / interface explicitly first, then fall back
            inner_struct = _first(spec, "struct_type")
            inner_iface  = _first(spec, "interface_type")

            if inner_struct:
                inner = inner_struct
            elif inner_iface:
                inner = inner_iface
            else:
                # Named type (type Role int) — skip the name identifier, find underlying
                inner = None
                seen_name = False
                for child in spec.children:
                    if child.type == "type_identifier" and not seen_name:
                        seen_name = True
                        continue
                    if child.type in ("type_identifier", "qualified_type", "pointer_type",
                                      "slice_type", "array_type", "map_type",
                                      "generic_type", "func_type"):
                        inner = child
                        break

            if inner is None:
                continue

            if inner.type == "struct_type":
                bases = _struct_embedded_types(inner, src)
                cls = ClassInfo(
                    name=name, bases=bases, methods=[], class_vars=[],
                    decorators=[], docstring="",
                    line_start=_line(node), line_end=_end_line(node),
                    calls=[], kind="",
                )
            elif inner.type == "interface_type":
                bases, methods = _interface_contents(inner, src)
                cls = ClassInfo(
                    name=name, bases=bases, methods=methods, class_vars=[],
                    decorators=[], docstring="",
                    line_start=_line(node), line_end=_end_line(node),
                    calls=[], kind="interface",
                )
            else:
                # Named type over primitive/other: type Role int
                underlying = _text(inner, src).split("[")[0]
                cls = ClassInfo(
                    name=name, bases=[underlying], methods=[], class_vars=[],
                    decorators=[], docstring="",
                    line_start=_line(node), line_end=_end_line(node),
                    calls=[], kind="type",
                )

        elif alias:
            # type Writer = io.Writer
            name_node = _first(alias, "type_identifier")
            if not name_node:
                continue
            name = _text(name_node, src)
            underlying_node = None
            for child in alias.children:
                if child.type not in ("type_identifier", "=") and child == name_node:
                    continue
                if child.type in _TYPE_NODES:
                    underlying_node = child
                    break
            underlying = _type_name(underlying_node, src) if underlying_node else ""
            cls = ClassInfo(
                name=name, bases=[underlying] if underlying else [], methods=[],
                class_vars=[], decorators=[], docstring="",
                line_start=_line(node), line_end=_end_line(node),
                calls=[], kind="alias",
            )
        else:
            continue

        name_to_idx[cls.name] = len(classes)
        classes.append(cls)

    return classes, name_to_idx


def _struct_embedded_types(struct_node, src: bytes) -> list[str]:
    """Return names of embedded (anonymous) types in a struct."""
    embedded = []
    fdl = _first(struct_node, "field_declaration_list")
    if not fdl:
        return embedded
    for fd in _all(fdl, "field_declaration"):
        # Embedded field has type but no leading identifier(s)
        children = [c for c in fd.children if c.type not in (",", ";", "\n")]
        if not children:
            continue
        # If first child is a type node (not an identifier), it's embedded
        if children[0].type in ("type_identifier", "pointer_type", "qualified_type", "generic_type"):
            embedded.append(_type_name(children[0], src))
    return embedded


def _interface_contents(iface_node, src: bytes) -> tuple[list[str], list[MethodInfo]]:
    """Extract embedded interfaces and method signatures from an interface_type."""
    bases: list[str] = []
    methods: list[MethodInfo] = []

    for child in iface_node.children:
        if child.type == "method_elem":
            m = _parse_interface_method(child, src)
            if m:
                methods.append(m)
        elif child.type == "type_elem":
            # Embedded interface
            type_node = _first(child, "type_identifier", "qualified_type", "generic_type")
            if type_node:
                bases.append(_type_name(type_node, src))

    return bases, methods


def _parse_interface_method(node, src: bytes) -> MethodInfo | None:
    name_node = _first(node, "field_identifier")
    if not name_node:
        return None
    name = _text(name_node, src)

    params_node = _first(node, "parameter_list")
    args = _parse_params(params_node, src) if params_node else []

    # Return type: last type node / parameter_list in the method_elem
    return_type = ""
    children_after_params = []
    past_params = False
    for child in node.children:
        if child == params_node:
            past_params = True
            continue
        if past_params and child.type in _TYPE_NODES | {"parameter_list"}:
            children_after_params.append(child)
    if children_after_params:
        ret = children_after_params[-1]
        if ret.type == "parameter_list":
            # Multi-return: (string, error)
            return_type = _text(ret, src)
        else:
            return_type = _type_name(ret, src)

    return MethodInfo(name=name, args=args, return_type=return_type)


# ---------------------------------------------------------------------------
# Method declaration extraction (second pass — attach to structs)
# ---------------------------------------------------------------------------

def _extract_methods(root, src: bytes, name_to_idx: dict[str, int],
                     classes: list[ClassInfo]) -> None:
    """Walk all method_declaration nodes and attach to their receiver type."""
    for node in root.children:
        if node.type != "method_declaration":
            continue
        # First parameter_list is the receiver
        receiver_list = _first(node, "parameter_list")
        if not receiver_list:
            continue
        receiver_type = _receiver_type_name(receiver_list, src)
        if not receiver_type or receiver_type not in name_to_idx:
            continue

        name_node = _first(node, "field_identifier")
        if not name_node:
            continue
        method_name = _text(name_node, src)

        # Find the parameters (second parameter_list)
        param_lists = _all(node, "parameter_list")
        params_node = param_lists[1] if len(param_lists) >= 2 else None
        args = _parse_params(params_node, src) if params_node else []

        # Return type: first type node after the params list
        return_type = ""
        past_params = False
        for child in node.children:
            if child == params_node:
                past_params = True
                continue
            if past_params and child.type in _TYPE_NODES | {"parameter_list"}:
                if child.type == "parameter_list":
                    return_type = _text(child, src)
                else:
                    return_type = _type_name(child, src)
                break

        method = MethodInfo(name=method_name, args=args, return_type=return_type)
        idx = name_to_idx[receiver_type]
        classes[idx].methods.append(method)

        # Call graph: struct instantiations inside method body
        body = _first(node, "block")
        if body and classes[idx].kind == "":
            _extract_calls_from_block(body, src, method_name, classes[idx], receiver_type)


def _extract_calls_from_block(body, src: bytes, method_name: str,
                               cls: ClassInfo, own_name: str) -> None:
    seen = {(c, m) for c, m in cls.calls}

    def _scan(node):
        if node.type == "composite_literal":
            type_node = _first(node, "type_identifier", "qualified_type", "generic_type")
            if type_node:
                cname = _type_name(type_node, src).split(".")[0]
                if (cname and cname[0].isupper() and cname not in _GO_IGNORE
                        and cname != own_name):
                    pair = (cname, method_name)
                    if pair not in seen:
                        seen.add(pair)
                        cls.calls.append(pair)
        for child in node.children:
            _scan(child)

    _scan(body)


# ---------------------------------------------------------------------------
# Function extraction (top-level non-method functions)
# ---------------------------------------------------------------------------

def _extract_functions(root, src: bytes) -> list[FunctionInfo]:
    functions: list[FunctionInfo] = []
    for node in root.children:
        if node.type != "function_declaration":
            continue
        name_node = _first(node, "identifier")
        if not name_node:
            continue
        name = _text(name_node, src)
        # Skip unexported helpers (lowercase start) — configurable
        # We include all exported + constructor-style (New*)
        if not name[0].isupper() and not name.startswith("New"):
            continue

        param_lists = _all(node, "parameter_list")
        params_node = param_lists[0] if param_lists else None
        args = [ArgInfo(name=p) for p in (_parse_params(params_node, src) if params_node else [])]

        return_type = ""
        past_params = False
        for child in node.children:
            if child == params_node:
                past_params = True
                continue
            if past_params and child.type in _TYPE_NODES | {"parameter_list"}:
                if child.type == "parameter_list":
                    return_type = _text(child, src)
                else:
                    return_type = _type_name(child, src)
                break

        functions.append(FunctionInfo(
            name=name, args=args, return_type=return_type,
            decorators=[], docstring="", is_async=False,
            line_start=_line(node), line_end=_end_line(node),
            calls=_extract_function_calls(node, src, name),
        ))
    return functions


def _extract_function_calls(node, src: bytes, fn_name: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _scan(n):
        if n.type == "composite_literal":
            type_node = _first(n, "type_identifier", "qualified_type", "generic_type")
            if type_node:
                cname = _type_name(type_node, src).split(".")[0]
                if (cname and cname[0].isupper() and cname not in _GO_IGNORE
                        and cname not in seen):
                    seen.add(cname)
                    results.append((cname, fn_name))
        for child in n.children:
            _scan(child)

    _scan(node)
    return results


# ---------------------------------------------------------------------------
# Parameter parsing
# ---------------------------------------------------------------------------

def _parse_params(params_node, src: bytes) -> list[str]:
    """Return flat list of parameter names (or type names for unnamed params)."""
    args: list[str] = []
    for child in params_node.children:
        if child.type == "parameter_declaration":
            children = child.children
            # Go allows: "name type" or just "type" (unnamed), or "name1, name2 type"
            identifiers = [c for c in children if c.type == "identifier"]
            type_node = None
            for c in reversed(children):
                if c.type in _TYPE_NODES | {"variadic_type"}:
                    type_node = c
                    break
            if identifiers:
                for id_node in identifiers:
                    args.append(_text(id_node, src))
            elif type_node:
                # Unnamed parameter — use type as label
                args.append(_type_name(type_node, src))
        elif child.type == "variadic_parameter_declaration":
            id_node = _first(child, "identifier")
            if id_node:
                args.append(_text(id_node, src) + "...")
            else:
                type_node = _first(child, *list(_TYPE_NODES))
                if type_node:
                    args.append(_type_name(type_node, src) + "...")
    return args


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_go(path: str, content: str) -> CodeAnalysis:
    """
    Parse a Go source file and return a CodeAnalysis.
    Falls back to a stub with explanatory parse_error if tree-sitter-go
    is not installed.  Never raises.
    """
    line_count = content.count("\n") + 1

    if not _TREESITTER_AVAILABLE:
        return CodeAnalysis(
            path=path, language="go", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                "tree-sitter-go not installed — run: "
                "pip install \"tree-sitter>=0.23.0\" tree-sitter-go"
            ],
        )

    try:
        parser = Parser(_GO_LANGUAGE)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        package    = _extract_package(root, src)
        imports    = _extract_imports(root, src)
        constants  = _extract_constants(root, src)

        # Two-pass: collect types, then attach methods
        classes, name_to_idx = _extract_types(root, src)
        _extract_methods(root, src, name_to_idx, classes)
        functions  = _extract_functions(root, src)

        # Store exported constants in module_docstring / constants field
        return CodeAnalysis(
            path=path,
            language="go",
            line_count=line_count,
            module_docstring=package,   # package name
            classes=classes,
            functions=functions,
            imports=imports,
            all_exports=[],
            constants=constants,
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="go", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"AnalysisError: {exc}"],
        )
