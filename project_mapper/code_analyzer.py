"""
project_mapper/code_analyzer.py
Python AST-based code structure extractor.

Given a file path and its content, extracts all structurally meaningful
information without any AI calls:
  - Module docstring
  - Classes (with methods, bases, decorators, class vars)
  - Top-level functions (with signatures, decorators, docstrings)
  - Imports (distinguishing internal vs. external, relative vs. absolute)
  - Module-level constants (__all__, UPPER_CASE names)
  - Parse errors (so callers can fall back gracefully)

Requires Python 3.9+ for ast.unparse().
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ImportInfo:
    module:      str         # "jwt", "core.auth.service", "" (for "from . import x")
    names:       list[str]   # [] for "import x", ["y","z"] for "from x import y,z"
    is_from:     bool        # True for "from X import Y"
    is_relative: bool        # True for "from . import ..."
    level:       int = 0     # number of leading dots in relative import
    alias:       str = ""    # "import jwt as j" → alias="j"


@dataclass
class ArgInfo:
    name:       str
    annotation: str = ""
    default:    str = ""


@dataclass
class MethodInfo:
    name:            str
    args:            list[str]       # parameter names only (brief)
    return_type:     str = ""
    decorators:      list[str] = field(default_factory=list)
    is_async:        bool = False
    is_property:     bool = False
    is_classmethod:  bool = False
    is_staticmethod: bool = False


@dataclass
class ClassInfo:
    name:        str
    bases:       list[str]
    methods:     list[MethodInfo]
    class_vars:  list[str]            # UPPER_CASE class-level names
    decorators:  list[str] = field(default_factory=list)
    docstring:   str = ""
    line_start:  int = 0
    line_end:    int = 0
    calls:       list[tuple[str, str]] = field(default_factory=list)  # (callee_name, via_method)
    kind:        str = ""             # "interface", "abstract", "enum", "struct", "record", "" …


@dataclass
class FunctionInfo:
    name:        str
    args:        list[ArgInfo]
    return_type: str = ""
    decorators:  list[str] = field(default_factory=list)
    docstring:   str = ""
    is_async:    bool = False
    line_start:  int = 0
    line_end:    int = 0
    calls:       list[tuple[str, str]] = field(default_factory=list)  # (callee_name, via_method)


@dataclass
class CodeAnalysis:
    path:             str              # relative path from project root
    language:         str              # "python", etc.
    line_count:       int
    module_docstring: str
    classes:          list[ClassInfo]
    functions:        list[FunctionInfo]   # top-level functions (public + private)
    imports:          list[ImportInfo]
    all_exports:      list[str]            # __all__ contents
    constants:        list[tuple[str, str]]  # (name, value_repr) for UPPER_CASE
    parse_errors:     list[str]
    module_calls:     list[tuple[str, str]] = field(default_factory=list)  # (callee_name, "module_level")


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _safe_unparse(node: ast.expr) -> str:
    """Convert an AST expression to source string; fall back to type name."""
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _node_to_str(node: ast.expr) -> str:
    """Simplified expression to string — handles Name, Attribute, Subscript."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_node_to_str(node.value)}.{node.attr}"
    return _safe_unparse(node)


def _decorator_name(dec: ast.expr) -> str:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return _node_to_str(dec)
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    return _safe_unparse(dec)


def _arg_info(arg: ast.arg, default_val: Optional[ast.expr] = None) -> ArgInfo:
    ann = _safe_unparse(arg.annotation) if arg.annotation else ""
    dflt = _safe_unparse(default_val) if default_val else ""
    return ArgInfo(name=arg.arg, annotation=ann, default=dflt)


def _is_upper(name: str) -> bool:
    """True for UPPER_CASE_NAMES (module constants)."""
    return bool(re.match(r"^[A-Z][A-Z0-9_]*$", name))


