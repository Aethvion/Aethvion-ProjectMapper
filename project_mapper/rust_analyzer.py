"""
core/project_mapper/rust_analyzer.py
Rust source-file analyzer using tree-sitter.

Entity kinds extracted:
  "struct"  — struct items
  "enum"    — enum items
  "trait"   — trait definitions
  "impl"    — synthetic impl entries when no matching struct/enum/trait found
  "type"    — type alias items

Two-pass strategy: pass 1 collects structs/enums/traits by name;
pass 2 processes impl blocks and attaches methods to the matching type.

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-rust
"""

from __future__ import annotations

try:
    from tree_sitter import Language, Parser
    import tree_sitter_rust as _tsrust
    _RUST_LANGUAGE = Language(_tsrust.language())
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


def _preceding_rust_doc(node, src: bytes) -> str:
    before = src[:node.start_byte].decode("utf-8", errors="replace").rstrip()
    lines = before.split("\n")
    doc_lines = []
    for line in reversed(lines):
        line_stripped = line.strip()
        if line_stripped.startswith("///"):
            doc_lines.append(line_stripped.removeprefix("///").strip())
        elif line_stripped.startswith("//!"):
            doc_lines.append(line_stripped.removeprefix("//!").strip())
        elif not line_stripped:
            break
        elif line_stripped.startswith("/**") or line_stripped.startswith("/*!"):
            inner = line_stripped
            if inner.startswith("/**"):
                inner = inner.removeprefix("/**")
            else:
                inner = inner.removeprefix("/*!")
            if inner.endswith("*/"):
                inner = inner.removesuffix("*/")
            doc_lines.append(inner.strip())
            break
        elif line_stripped.startswith("#["):
            continue
        elif line_stripped.startswith("pub") or line_stripped.startswith("crate") or line_stripped.startswith("async"):
            continue
        else:
            break
    if not doc_lines:
        return ""
    doc_lines.reverse()
    text = " ".join(doc_lines)
    return text[:200]


# ---------------------------------------------------------------------------
# parameter parsing
# ---------------------------------------------------------------------------


def _parse_params(params_node, src: bytes) -> list[str]:
    """Extract parameter names from a `parameters` node."""
    if params_node is None:
        return []
    names: list[str] = []
    for child in params_node.children:
        if child.type == "self_parameter":
            continue  # skip &self / &mut self
        if child.type == "parameter":
            # No `name` field in tree-sitter-rust — first identifier child is the name
            for c in child.children:
                if c.type == "identifier":
                    names.append(_t(c, src))
                    break
    return names


# ---------------------------------------------------------------------------
# call graph extraction
# ---------------------------------------------------------------------------

_RUST_CRATE_PREFIXES: frozenset[str] = frozenset({"crate", "self", "super", "std", "core", "alloc"})


def _collect_calls_rust(body_node, src: bytes) -> list[tuple[str, str]]:
    """Walk a Rust block body and return (callee_name, "") for each call."""
    if body_node is None:
        return []
    calls: list[tuple[str, str]] = []

    def _walk(node):
        nt = node.type
        if nt == "call_expression":
            fn = node.child_by_field_name("function")
            if fn:
                fnt = fn.type
                if fnt == "identifier":
                    name = _t(fn, src)
                    if name and name.isidentifier():
                        calls.append((name, ""))
                elif fnt == "scoped_identifier":
                    # Foo::new, crate::bar::Baz — take first non-crate part
                    raw = _t(fn, src)
                    parts = [p.strip() for p in raw.split("::") if p.strip()]
                    for part in parts:
                        if part not in _RUST_CRATE_PREFIXES and part.isidentifier():
                            calls.append((part, ""))
                            break
                elif fnt == "field_expression":
                    f = fn.child_by_field_name("field")
                    if f:
                        name = _t(f, src)
                        if name and name.isidentifier():
                            calls.append((name, ""))
        elif nt == "method_call_expression":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _t(name_node, src)
                if name and name.isidentifier():
                    calls.append((name, ""))
        for c in node.children:
            _walk(c)

    _walk(body_node)
    return calls


