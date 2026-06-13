"""
project_mapper/java_analyzer.py
Java code structure extractor using tree-sitter.

Extracts the same CodeAnalysis structure as code_analyzer.py so the
ingestor can handle Java files uniformly.

Supports:
  .java — Java source files

Entity kinds:
  ""         — regular class
  "abstract" — abstract class
  "interface"— interface
  "enum"     — enum (constants become class_vars)
  "record"   — Java 16+ record
  "annotation" — @interface annotation type

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-java
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
_JAVA_LANGUAGE = None

try:
    from tree_sitter import Language, Parser
    import tree_sitter_java as _tsj

    _JAVA_LANGUAGE = Language(_tsj.language())
    _TREESITTER_AVAILABLE = True
except Exception:
    pass  # tree-sitter-java not installed — analyze_java() returns stubs


# ---------------------------------------------------------------------------
# Java standard-library classes to exclude from call graphs
# ---------------------------------------------------------------------------

_JAVA_IGNORE: frozenset[str] = frozenset({
    # java.lang (auto-imported)
    "Object", "String", "Integer", "Long", "Double", "Float", "Boolean",
    "Byte", "Short", "Character", "Number", "Math", "System", "Runtime",
    "Thread", "Runnable", "Enum", "Record", "Class", "ClassLoader",
    "Throwable", "Exception", "Error", "RuntimeException",
    "NullPointerException", "IllegalArgumentException", "IllegalStateException",
    "IndexOutOfBoundsException", "UnsupportedOperationException",
    "StringBuilder", "StringBuffer", "Comparable", "Iterable", "Cloneable",
    # java.util
    "List", "ArrayList", "LinkedList", "Map", "HashMap", "LinkedHashMap",
    "TreeMap", "Set", "HashSet", "LinkedHashSet", "TreeSet", "Queue",
    "Deque", "ArrayDeque", "PriorityQueue", "Collections", "Arrays",
    "Optional", "Stream", "Iterator", "ListIterator",
    # java.io / java.nio
    "File", "Path", "Paths", "Files", "InputStream", "OutputStream",
    "Reader", "Writer", "BufferedReader", "BufferedWriter",
    "PrintWriter", "PrintStream",
    # Spring / Jakarta common base types (skip, too generic)
    "Object",
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


def _has_modifier(modifiers_node, *keywords: str) -> bool:
    """Return True if any keyword appears directly in modifiers."""
    if modifiers_node is None:
        return False
    for child in modifiers_node.children:
        if child.type in keywords:
            return True
    return False


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------

def _scoped_id_to_str(node, src: bytes) -> str:
    """Flatten a scoped_identifier / identifier into a dotted string."""
    return _text(node, src)


def _extract_imports(root, src: bytes) -> list[ImportInfo]:
    imports: list[ImportInfo] = []

    for node in root.children:
        if node.type != "import_declaration":
            continue
        is_static = any(c.type == "static" for c in node.children)
        # Find the scoped_identifier or identifier
        module_node = _first(node, "scoped_identifier", "identifier", "asterisk")
        if not module_node:
            # wildcard: "import java.util.*"
            # look for the last significant token
            for c in reversed(node.children):
                if c.type not in (";", "import", "static"):
                    module_node = c
                    break
        if not module_node:
            continue

        raw = _text(module_node, src)
        is_wildcard = raw.endswith(".*")
        module_path = raw.rstrip(".*").rstrip(".")

        # Module is the package; names = [simple class name] or ["*"]
        parts = module_path.split(".")
        if is_wildcard:
            names = ["*"]
            module = module_path
        else:
            names = [parts[-1]] if parts else []
            module = ".".join(parts[:-1]) if len(parts) > 1 else module_path

        imports.append(ImportInfo(
            module=module,
            names=names,
            is_from=True,
            is_relative=False,
            level=0,
        ))

    return imports


# ---------------------------------------------------------------------------
# Class / interface / enum / record extraction
# ---------------------------------------------------------------------------

_TOP_DECL_TYPES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}


def _extract_type_declarations(root, src: bytes) -> list[ClassInfo]:
    """Walk top-level and extract all type declarations (including nested)."""
    result: list[ClassInfo] = []
    _walk_declarations(root, src, result, depth=0)
    return result


def _walk_declarations(node, src: bytes, out: list[ClassInfo], depth: int) -> None:
    for child in node.children:
        ntype = child.type
        if ntype == "class_declaration":
            _parse_class(child, src, out, depth)
        elif ntype == "interface_declaration":
            _parse_interface(child, src, out, depth)
        elif ntype == "enum_declaration":
            _parse_enum(child, src, out, depth)
        elif ntype == "record_declaration":
            _parse_record(child, src, out, depth)
        elif ntype == "annotation_type_declaration":
            _parse_annotation(child, src, out, depth)
        # Don't recurse into method/constructor bodies — only into class bodies
        elif ntype == "class_body":
            _walk_declarations(child, src, out, depth + 1)


# --- Class ---

def _parse_class(node, src: bytes, out: list[ClassInfo], depth: int = 0) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    modifiers = _first(node, "modifiers")
    is_abstract = _has_modifier(modifiers, "abstract")
    decorators = _collect_annotations(modifiers, src)

    # Bases: extends (one class) + implements (one or more interfaces)
    bases: list[str] = []
    superclass = _first(node, "superclass")
    if superclass:
        sc_type = _first(superclass, "type_identifier", "generic_type")
        if sc_type:
            bases.append(_text(sc_type, src).split("<")[0])

    super_ifaces = _first(node, "super_interfaces")
    if super_ifaces:
        type_list = _first(super_ifaces, "type_list")
        if type_list:
            for ti in _all(type_list, "type_identifier", "generic_type"):
                bases.append(_text(ti, src).split("<")[0])

    body = _first(node, "class_body")
    methods, class_vars, calls = _parse_class_body(body, src, name) if body else ([], [], [])

    # Also descend into nested classes
    if body:
        _walk_declarations(body, src, out, depth + 1)

    out.append(ClassInfo(
        name=name,
        bases=bases,
        methods=methods,
        class_vars=class_vars,
        decorators=decorators,
        docstring="",
        line_start=_line(node),
        line_end=_end_line(node),
        calls=calls,
        kind="abstract" if is_abstract else "",
    ))


def _parse_class_body(body, src: bytes, own_name: str):
    methods: list[MethodInfo] = []
    class_vars: list[str] = []
    calls: list[tuple[str, str]] = []
    seen_calls: set[tuple[str, str]] = set()

    for child in body.children:
        if child.type == "method_declaration":
            m = _parse_method(child, src)
            if m:
                methods.append(m)
                _collect_calls_from_method(child, src, m.name, calls, seen_calls, own_name)
        elif child.type == "constructor_declaration":
            # Include constructors in methods with name = class name
            c = _parse_constructor(child, src)
            if c:
                methods.append(c)
        elif child.type == "field_declaration":
            # Capture constants: static final UPPER_CASE fields
            mods = _first(child, "modifiers")
            if _has_modifier(mods, "static", "final") if mods else False:
                for decl in _all(child, "variable_declarator"):
                    id_node = _first(decl, "identifier")
                    if id_node:
                        fname = _text(id_node, src)
                        if re.match(r"^[A-Z][A-Z0-9_]*$", fname):
                            class_vars.append(fname)

    return methods, class_vars, calls


# --- Interface ---

def _parse_interface(node, src: bytes, out: list[ClassInfo], depth: int = 0) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    modifiers = _first(node, "modifiers")
    decorators = _collect_annotations(modifiers, src)

    # Interface extends (other interfaces)
    bases: list[str] = []
    ext_ifaces = _first(node, "extends_interfaces")
    if ext_ifaces:
        type_list = _first(ext_ifaces, "type_list")
        if type_list:
            for ti in _all(type_list, "type_identifier", "generic_type"):
                bases.append(_text(ti, src).split("<")[0])

    body = _first(node, "interface_body")
    methods: list[MethodInfo] = []
    if body:
        for child in body.children:
            if child.type == "method_declaration":
                m = _parse_method(child, src)
                if m:
                    methods.append(m)
            elif child.type == "class_declaration":
                _parse_class(child, src, out, depth + 1)

    out.append(ClassInfo(
        name=name,
        bases=bases,
        methods=methods,
        class_vars=[],
        decorators=decorators,
        docstring="",
        line_start=_line(node),
        line_end=_end_line(node),
        calls=[],
        kind="interface",
    ))


# --- Enum ---

def _parse_enum(node, src: bytes, out: list[ClassInfo], depth: int = 0) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    modifiers = _first(node, "modifiers")
    decorators = _collect_annotations(modifiers, src)

    # Enum implements interfaces
    bases: list[str] = []
    super_ifaces = _first(node, "super_interfaces")
    if super_ifaces:
        type_list = _first(super_ifaces, "type_list")
        if type_list:
            for ti in _all(type_list, "type_identifier", "generic_type"):
                bases.append(_text(ti, src).split("<")[0])

    body = _first(node, "enum_body")
    enum_constants: list[str] = []
    methods: list[MethodInfo] = []

    if body:
        # Enum constants
        for child in _all(body, "enum_constant"):
            id_node = _first(child, "identifier")
            if id_node:
                enum_constants.append(_text(id_node, src))

        # Methods live in enum_body_declarations
        decls = _first(body, "enum_body_declarations")
        if decls:
            for child in decls.children:
                if child.type == "method_declaration":
                    m = _parse_method(child, src)
                    if m:
                        methods.append(m)
                elif child.type == "class_declaration":
                    _parse_class(child, src, out, depth + 1)

    out.append(ClassInfo(
        name=name,
        bases=bases,
        methods=methods,
        class_vars=enum_constants,
        decorators=decorators,
        docstring="",
        line_start=_line(node),
        line_end=_end_line(node),
        calls=[],
        kind="enum",
    ))


# --- Record ---

def _parse_record(node, src: bytes, out: list[ClassInfo], depth: int = 0) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    modifiers = _first(node, "modifiers")
    decorators = _collect_annotations(modifiers, src)

    # Record components (its canonical constructor args) become bases-like info
    # We store the component names as class_vars
    params_node = _first(node, "formal_parameters")
    components: list[str] = []
    if params_node:
        for fp in _all(params_node, "formal_parameter"):
            id_node = _first(fp, "identifier")
            if id_node:
                components.append(_text(id_node, src))

    # Implements
    bases: list[str] = []
    super_ifaces = _first(node, "super_interfaces")
    if super_ifaces:
        type_list = _first(super_ifaces, "type_list")
        if type_list:
            for ti in _all(type_list, "type_identifier", "generic_type"):
                bases.append(_text(ti, src).split("<")[0])

    body = _first(node, "class_body")
    methods: list[MethodInfo] = []
    if body:
        _walk_declarations(body, src, out, depth + 1)
        for child in body.children:
            if child.type == "method_declaration":
                m = _parse_method(child, src)
                if m:
                    methods.append(m)

    out.append(ClassInfo(
        name=name,
        bases=bases,
        methods=methods,
        class_vars=components,
        decorators=decorators,
        docstring="",
        line_start=_line(node),
        line_end=_end_line(node),
        calls=[],
        kind="record",
    ))


# --- Annotation type ---

def _parse_annotation(node, src: bytes, out: list[ClassInfo], depth: int = 0) -> None:
    name_node = _first(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, src)

    body = _first(node, "annotation_type_body")
    elements: list[str] = []
    if body:
        for child in body.children:
            if child.type == "annotation_type_element_declaration":
                id_node = _first(child, "identifier")
                if id_node:
                    elements.append(_text(id_node, src))

    out.append(ClassInfo(
        name=name,
        bases=[],
        methods=[MethodInfo(name=e, args=[]) for e in elements],
        class_vars=[],
        decorators=[],
        docstring="",
        line_start=_line(node),
        line_end=_end_line(node),
        calls=[],
        kind="annotation",
    ))


# ---------------------------------------------------------------------------
# Method / constructor parsing
# ---------------------------------------------------------------------------

def _parse_method(node, src: bytes) -> MethodInfo | None:
    name_node = _first(node, "identifier")
    if not name_node:
        return None
    name = _text(name_node, src)

    modifiers = _first(node, "modifiers")
    is_static   = _has_modifier(modifiers, "static")
    is_abstract = _has_modifier(modifiers, "abstract")

    params_node = _first(node, "formal_parameters")
    args = _parse_params(params_node, src) if params_node else []

    # Return type: first type node before identifier (various Java type nodes)
    _TYPE_NODES = {
        "type_identifier", "void_type", "integral_type", "floating_point_type",
        "boolean_type", "generic_type", "array_type", "wildcard_type",
    }
    return_type = ""
    for child in node.children:
        if child.type in _TYPE_NODES:
            return_type = _text(child, src)
            break
        if child == name_node:
            break

    return MethodInfo(
        name=name,
        args=args,
        return_type=return_type,
        decorators=_collect_annotations(modifiers, src),
        is_async=False,
        is_property=False,
        is_classmethod=is_static,
        is_staticmethod=is_static,
    )


def _parse_constructor(node, src: bytes) -> MethodInfo | None:
    name_node = _first(node, "identifier")
    if not name_node:
        return None
    name = _text(name_node, src)
    params_node = _first(node, "formal_parameters")
    args = _parse_params(params_node, src) if params_node else []
    return MethodInfo(
        name=f"<init>",   # Java convention for constructors
        args=args,
        return_type="",
        decorators=[],
        is_async=False,
        is_property=False,
        is_classmethod=False,
        is_staticmethod=False,
    )


def _parse_params(params_node, src: bytes) -> list[str]:
    """Return flat list of parameter names."""
    args: list[str] = []
    for child in params_node.children:
        if child.type in ("formal_parameter", "spread_parameter"):
            id_node = _first(child, "identifier")
            if id_node:
                suffix = "..." if child.type == "spread_parameter" else ""
                args.append(_text(id_node, src) + suffix)
        elif child.type == "receiver_parameter":
            pass  # skip `Foo.this` receiver params
    return args


def _collect_annotations(modifiers_node, src: bytes) -> list[str]:
    """Extract annotation names from a modifiers node."""
    if not modifiers_node:
        return []
    result = []
    for child in modifiers_node.children:
        if child.type in ("annotation", "marker_annotation"):
            id_node = _first(child, "identifier")
            if id_node:
                result.append(_text(id_node, src))
    return result


# ---------------------------------------------------------------------------
# Call graph (new X() and static calls inside method bodies)
# ---------------------------------------------------------------------------

def _collect_calls_from_method(
    method_node, src: bytes, method_name: str,
    out: list[tuple[str, str]], seen: set[tuple[str, str]], own_name: str,
) -> None:
    body = _first(method_node, "block")
    if not body:
        return
    _scan_calls(body, src, method_name, out, seen, own_name)


def _scan_calls(
    node, src: bytes, context: str,
    out: list[tuple[str, str]], seen: set[tuple[str, str]], own_name: str,
) -> None:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "object_creation_expression":
            # new ClassName(...)
            type_node = _first(current, "type_identifier", "generic_type")
            if type_node:
                cname = _text(type_node, src).split("<")[0]
                if cname and cname[0].isupper() and cname not in _JAVA_IGNORE and cname != own_name:
                    pair = (cname, context)
                    if pair not in seen:
                        seen.add(pair)
                        out.append(pair)
        if current.child_count > 0:
            stack.extend(reversed(current.children))


# ---------------------------------------------------------------------------
# Top-level function extraction
# ---------------------------------------------------------------------------
# Java has no top-level functions — only methods inside types.
# We return an empty list here; standalone static methods on utility classes
# are captured under their class.

def _extract_functions(root, src: bytes) -> list[FunctionInfo]:
    return []


# ---------------------------------------------------------------------------
# Package extraction (used as module path)
# ---------------------------------------------------------------------------

def _extract_package(root, src: bytes) -> str:
    for child in root.children:
        if child.type == "package_declaration":
            scope = _first(child, "scoped_identifier", "identifier")
            if scope:
                return _text(scope, src)
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_java(path: str, content: str) -> CodeAnalysis:
    """
    Parse a Java source file and return a CodeAnalysis.
    Falls back to a stub with explanatory parse_error if tree-sitter-java
    is not installed.  Never raises.
    """
    line_count = content.count("\n") + 1

    if not _TREESITTER_AVAILABLE:
        return CodeAnalysis(
            path=path, language="java", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                "tree-sitter-java not installed — run: "
                "pip install \"tree-sitter>=0.23.0\" tree-sitter-java"
            ],
        )

    try:
        parser = Parser(_JAVA_LANGUAGE)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        imports    = _extract_imports(root, src)
        classes    = _extract_type_declarations(root, src)
        functions  = _extract_functions(root, src)
        package    = _extract_package(root, src)

        return CodeAnalysis(
            path=path,
            language="java",
            line_count=line_count,
            module_docstring=package,   # re-use docstring field for package name
            classes=classes,
            functions=functions,
            imports=imports,
            all_exports=[],
            constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="java", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"AnalysisError: {exc}"],
        )