def _literal_repr(node: ast.expr) -> str:
    """Return a compact string representation of a simple literal."""
    try:
        val = ast.literal_eval(node)
        r = repr(val)
        return r[:80] + "…" if len(r) > 80 else r
    except Exception:
        return _safe_unparse(node)[:60]


# ---------------------------------------------------------------------------
# Call-graph extraction helpers
# ---------------------------------------------------------------------------

# Built-in names, stdlib types, and common non-class callables to ignore when
# extracting call-graph targets.  Keep this list broad so the ingestor doesn't
# create stubs for obvious non-project names.
_CALL_IGNORE: frozenset[str] = frozenset({
    # ---- builtins --------------------------------------------------------
    "print", "len", "range", "list", "dict", "set", "tuple", "str", "int",
    "float", "bool", "bytes", "bytearray", "memoryview", "complex",
    "type", "isinstance", "issubclass", "hasattr", "getattr", "setattr",
    "delattr", "super", "object", "staticmethod", "classmethod", "property",
    "enumerate", "zip", "map", "filter", "sorted", "reversed", "min", "max",
    "sum", "abs", "round", "pow", "divmod", "hex", "oct", "bin", "chr", "ord",
    "open", "next", "iter", "vars", "dir", "repr", "hash", "id", "callable",
    "any", "all", "format", "input", "eval", "exec", "compile", "breakpoint",
    "globals", "locals", "classmethod",
    # ---- exceptions ------------------------------------------------------
    "Exception", "BaseException", "NotImplementedError", "NotImplemented",
    "ValueError", "KeyError", "TypeError", "RuntimeError", "AttributeError",
    "OSError", "IOError", "FileNotFoundError", "PermissionError", "IsADirectoryError",
    "StopIteration", "StopAsyncIteration", "IndexError", "NameError",
    "AssertionError", "ImportError", "ModuleNotFoundError", "LookupError",
    "ArithmeticError", "ZeroDivisionError", "OverflowError", "MemoryError",
    "RecursionError", "TimeoutError", "ConnectionError", "BrokenPipeError",
    "GeneratorExit", "SystemExit", "KeyboardInterrupt", "UnicodeError",
    "UnicodeDecodeError", "UnicodeEncodeError", "BufferError", "EOFError",
    "DeprecationWarning", "UserWarning", "FutureWarning", "Warning",
    # ---- typing ----------------------------------------------------------
    "Optional", "Dict", "List", "Set", "FrozenSet", "Tuple", "Union",
    "Callable", "Any", "Type", "ClassVar", "Final", "Literal",
    "TypeVar", "TypeVarTuple", "ParamSpec", "Protocol", "TypeAlias",
    "Generator", "Iterator", "Iterable", "AsyncGenerator", "AsyncIterator",
    "AsyncIterable", "Awaitable", "Coroutine", "Sequence", "MutableSequence",
    "Mapping", "MutableMapping", "AbstractSet", "MutableSet",
    "TypedDict", "NamedTuple", "overload", "cast", "dataclass",
    "Generic", "Annotated", "get_type_hints", "get_origin", "get_args",
    # ---- stdlib classes --------------------------------------------------
    "Path", "PurePath", "PosixPath", "WindowsPath",
    "datetime", "date", "time", "timedelta", "timezone",
    "deque", "defaultdict", "OrderedDict", "Counter", "ChainMap",
    "Thread", "Lock", "RLock", "Event", "Condition", "Semaphore",
    "Queue", "PriorityQueue", "LifoQueue",
    "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "auto",
    "ABC", "ABCMeta", "abstractmethod",
    "StringIO", "BytesIO", "TextIOWrapper",
    "re", "Pattern", "Match",
    # ---- common third-party base classes / decorators --------------------
    "BaseModel", "BaseSettings", "Field", "validator", "root_validator",
    "model_validator", "field_validator", "ConfigDict",
    "dataclasses",
    # ---- FastAPI / Starlette / HTTP --------------------------------------
    "FastAPI", "APIRouter", "Request", "Response", "JSONResponse",
    "HTMLResponse", "StreamingResponse", "FileResponse", "RedirectResponse",
    "HTTPException", "WebSocket", "BackgroundTasks", "Depends",
    "Body", "Query", "Path", "Header", "Cookie", "Form", "File", "UploadFile",
    "status",
    # ---- asyncio ---------------------------------------------------------
    "asyncio", "Task", "Future", "Event", "gather", "sleep", "create_task",
    "get_event_loop", "run", "wait", "wait_for", "shield", "timeout",
    # ---- logging / misc --------------------------------------------------
    "Logger", "LogRecord", "Formatter", "Handler", "StreamHandler",
    "NullHandler", "FileHandler",
    "UUID", "Decimal", "Fraction",
    "json", "os", "sys", "re", "math", "random", "copy", "functools",
})