def _collect_impl_calls_rust(impl_node, src: bytes) -> list[tuple[str, str]]:
    """Aggregate calls from all method bodies within an impl block."""
    body = impl_node.child_by_field_name("body")
    if not body:
        return []
    calls: list[tuple[str, str]] = []
    for child in body.children:
        if child.type == "function_item":
            calls.extend(_collect_calls_rust(child.child_by_field_name("body"), src))
    return calls


# ---------------------------------------------------------------------------
# function / method parsing
# ---------------------------------------------------------------------------


def _parse_fn(node, src: bytes) -> MethodInfo:
    """Parse a function_item or function_signature_item into a MethodInfo."""
    name = _ft(node, "name", src)

    is_async = False
    for c in node.children:
        if c.type == "function_modifiers":
            for m in c.children:
                if m.type == "async":
                    is_async = True
            break

    params_node = node.child_by_field_name("parameters")
    args = _parse_params(params_node, src)

    ret_node = node.child_by_field_name("return_type")
    return_type = _t(ret_node, src) if ret_node else ""

    return MethodInfo(name=name, args=args, return_type=return_type, is_async=is_async)


def _parse_fn_info(node, src: bytes) -> FunctionInfo:
    m = _parse_fn(node, src)
    body_node = node.child_by_field_name("body")
    calls = _collect_calls_rust(body_node, src)
    return FunctionInfo(
        name=m.name,
        args=[ArgInfo(name=a) for a in m.args],
        return_type=m.return_type,
        is_async=m.is_async,
        calls=calls,
        line_start=_line(node),
        line_end=_end_line(node),
        docstring=_preceding_rust_doc(node, src),
    )


# ---------------------------------------------------------------------------
# impl block helpers
# ---------------------------------------------------------------------------


def _impl_type_name(impl_node, src: bytes) -> str:
    """Return the implementing type name from the `type` field of impl_item."""
    type_node = impl_node.child_by_field_name("type")
    if type_node:
        raw = _t(type_node, src)
        return raw.split("<")[0].strip()  # strip generic params
    return ""


def _impl_trait_name(impl_node, src: bytes) -> str:
    """For `impl Trait for Type`, return the trait name; "" for plain impl."""
    found_for = False
    trait = ""
    for c in impl_node.children:
        if c.type == "for":
            found_for = True
            break
        if c.type in ("type_identifier", "generic_type", "scoped_type_identifier"):
            trait = _t(c, src).split("<")[0]
    return trait if found_for else ""


def _parse_impl_methods(impl_node, src: bytes) -> list[MethodInfo]:
    body = impl_node.child_by_field_name("body")
    if not body:
        return []
    return [_parse_fn(child, src) for child in body.children
            if child.type == "function_item"]


# ---------------------------------------------------------------------------
# struct / enum / trait parsing
# ---------------------------------------------------------------------------


def _parse_struct(node, src: bytes) -> ClassInfo:
    name = _ft(node, "name", src)
    body = node.child_by_field_name("body")
    class_vars: list[str] = []
    if body:
        for child in body.children:
            if child.type == "field_declaration":
                for c in child.children:
                    if c.type == "field_identifier":
                        class_vars.append(_t(c, src))
                        break
    return ClassInfo(
        name=name, kind="struct", bases=[], methods=[], class_vars=class_vars,
        line_start=_line(node), line_end=_end_line(node),
        docstring=_preceding_rust_doc(node, src),
    )


def _parse_enum(node, src: bytes) -> ClassInfo:
    name = _ft(node, "name", src)
    body = node.child_by_field_name("body")
    class_vars: list[str] = []
    if body:
        for child in body.children:
            if child.type == "enum_variant":
                vn = child.child_by_field_name("name")
                if vn:
                    class_vars.append(_t(vn, src))
    return ClassInfo(
        name=name, kind="enum", bases=[], methods=[], class_vars=class_vars,
        line_start=_line(node), line_end=_end_line(node),
        docstring=_preceding_rust_doc(node, src),
    )


def _parse_trait(node, src: bytes) -> ClassInfo:
    name = _ft(node, "name", src)
    body = node.child_by_field_name("body")
    methods: list[MethodInfo] = []
    if body:
        for child in body.children:
            if child.type in ("function_item", "function_signature_item"):
                methods.append(_parse_fn(child, src))
    return ClassInfo(
        name=name, kind="trait", bases=[], methods=methods, class_vars=[],
        line_start=_line(node), line_end=_end_line(node),
        docstring=_preceding_rust_doc(node, src),
    )


