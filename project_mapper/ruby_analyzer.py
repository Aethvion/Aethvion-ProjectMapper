"""
core/project_mapper/ruby_analyzer.py
Ruby source-file analyzer using tree-sitter.

Entity kinds extracted:
  ""        — class (default)
  "module"  — Ruby module

Handles:
  - class / module definitions
  - instance methods (def) and class-level singleton methods (def self.foo)
  - superclass inheritance
  - require / require_relative / include / extend imports

Dependencies (optional — falls back to stub if not installed):
  pip install "tree-sitter>=0.23.0" tree-sitter-ruby
"""

from __future__ import annotations

try:
    from tree_sitter import Language, Parser
    import tree_sitter_ruby as _tsrb
    _RUBY_LANGUAGE = Language(_tsrb.language())
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
# call graph extraction
# ---------------------------------------------------------------------------

_RUBY_IMPORT_METHODS: frozenset[str] = frozenset({"require", "require_relative", "include", "extend"})


def _collect_calls_rb(body_node, src: bytes) -> list[tuple[str, str]]:
    """Walk a Ruby method body and return (callee_name, "") for each call."""
    if body_node is None:
        return []
    calls: list[tuple[str, str]] = []

    def _walk(node):
        if node.type == "call":
            method_node = node.child_by_field_name("method")
            if method_node:
                name = _t(method_node, src).rstrip("!?")
                if name and name not in _RUBY_IMPORT_METHODS and name.isidentifier():
                    calls.append((name, ""))
        for c in node.children:
            _walk(c)

    _walk(body_node)
    return calls


# ---------------------------------------------------------------------------
# parameter parsing
# ---------------------------------------------------------------------------


def _parse_rb_params(params_node, src: bytes) -> list[str]:
    """Extract parameter names from method_parameters."""
    if params_node is None:
        return []
    names: list[str] = []
    for child in params_node.children:
        nt = child.type
        if nt in ("identifier", "optional_parameter", "splat_parameter",
                  "hash_splat_parameter", "block_parameter",
                  "keyword_parameter"):
            # For simple params the node IS the identifier;
            # for typed/optional the `name` field gives the identifier.
            name_node = child.child_by_field_name("name")
            if name_node:
                names.append(_t(name_node, src).lstrip("*&:"))
            elif child.type == "identifier":
                names.append(_t(child, src))
    return names


# ---------------------------------------------------------------------------
# method parsing
# ---------------------------------------------------------------------------


def _parse_method(node, src: bytes) -> MethodInfo | None:
    """Parse a `method` node."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    params_node = node.child_by_field_name("parameters")
    args = _parse_rb_params(params_node, src)

    return MethodInfo(name=name, args=args)


def _parse_singleton_method(node, src: bytes) -> MethodInfo | None:
    """Parse a `singleton_method` node (def self.foo)."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    params_node = node.child_by_field_name("parameters")
    args = _parse_rb_params(params_node, src)

    return MethodInfo(name=name, args=args, is_classmethod=True)


# ---------------------------------------------------------------------------
# class / module parsing
# ---------------------------------------------------------------------------