# ---------------------------------------------------------------------------
# Factory-function heuristics (shared by _SelfAssignExtractor + _CallExtractor)
# ---------------------------------------------------------------------------

_FACTORY_PREFIXES: tuple[str, ...] = (
    "get_", "create_", "build_", "make_", "load_", "init_", "setup_",
)


def _factory_to_class_name(fname: str) -> str:
    """
    Convert a factory function name to its likely class name.
      'get_provider_manager'  → 'ProviderManager'
      'create_task_queue'     → 'TaskQueue'
      'build_response'        → 'Response'
    """
    for prefix in _FACTORY_PREFIXES:
        if fname.startswith(prefix):
            remainder = fname[len(prefix):]
            if remainder:
                return "".join(w.capitalize() for w in remainder.split("_"))
    return ""


def _resolve_func_to_class(func: ast.expr) -> str:
    """
    Given the func node of an ast.Call, return the likely class name being
    instantiated or obtained, or an empty string if it can't be determined.

    Handles:
      SomeClass(...)           → 'SomeClass'
      get_provider_manager()   → 'ProviderManager'
      module.SomeClass(...)    → 'SomeClass'
      module.get_something()   → 'Something'
    """
    if isinstance(func, ast.Name):
        name = func.id
        if name and name[0].isupper() and name not in _CALL_IGNORE:
            return name
        candidate = _factory_to_class_name(name)
        if candidate and candidate not in _CALL_IGNORE:
            return candidate
    elif isinstance(func, ast.Attribute):
        attr = func.attr
        if attr and attr[0].isupper() and attr not in _CALL_IGNORE:
            return attr
        candidate = _factory_to_class_name(attr)
        if candidate and candidate not in _CALL_IGNORE:
            return candidate
    return ""