# ---------------------------------------------------------------------------
# import parsing
# ---------------------------------------------------------------------------


_RUST_INTERNAL_PREFIXES: frozenset[str] = frozenset({"crate", "self", "super"})


def _parse_use(node, src: bytes) -> ImportInfo:
    text = _t(node, src)
    raw = text.removeprefix("use ").rstrip(";").strip()
    # Flatten use tree syntax: "use foo::{A, B}" → treat as "foo::A" for module path
    parts = [p.strip() for p in raw.replace("{", "").replace("}", "").split("::") if p.strip()]
    is_relative = False
    level = 0
    if parts and parts[0] in _RUST_INTERNAL_PREFIXES:
        is_relative = True
        level = 1
        parts = parts[1:]  # strip crate:: / self:: / super:: prefix
    module = ".".join(parts)
    symbol = parts[-1] if parts else ""
    return ImportInfo(
        module=module,
        names=[symbol] if symbol and symbol not in ("*", "") else [],
        is_from=False,
        is_relative=is_relative,
        level=level,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_rust(path: str, content: str) -> CodeAnalysis:
    """Parse a Rust source file and return a CodeAnalysis. Never raises."""
    line_count = content.count("\n") + 1

    if not _AVAILABLE:
        return CodeAnalysis(
            path=path, language="rust", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                'tree-sitter-rust not installed — run: '
                'pip install "tree-sitter>=0.23.0" tree-sitter-rust'
            ],
        )

    try:
        parser = Parser(_RUST_LANGUAGE)
        src = content.encode("utf-8", errors="replace")
        tree = parser.parse(src)
        root = tree.root_node

        parse_errors: list[str] = []
        if root.has_error:
            parse_errors.append("File contains syntax errors (partial extraction attempted)")

        imports: list[ImportInfo] = []
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []
        type_map: dict[str, ClassInfo] = {}
        impl_queue: list = []

        for node in root.children:
            nt = node.type
            if nt == "use_declaration":
                imports.append(_parse_use(node, src))
            elif nt == "struct_item":
                cls = _parse_struct(node, src)
                if cls.name:
                    type_map[cls.name] = cls
                    classes.append(cls)
            elif nt == "enum_item":
                cls = _parse_enum(node, src)
                if cls.name:
                    type_map[cls.name] = cls
                    classes.append(cls)
            elif nt == "trait_item":
                cls = _parse_trait(node, src)
                if cls.name:
                    type_map[cls.name] = cls
                    classes.append(cls)
            elif nt == "type_item":
                name = _ft(node, "name", src)
                if name:
                    cls = ClassInfo(
                        name=name, kind="type", bases=[], methods=[], class_vars=[],
                        line_start=_line(node), line_end=_end_line(node),
                    )
                    type_map[name] = cls
                    classes.append(cls)
            elif nt == "impl_item":
                impl_queue.append(node)
            elif nt == "function_item":
                functions.append(_parse_fn_info(node, src))

        # Pass 2 — attach impl methods to their types + collect call graph
        for node in impl_queue:
            impl_type = _impl_type_name(node, src)
            trait_name = _impl_trait_name(node, src)
            methods = _parse_impl_methods(node, src)
            impl_calls = _collect_impl_calls_rust(node, src)

            if impl_type in type_map:
                existing = type_map[impl_type]
                existing.methods.extend(methods)
                existing.calls.extend(impl_calls)
                if trait_name and trait_name not in existing.bases:
                    existing.bases.append(trait_name)
            elif impl_type:
                # Synthetic entry for external or forward-declared types
                cls = ClassInfo(
                    name=impl_type,
                    kind="impl",
                    bases=[trait_name] if trait_name else [],
                    methods=methods,
                    class_vars=[],
                    calls=impl_calls,
                    line_start=_line(node),
                    line_end=_end_line(node),
                )
                type_map[impl_type] = cls
                classes.append(cls)

        return CodeAnalysis(
            path=path, language="rust", line_count=line_count,
            module_docstring="", classes=classes, functions=functions,
            imports=imports, all_exports=[], constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="rust", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"rust_analyzer internal error: {exc}"],
        )