def _parse_class_or_module(node, src: bytes, kind: str) -> ClassInfo | None:
    """Parse a `class` or `module` node."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _t(name_node, src)

    # Superclass
    bases: list[str] = []
    superclass_node = node.child_by_field_name("superclass")
    if superclass_node:
        for c in superclass_node.children:
            if c.type in ("constant", "scope_resolution"):
                bases.append(_t(c, src))
                break

    # Body
    body = node.child_by_field_name("body")
    methods: list[MethodInfo] = []
    class_vars: list[str] = []
    calls: list[tuple[str, str]] = []

    if body:
        _collect_body(body, src, methods, class_vars, calls)

    return ClassInfo(
        name=name, kind=kind, bases=bases, methods=methods, class_vars=class_vars,
        calls=calls,
        line_start=_line(node), line_end=_end_line(node),
    )


def _collect_body(body_node, src: bytes,
                  methods: list[MethodInfo],
                  class_vars: list[str],
                  calls: list[tuple[str, str]]) -> None:
    """Collect methods, constants, and call graph from a class/module body."""
    for child in body_node.children:
        nt = child.type
        if nt == "method":
            m = _parse_method(child, src)
            if m:
                methods.append(m)
            calls.extend(_collect_calls_rb(child.child_by_field_name("body"), src))
        elif nt == "singleton_method":
            m = _parse_singleton_method(child, src)
            if m:
                methods.append(m)
            calls.extend(_collect_calls_rb(child.child_by_field_name("body"), src))
        elif nt == "assignment":
            # Capture CONSTANT = ... as class_vars
            target = child.child_by_field_name("left")
            if target and target.type == "constant":
                class_vars.append(_t(target, src))


# ---------------------------------------------------------------------------
# import (require / require_relative / include / extend) parsing
# ---------------------------------------------------------------------------


def _try_parse_require(node, src: bytes) -> ImportInfo | None:
    """Attempt to parse a `call` node as require/require_relative."""
    method_node = node.child_by_field_name("method")
    if not method_node:
        return None
    method_name = _t(method_node, src)
    if method_name not in ("require", "require_relative", "include", "extend"):
        return None

    args_node = node.child_by_field_name("arguments")
    if not args_node:
        return None

    for c in args_node.children:
        if c.type == "string":
            # String content child or the whole string text
            content_node = c.child_by_field_name("content")
            raw = _t(content_node, src) if content_node else _t(c, src).strip("'\"`")
            is_rel = method_name == "require_relative"
            return ImportInfo(
                module=raw, names=[], is_from=False, is_relative=is_rel,
            )
        elif c.type in ("constant", "scope_resolution"):
            # include / extend with module constant
            mod = _t(c, src)
            return ImportInfo(
                module=mod, names=[mod], is_from=False, is_relative=False,
            )
    return None


# ---------------------------------------------------------------------------
# recursive walker
# ---------------------------------------------------------------------------


def _walk(node, src: bytes,
          classes: list[ClassInfo],
          functions: list[FunctionInfo],
          imports: list[ImportInfo],
          depth: int = 0) -> None:
    """
    Walk a Ruby AST node recursively.
    Recurses into class / module bodies to capture nested definitions.
    """
    for child in node.children:
        nt = child.type
        if nt == "class":
            cls = _parse_class_or_module(child, src, kind="")
            if cls:
                classes.append(cls)
            # Recurse into body for nested classes/modules
            body = child.child_by_field_name("body")
            if body:
                _walk(body, src, classes, functions, imports, depth + 1)
        elif nt == "module":
            cls = _parse_class_or_module(child, src, kind="module")
            if cls:
                classes.append(cls)
            body = child.child_by_field_name("body")
            if body:
                _walk(body, src, classes, functions, imports, depth + 1)
        elif nt == "method" and depth == 0:
            # Only capture truly top-level (not inside any class) methods as functions
            m = _parse_method(child, src)
            if m:
                fn_calls = _collect_calls_rb(child.child_by_field_name("body"), src)
                functions.append(FunctionInfo(
                    name=m.name,
                    args=[ArgInfo(name=a) for a in m.args],
                    calls=fn_calls,
                    line_start=_line(child),
                    line_end=_end_line(child),
                ))
        elif nt == "call":
            imp = _try_parse_require(child, src)
            if imp:
                imports.append(imp)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_ruby(path: str, content: str) -> CodeAnalysis:
    """Parse a Ruby source file and return a CodeAnalysis. Never raises."""
    line_count = content.count("\n") + 1

    if not _AVAILABLE:
        return CodeAnalysis(
            path=path, language="ruby", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[
                'tree-sitter-ruby not installed — run: '
                'pip install "tree-sitter>=0.23.0" tree-sitter-ruby'
            ],
        )

    try:
        parser = Parser(_RUBY_LANGUAGE)
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
            path=path, language="ruby", line_count=line_count,
            module_docstring="", classes=classes, functions=functions,
            imports=imports, all_exports=[], constants=[],
            parse_errors=parse_errors,
        )

    except Exception as exc:
        return CodeAnalysis(
            path=path, language="ruby", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"ruby_analyzer internal error: {exc}"],
        )