class _SelfAssignExtractor(ast.NodeVisitor):
    """
    Extract self.X = SomeClass(...) or self.X = get_something() assignments
    from any method body, mapping the attribute name to the resolved class name.
    """

    def __init__(self) -> None:
        self.attr_to_class: dict[str, str] = {}   # attr_name → ClassName

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if not (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"):
                continue
            attr = target.attr
            if isinstance(node.value, ast.Call):
                resolved = _resolve_func_to_class(node.value.func)
                if resolved:
                    self.attr_to_class[attr] = resolved
        self.generic_visit(node)


class _CallExtractor(ast.NodeVisitor):
    """
    Walk a method body and collect:
      - instantiated: class names obtained by direct instantiation, factory calls,
                      or class-level attribute access
      - attr_calls:   self.X.method(...) → X is a stored-object attribute
    """

    def __init__(self) -> None:
        self.instantiated: set[str] = set()
        self.attr_calls:   set[str] = set()
        self.fn_calls:     set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func

        if isinstance(func, ast.Name):
            name = func.id
            # UpperCaseName(...) — direct class instantiation
            if name and name[0].isupper() and name not in _CALL_IGNORE:
                self.instantiated.add(name)
            # get_something() / create_something() anywhere in method body —
            # the *local variable* pattern: pm = get_provider_manager()
            # We don't need to track what variable it's assigned to; just
            # knowing the class was obtained here is enough.
            else:
                candidate = _factory_to_class_name(name)
                if candidate and candidate not in _CALL_IGNORE:
                    self.instantiated.add(candidate)
                elif name and name[0].islower() and name not in _CALL_IGNORE:
                    # Direct call to a lowercase function — may be intra-file.
                    # The ingestor will only wire a relation if the name is indexed.
                    self.fn_calls.add(name)

        elif isinstance(func, ast.Attribute):
            obj  = func.value
            attr = func.attr

            # self.X.method(...) — X is a stored object attribute
            if (isinstance(obj, ast.Attribute)
                    and isinstance(obj.value, ast.Name)
                    and obj.value.id == "self"
                    and not obj.attr.startswith("_")):
                self.attr_calls.add(obj.attr)

            # SomeName.method(...) — SomeName looks like a class/module name
            elif (isinstance(obj, ast.Name)
                  and obj.id != "self"
                  and obj.id and obj.id[0].isupper()
                  and obj.id not in _CALL_IGNORE):
                self.instantiated.add(obj.id)

            # module.get_something() or module.SomeClass() — attribute factory/class
            elif isinstance(obj, ast.Name) and obj.id != "self":
                candidate = _resolve_func_to_class(func)
                if candidate and candidate not in _CALL_IGNORE:
                    self.instantiated.add(candidate)

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id and node.id[0].isupper() and not node.id.isupper() and node.id not in _CALL_IGNORE:
            self.instantiated.add(node.id)
        self.generic_visit(node)


_UPPERWORD_PAT = re.compile(r'\b[A-Z][a-zA-Z0-9_]*\b')

def _extract_classes_from_type_annotation(annotation: str) -> set[str]:
    if not annotation:
        return set()
    found = set()
    for word in _UPPERWORD_PAT.findall(annotation):
        if word not in _CALL_IGNORE:
            found.add(word)
    return found


def _extract_function_calls(
    fn_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, str]]:
    """
    Return a deduplicated list of (callee_name, via_method) tuples for the
    classes/objects that *fn_node* directly calls or instantiates.

    For a top-level function, via_method is always the function's own name.
    """
    extractor = _CallExtractor()
    extractor.visit(fn_node)

    resolved: set[str] = set(extractor.instantiated)
    resolved.update(extractor.fn_calls)

    # attr_calls from a top-level function are unresolvable (no self),
    # but keep uppercase ones as potential class names
    for attr in extractor.attr_calls:
        if attr and attr[0].isupper() and not attr.isupper():
            resolved.add(attr)

    # Extract class names from type annotations of arguments
    for arg in fn_node.args.args:
        if arg.annotation:
            ann_str = _safe_unparse(arg.annotation)
            resolved.update(_extract_classes_from_type_annotation(ann_str))

    # Extract class names from return type annotation
    if fn_node.returns:
        ann_str = _safe_unparse(fn_node.returns)
        resolved.update(_extract_classes_from_type_annotation(ann_str))

    resolved -= _CALL_IGNORE
    return [(name, fn_node.name) for name in sorted(resolved)]


def _extract_class_calls(
    class_node: ast.ClassDef,
) -> list[tuple[str, str]]:
    """
    Return a deduplicated list of (callee_name, via_method) tuples describing
    which classes *class_node* calls and from which of its methods.

    Strategy:
      1. From all methods, build a mapping: self.X → ClassName (via assignment)
      2. Per method, extract:
         a. Direct UpperCaseName() instantiations
         b. self.X.method() patterns → attribute X
      3. Resolve attr → class name where the mapping exists.
      4. Filter out the class itself and common primitives.

    The same callee may appear multiple times if it is called from multiple
    methods — each occurrence gets its own (callee, method) tuple.
    Duplicate (callee, method) pairs within the same method are de-duped.
    """
    # Step 1: build attr → class map across ALL methods
    attr_to_class: dict[str, str] = {}
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            extractor = _SelfAssignExtractor()
            extractor.visit(item)
            attr_to_class.update(extractor.attr_to_class)

    # Step 2 + 3: extract per-method, preserving source method name
    result:  list[tuple[str, str]] = []
    seen:    set[tuple[str, str]]  = set()

    for item in class_node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        method_name = item.name
        extractor   = _CallExtractor()
        extractor.visit(item)

        callees = set(extractor.instantiated)
        callees.update(extractor.fn_calls)

        # Attribute-based calls → resolve via attr_to_class
        for attr in extractor.attr_calls:
            callee = attr_to_class.get(attr, attr)
            callees.add(callee)

        # Extract class names from type annotations of arguments
        for arg in item.args.args:
            if arg.annotation:
                ann_str = _safe_unparse(arg.annotation)
                callees.update(_extract_classes_from_type_annotation(ann_str))

        # Extract class names from return type annotation
        if item.returns:
            ann_str = _safe_unparse(item.returns)
            callees.update(_extract_classes_from_type_annotation(ann_str))

        callees -= _CALL_IGNORE

        for callee in sorted(callees):
            pair = (callee, method_name)
            if pair not in seen:
                seen.add(pair)
                result.append(pair)

    # Step 4: filter
    own_name = class_node.name
    return [
        (callee, method)
        for callee, method in result
        if callee != own_name and callee not in _CALL_IGNORE
    ]


# ---------------------------------------------------------------------------
# Python AST visitor
# ---------------------------------------------------------------------------

class _PythonVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes:      list[ClassInfo] = []
        self.functions:    list[FunctionInfo] = []
        self.imports:      list[ImportInfo] = []
        self.all_exports:  list[str] = []
        self.constants:    list[tuple[str, str]] = []
        self.module_calls: list[tuple[str, str]] = []
        self._class_stack: list[str] = []   # track nesting

    def _in_class(self) -> bool:
        return bool(self._class_stack)

    # ------------------------------------------------------------------
    # Module-level calls (statements outside any function/class body)
    # ------------------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:
        _skip = (
            ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
            ast.Import, ast.ImportFrom,
        )
        seen: set[str] = set()
        for stmt in node.body:
            if isinstance(stmt, _skip):
                continue
            ext = _CallExtractor()
            ext.visit(stmt)
            for name in ext.instantiated | ext.fn_calls:
                if name not in seen:
                    seen.add(name)
                    self.module_calls.append((name, "module_level"))
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportInfo(
                module=alias.name,
                names=[],
                is_from=False,
                is_relative=False,
                level=0,
                alias=alias.asname or "",
            ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        level  = node.level or 0
        names  = [a.name for a in node.names]
        self.imports.append(ImportInfo(
            module=module,
            names=names,
            is_from=True,
            is_relative=(level > 0),
            level=level,
        ))
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Only process top-level classes
        if self._in_class():
            self.generic_visit(node)
            return

        bases      = [_node_to_str(b) for b in node.bases]
        decorators = [_decorator_name(d) for d in node.decorator_list]
        docstring  = ast.get_docstring(node) or ""

        methods:    list[MethodInfo] = []
        class_vars: list[str] = []

        self._class_stack.append(node.name)
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m = self._build_method(item)
                methods.append(m)
            elif isinstance(item, ast.Assign):
                for t in item.targets:
                    if isinstance(t, ast.Name) and _is_upper(t.id):
                        class_vars.append(t.id)
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name) and _is_upper(item.target.id):
                    class_vars.append(item.target.id)
        self._class_stack.pop()

        end_line = getattr(node, "end_lineno", node.lineno)
        calls    = _extract_class_calls(node)
        self.classes.append(ClassInfo(
            name=node.name,
            bases=bases,
            methods=methods,
            class_vars=class_vars,
            decorators=decorators,
            docstring=docstring[:300],
            line_start=node.lineno,
            line_end=end_line,
            calls=calls,
        ))

    def _build_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
        decs      = [_decorator_name(d) for d in node.decorator_list]
        args      = [a.arg for a in node.args.args if a.arg != "self" and a.arg != "cls"]
        ret_type  = _safe_unparse(node.returns) if node.returns else ""
        is_async  = isinstance(node, ast.AsyncFunctionDef)
        is_prop   = "property" in decs
        is_cm     = "classmethod" in decs
        is_sm     = "staticmethod" in decs
        return MethodInfo(
            name=node.name,
            args=args,
            return_type=ret_type,
            decorators=decs,
            is_async=is_async,
            is_property=is_prop,
            is_classmethod=is_cm,
            is_staticmethod=is_sm,
        )

    # ------------------------------------------------------------------
    # Top-level functions
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self._in_class():
            self._record_function(node, is_async=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not self._in_class():
            self._record_function(node, is_async=True)
        self.generic_visit(node)

    def _record_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool,
    ) -> None:
        decs      = [_decorator_name(d) for d in node.decorator_list]
        docstring = ast.get_docstring(node) or ""
        ret_type  = _safe_unparse(node.returns) if node.returns else ""

        # Build args list with defaults aligned
        all_args   = node.args.args
        defaults   = node.args.defaults
        # defaults are right-aligned: last len(defaults) args have defaults
        pad        = len(all_args) - len(defaults)
        args: list[ArgInfo] = []
        for i, arg in enumerate(all_args):
            dflt_node = defaults[i - pad] if i >= pad else None
            args.append(_arg_info(arg, dflt_node))

        end_line   = getattr(node, "end_lineno", node.lineno)
        fn_calls   = _extract_function_calls(node)
        self.functions.append(FunctionInfo(
            name=node.name,
            args=args,
            return_type=ret_type,
            decorators=decs,
            docstring=docstring[:200],
            is_async=is_async,
            line_start=node.lineno,
            line_end=end_line,
            calls=fn_calls,
        ))

    # ------------------------------------------------------------------
    # Module-level assignments: constants + __all__
    # ------------------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._in_class():
            self.generic_visit(node)
            return
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if name == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    self.all_exports = [
                        elt.s if isinstance(elt, ast.Constant) and isinstance(elt.s, str)
                        else _safe_unparse(elt)
                        for elt in node.value.elts
                    ]
            elif _is_upper(name):
                self.constants.append((name, _literal_repr(node.value)))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self._in_class():
            if isinstance(node.target, ast.Name) and _is_upper(node.target.id):
                val_repr = _literal_repr(node.value) if node.value else ""
                self.constants.append((node.target.id, val_repr))
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Public analysis functions
# ---------------------------------------------------------------------------

def analyze_python(path: str, content: str) -> CodeAnalysis:
    """
    Parse *content* as Python source and return a CodeAnalysis.
    Never raises — parse errors are collected in CodeAnalysis.parse_errors.
    """
    line_count   = content.count("\n") + 1
    parse_errors: list[str] = []

    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        return CodeAnalysis(
            path=path, language="python", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"SyntaxError: {exc}"],
        )
    except Exception as exc:
        return CodeAnalysis(
            path=path, language="python", line_count=line_count,
            module_docstring="", classes=[], functions=[], imports=[],
            all_exports=[], constants=[],
            parse_errors=[f"ParseError: {exc}"],
        )

    module_docstring = ast.get_docstring(tree) or ""

    visitor = _PythonVisitor()
    try:
        visitor.visit(tree)
    except Exception as exc:
        parse_errors.append(f"VisitorError: {exc}")

    return CodeAnalysis(
        path=path,
        language="python",
        line_count=line_count,
        module_docstring=module_docstring[:500],
        classes=visitor.classes,
        functions=visitor.functions,
        imports=visitor.imports,
        all_exports=visitor.all_exports,
        constants=visitor.constants[:30],
        parse_errors=parse_errors,
        module_calls=visitor.module_calls,
    )


_LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".java": "java", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c": "c", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".go": "go", ".rs": "rust", ".php": "php",
    ".cs": "csharp", ".swift": "swift", ".kt": "kotlin",
}


def detect_language_for_path(path: str) -> str:
    """Return a language slug for the given file path."""
    return _LANGUAGE_BY_EXT.get(Path(path).suffix.lower(), "")


def analyze_file(path: str, content: str, language: str = "") -> CodeAnalysis:
    """
    Route to the appropriate language analyzer.
    Language is auto-detected from the path if not provided.
    Falls back to a line-count stub for unsupported file types.
    """
    if not language:
        language = detect_language_for_path(path)
    if language == "python":
        return analyze_python(path, content)
    if language in ("typescript", "javascript"):
        from .ts_analyzer import analyze_typescript
        return analyze_typescript(path, content, language)
    if language == "java":
        from .java_analyzer import analyze_java
        return analyze_java(path, content)
    if language == "go":
        from .go_analyzer import analyze_go
        return analyze_go(path, content)
    if language == "csharp":
        from .csharp_analyzer import analyze_csharp
        return analyze_csharp(path, content)
    if language == "rust":
        from .rust_analyzer import analyze_rust
        return analyze_rust(path, content)
    if language in ("c", "cpp"):
        if language == "c":
            from .c_analyzer import analyze_c
            return analyze_c(path, content)
        from .cpp_analyzer import analyze_cpp
        return analyze_cpp(path, content)
    if language == "php":
        from .php_analyzer import analyze_php
        return analyze_php(path, content)
    if language == "ruby":
        from .ruby_analyzer import analyze_ruby
        return analyze_ruby(path, content)
    if language == "kotlin":
        from .kotlin_analyzer import analyze_kotlin
        return analyze_kotlin(path, content)
    if language == "swift":
        from .swift_analyzer import analyze_swift
        return analyze_swift(path, content)
    # Minimal stub for unsupported file types
    return CodeAnalysis(
        path=path,
        language=language or "unknown",
        line_count=content.count("\n") + 1,
        module_docstring="",
        classes=[],
        functions=[],
        imports=[],
        all_exports=[],
        constants=[],
        parse_errors=[],
    )


def build_compact_summary(analysis: CodeAnalysis) -> str:
    """
    Build a compact, LLM-friendly structured text summary of a CodeAnalysis.
    Designed to fit well within a prompt without wasting tokens.
    """
    lines: list[str] = []
    lines.append(f"Module: {analysis.path} ({analysis.language}, {analysis.line_count} lines)")

    if analysis.module_docstring:
        lines.append(f"Docstring: {analysis.module_docstring[:300]}")

    if analysis.classes:
        lines.append("\nClasses:")
        for cls in analysis.classes:
            bases_str = f"({', '.join(cls.bases)})" if cls.bases else ""
            lines.append(f"  {cls.name}{bases_str}")
            if cls.docstring:
                lines.append(f"    \"{cls.docstring[:120]}\"")
            public_methods = [m for m in cls.methods if not m.name.startswith("_") or m.name.startswith("__") and m.name.endswith("__")]
            if public_methods:
                meth_strs = []
                for m in public_methods[:8]:
                    sig = f"{m.name}({', '.join(m.args)})"
                    if m.return_type:
                        sig += f" -> {m.return_type}"
                    if m.is_async:
                        sig = "[async] " + sig
                    if m.is_property:
                        sig = "@property " + sig
                    meth_strs.append(sig)
                lines.append(f"    Methods: {', '.join(meth_strs)}")
            if cls.class_vars:
                lines.append(f"    Class vars: {', '.join(cls.class_vars[:6])}")

    if analysis.functions:
        lines.append("\nTop-level Functions:")
        for fn in analysis.functions[:12]:
            arg_strs = []
            for a in fn.args[:6]:
                s = a.name
                if a.annotation:
                    s += f": {a.annotation}"
                if a.default:
                    s += f" = {a.default}"
                arg_strs.append(s)
            sig = f"  {fn.name}({', '.join(arg_strs)})"
            if fn.return_type:
                sig += f" -> {fn.return_type}"
            if fn.is_async:
                sig = "  [async]" + sig[1:]
            lines.append(sig)
            if fn.docstring:
                lines.append(f"    \"{fn.docstring[:100]}\"")

    # Partition imports
    int_imps = [i for i in analysis.imports if _could_be_internal(i)]
    ext_imps = [i for i in analysis.imports if not _could_be_internal(i)]

    if int_imps:
        names = [i.module or ("." * i.level) for i in int_imps[:10]]
        lines.append(f"\nInternal Imports: {', '.join(filter(None, names))}")
    if ext_imps:
        names = list(dict.fromkeys(i.module.split(".")[0] for i in ext_imps if i.module))[:12]
        lines.append(f"External Dependencies: {', '.join(names)}")

    if analysis.all_exports:
        lines.append(f"\n__all__: {', '.join(analysis.all_exports[:10])}")

    if analysis.constants:
        const_strs = [f"{n} = {v}" for n, v in analysis.constants[:8]]
        lines.append(f"Constants: {', '.join(const_strs)}")

    if analysis.parse_errors:
        lines.append(f"\nParse Warnings: {'; '.join(analysis.parse_errors)}")

    return "\n".join(lines)


def _could_be_internal(imp: ImportInfo) -> bool:
    """Heuristic: relative imports are always internal; absolute imports with
    known stdlib top-level names are external. Everything else is ambiguous
    (treated as potentially internal for display purposes in the summary)."""
    if imp.is_relative:
        return True
    if not imp.module:
        return False
    first = imp.module.split(".")[0]
    return first not in _STDLIB_TOP_LEVEL


# ---------------------------------------------------------------------------
# Known stdlib top-level package names (Python 3.10 stdlib)
# ---------------------------------------------------------------------------

_STDLIB_TOP_LEVEL: frozenset[str] = frozenset({
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii",
    "binhex", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
    "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "csv", "ctypes",
    "curses", "dataclasses", "datetime", "dbm", "decimal", "difflib",
    "dis", "distutils", "doctest", "email", "encodings", "enum",
    "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
    "gettext", "glob", "grp", "gzip", "hashlib", "heapq", "hmac",
    "html", "http", "idlelib", "imaplib", "imghdr", "imp", "importlib",
    "inspect", "io", "ipaddress", "itertools", "json", "keyword",
    "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox",
    "marshal", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
    "netrc", "nis", "nntplib", "numbers", "operator", "optparse",
    "os", "ossaudiodev", "pathlib", "pdb", "pickle", "pickletools",
    "pipes", "pkgutil", "platform", "plistlib", "poplib", "posix",
    "posixpath", "pprint", "profile", "pstats", "pty", "pwd", "py_compile",
    "pyclbr", "pydoc", "queue", "quopri", "random", "re", "readline",
    "reprlib", "resource", "rlcompleter", "runpy", "sched", "secrets",
    "select", "selectors", "shelve", "shlex", "shutil", "signal",
    "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver",
    "spwd", "sqlite3", "sre_compile", "sre_constants", "sre_parse",
    "ssl", "stat", "statistics", "string", "stringprep", "struct",
    "subprocess", "sunau", "symtable", "sys", "sysconfig", "syslog",
    "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
    "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty",
    "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
    "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp",
    "zipfile", "zipimport", "zlib", "zoneinfo",
    # Common third-party that look like stdlib
    "typing_extensions",
})
