"""
project_mapper/csharp_analyzer.py
C# code structure extractor using tree-sitter.

Extracts the same CodeAnalysis structure as base.py so the
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

from .base import (
    ClassInfo,
    CodeAnalysis,
    FunctionInfo,
    ImportInfo,
    MethodInfo,
)

# ---------------------------------------------------------------------------
# tree-sitter availability — soft dependency
# ---------------------------------------------------------------------------

_TREESITTER_AVAILABLE = False
_CS_LANGUAGE = None

try:
    import tree_sitter_c_sharp as _tscs
    from tree_sitter import Language, Parser

    _CS_LANGUAGE = Language(_tscs.language())
    _TREESITTER_AVAILABLE = True
except Exception:
    pass


# ---------------------------------------------------------------------------
# C# standard-library and Unity Engine types to skip in call graphs
# ---------------------------------------------------------------------------

_CS_IGNORE: frozenset[str] = frozenset(
    {
        # System
        "Object",
        "String",
        "Int16",
        "Int32",
        "Int64",
        "UInt16",
        "UInt32",
        "UInt64",
        "Single",
        "Double",
        "Boolean",
        "Char",
        "Byte",
        "SByte",
        "Decimal",
        "DateTime",
        "DateTimeOffset",
        "TimeSpan",
        "Guid",
        "Array",
        "List",
        "Dictionary",
        "HashSet",
        "Queue",
        "Stack",
        "LinkedList",
        "SortedDictionary",
        "SortedList",
        "SortedSet",
        "ConcurrentDictionary",
        "ConcurrentQueue",
        "ConcurrentBag",
        "IEnumerable",
        "IEnumerator",
        "IList",
        "ICollection",
        "IReadOnlyList",
        "IReadOnlyCollection",
        "IReadOnlyDictionary",
        "IDictionary",
        "ISet",
        "IComparable",
        "IEquatable",
        "IDisposable",
        "IAsyncDisposable",
        "ICloneable",
        "IFormattable",
        "Task",
        "ValueTask",
        "CancellationToken",
        "CancellationTokenSource",
        "Exception",
        "SystemException",
        "InvalidOperationException",
        "ArgumentException",
        "ArgumentNullException",
        "ArgumentOutOfRangeException",
        "NotImplementedException",
        "NotSupportedException",
        "NullReferenceException",
        "IndexOutOfRangeException",
        "KeyNotFoundException",
        "FormatException",
        "IOException",
        "StringBuilder",
        "Stream",
        "MemoryStream",
        "FileStream",
        "StreamReader",
        "StreamWriter",
        "Nullable",
        "Lazy",
        "Tuple",
        "ValueTuple",
        "Math",
        "Console",
        "Convert",
        "BitConverter",
        "Encoding",
        "Environment",
        "GC",
        "Thread",
        "Mutex",
        "Semaphore",
        "SemaphoreSlim",
        "Interlocked",
        "Stopwatch",
        "Regex",
        "Match",
        "File",
        "Directory",
        "Path",
        "Action",
        "Func",
        "Predicate",
        "Comparison",
        "EventHandler",
        "Enumerable",
        "Type",
        "Activator",
        "Attribute",
        "FlagsAttribute",
        "SerializableAttribute",
        "ObsoleteAttribute",
        # ASP.NET Core common base types
        "Controller",
        "ControllerBase",
        "PageModel",
        "Hub",
        "BackgroundService",
        "Middleware",
        "FilterAttribute",
        # Microsoft.Extensions
        "ILogger",
        "IConfiguration",
        "IServiceCollection",
        "IServiceProvider",
        "IOptions",
        "IHostedService",
        # UnityEngine / UnityEditor / TMPro / UI built-ins
        "MonoBehaviour",
        "ScriptableObject",
        "GameObject",
        "Transform",
        "RectTransform",
        "Component",
        "Behaviour",
        "Coroutine",
        "YieldInstruction",
        "CustomYieldInstruction",
        "WaitForSeconds",
        "WaitForSecondsRealtime",
        "WaitForEndOfFrame",
        "WaitForFixedUpdate",
        "WaitUntil",
        "WaitWhile",
        "AsyncOperation",
        "Vector2",
        "Vector3",
        "Vector4",
        "Vector2Int",
        "Vector3Int",
        "Quaternion",
        "Matrix4x4",
        "Color",
        "Color32",
        "Gradient",
        "AnimationCurve",
        "Rect",
        "RectInt",
        "Bounds",
        "BoundsInt",
        "Ray",
        "Ray2D",
        "Plane",
        "RaycastHit",
        "RaycastHit2D",
        "ContactPoint",
        "ContactPoint2D",
        "Collision",
        "Collision2D",
        "LayerMask",
        "Mathf",
        "Time",
        "Random",
        "Input",
        "KeyCode",
        "Touch",
        "Screen",
        "Cursor",
        "Application",
        "SystemInfo",
        "QualitySettings",
        "RenderSettings",
        "Graphics",
        "GL",
        "Gizmos",
        "Handles",
        "Debug",
        "Physics",
        "Physics2D",
        "Collider",
        "Collider2D",
        "BoxCollider",
        "BoxCollider2D",
        "SphereCollider",
        "CapsuleCollider",
        "CapsuleCollider2D",
        "CircleCollider2D",
        "PolygonCollider2D",
        "EdgeCollider2D",
        "CompositeCollider2D",
        "MeshCollider",
        "WheelCollider",
        "TerrainCollider",
        "CharacterController",
        "Rigidbody",
        "Rigidbody2D",
        "Joint",
        "Joint2D",
        "HingeJoint",
        "SpringJoint",
        "FixedJoint",
        "AudioSource",
        "AudioClip",
        "AudioListener",
        "AudioMixer",
        "AudioMixerGroup",
        "Animator",
        "AnimatorStateInfo",
        "Animation",
        "AnimationClip",
        "AnimationEvent",
        "Renderer",
        "MeshRenderer",
        "SkinnedMeshRenderer",
        "SpriteRenderer",
        "TrailRenderer",
        "LineRenderer",
        "ParticleSystem",
        "ParticleSystemRenderer",
        "Mesh",
        "MeshFilter",
        "Material",
        "MaterialPropertyBlock",
        "Shader",
        "Sprite",
        "Texture",
        "Texture2D",
        "Texture3D",
        "Cubemap",
        "RenderTexture",
        "Camera",
        "Light",
        "ReflectionProbe",
        "LightProbeGroup",
        "Terrain",
        "TerrainData",
        "NavMesh",
        "NavMeshAgent",
        "NavMeshObstacle",
        "NavMeshPath",
        "NavMeshHit",
        "Canvas",
        "CanvasGroup",
        "CanvasScaler",
        "GraphicRaycaster",
        "Graphic",
        "MaskableGraphic",
        "Image",
        "RawImage",
        "Text",
        "Button",
        "Toggle",
        "ToggleGroup",
        "Slider",
        "Scrollbar",
        "ScrollRect",
        "InputField",
        "Dropdown",
        "LayoutGroup",
        "HorizontalLayoutGroup",
        "VerticalLayoutGroup",
        "GridLayoutGroup",
        "ContentSizeFitter",
        "AspectRatioFitter",
        "LayoutElement",
        "RectMask2D",
        "Mask",
        "Shadow",
        "Outline",
        "Selectable",
        "EventSystem",
        "PointerEventData",
        "BaseEventData",
        "AxisEventData",
        "TMP_Text",
        "TextMeshPro",
        "TextMeshProUGUI",
        "TMP_InputField",
        "TMP_Dropdown",
        "TMP_FontAsset",
        "TMP_SpriteAsset",
        "SceneManager",
        "Scene",
        "LoadSceneMode",
        "PlayerPrefs",
        "JsonUtility",
        "Resources",
        "AssetBundle",
        "Profiler",
        "UnityEvent",
        "UnityEventBase",
        "UnityAction",
        "SerializeField",
        "SerializeReference",
        "Header",
        "Tooltip",
        "Range",
        "Min",
        "Space",
        "TextArea",
        "Multiline",
        "ColorUsage",
        "GradientUsage",
        "HideInInspector",
        "NonSerialized",
        "FormerlySerializedAs",
        "RequireComponent",
        "DisallowMultipleComponent",
        "AddComponentMenu",
        "ExecuteAlways",
        "ExecuteInEditMode",
        "CreateAssetMenu",
        "ContextMenu",
        "ContextMenuItem",
        "MenuItem",
        "InitializeOnLoad",
        "InitializeOnLoadMethod",
        "RuntimeInitializeOnLoadMethod",
        "CustomEditor",
        "CustomPropertyDrawer",
        "Selection",
        "AssetDatabase",
        "Editor",
        "EditorWindow",
        "EditorGUILayout",
        "GUILayout",
        "EditorGUI",
        "GUI",
        "GUIStyle",
        "GUIContent",
        "GUISkin",
        "EditorUtility",
        "SerializedObject",
        "SerializedProperty",
        "PropertyDrawer",
        "AssetPostprocessor",
        "ScriptableWizard",
    }
)

_CS_SINGLETON_NAMES: frozenset[str] = frozenset(
    {
        "instance",
        "Instance",
        "INSTANCE",
        "singleton",
        "Singleton",
        "SINGLETON",
        "current",
        "Current",
        "shared",
        "Shared",
        "default",
        "Default",
        "active",
        "Active",
        "main",
        "Main",
    }
)

# Built-in C# / Unity Engine / LINQ / collection methods that should not be
# resolved by bare method name across unrelated classes when receiver type is unknown.
_CS_METHOD_IGNORE: frozenset[str] = frozenset(
    {
        # Unity lifecycle callbacks
        "Awake",
        "Start",
        "Update",
        "FixedUpdate",
        "LateUpdate",
        "OnEnable",
        "OnDisable",
        "OnDestroy",
        "OnValidate",
        "Reset",
        "OnGUI",
        "OnDrawGizmos",
        "OnDrawGizmosSelected",
        "OnTriggerEnter",
        "OnTriggerStay",
        "OnTriggerExit",
        "OnTriggerEnter2D",
        "OnTriggerStay2D",
        "OnTriggerExit2D",
        "OnCollisionEnter",
        "OnCollisionStay",
        "OnCollisionExit",
        "OnCollisionEnter2D",
        "OnCollisionStay2D",
        "OnCollisionExit2D",
        "OnBecameVisible",
        "OnBecameInvisible",
        "OnApplicationQuit",
        "OnApplicationPause",
        "OnApplicationFocus",
        "OnAnimatorIK",
        "OnAnimatorMove",
        "OnParticleCollision",
        "OnTransformChildrenChanged",
        "OnTransformParentChanged",
        # System.Object / general primitives
        "ToString",
        "Equals",
        "ReferenceEquals",
        "GetHashCode",
        "GetType",
        "MemberwiseClone",
        "CompareTo",
        "Dispose",
        "Clone",
        "CopyTo",
        # Collections & LINQ
        "Add",
        "AddRange",
        "Remove",
        "RemoveAt",
        "RemoveAll",
        "RemoveRange",
        "Insert",
        "InsertRange",
        "Clear",
        "Contains",
        "ContainsKey",
        "ContainsValue",
        "TryGetValue",
        "TryAdd",
        "IndexOf",
        "LastIndexOf",
        "BinarySearch",
        "Find",
        "FindAll",
        "FindIndex",
        "FindLast",
        "FindLastIndex",
        "Exists",
        "TrueForAll",
        "ForEach",
        "Sort",
        "Reverse",
        "ToArray",
        "ToList",
        "ToDictionary",
        "ToHashSet",
        "AsEnumerable",
        "AsReadOnly",
        "Where",
        "First",
        "FirstOrDefault",
        "Last",
        "LastOrDefault",
        "Single",
        "SingleOrDefault",
        "ElementAt",
        "ElementAtOrDefault",
        "Any",
        "All",
        "Count",
        "Sum",
        "Min",
        "Max",
        "Average",
        "Aggregate",
        "OrderBy",
        "OrderByDescending",
        "ThenBy",
        "ThenByDescending",
        "GroupBy",
        "Distinct",
        "Concat",
        "Union",
        "Intersect",
        "Except",
        "Skip",
        "SkipWhile",
        "Take",
        "TakeWhile",
        "Cast",
        "OfType",
        "Zip",
        "Enqueue",
        "Dequeue",
        "TryDequeue",
        "Push",
        "Pop",
        "TryPop",
        "Peek",
        "TryPeek",
        # Unity Component / Object / GameObject primitives
        "GetComponent",
        "GetComponents",
        "GetComponentInChildren",
        "GetComponentsInChildren",
        "GetComponentInParent",
        "GetComponentsInParent",
        "TryGetComponent",
        "AddComponent",
        "FindObjectOfType",
        "FindObjectsOfType",
        "FindFirstObjectByType",
        "FindAnyObjectByType",
        "FindObjectsByType",
        "FindWithTag",
        "FindGameObjectsWithTag",
        "Instantiate",
        "Destroy",
        "DestroyImmediate",
        "DontDestroyOnLoad",
        "StartCoroutine",
        "StopCoroutine",
        "StopAllCoroutines",
        "Invoke",
        "InvokeRepeating",
        "CancelInvoke",
        "IsInvoking",
        "SetActive",
        "CompareTag",
        "SendMessage",
        "SendMessageUpwards",
        "BroadcastMessage",
        "GetInstanceID",
        "GetChild",
        "SetParent",
        "Translate",
        "Rotate",
        "LookAt",
        "TransformPoint",
        "InverseTransformPoint",
        "TransformDirection",
        "InverseTransformDirection",
        # Unity Debug / Math / Input / String / PlayerPrefs / Animator / Audio primitives
        "Log",
        "LogWarning",
        "LogError",
        "LogException",
        "LogFormat",
        "Assert",
        "Format",
        "IsNullOrEmpty",
        "IsNullOrWhiteSpace",
        "Join",
        "Split",
        "Trim",
        "TrimStart",
        "TrimEnd",
        "Substring",
        "Replace",
        "StartsWith",
        "EndsWith",
        "ToLower",
        "ToLowerInvariant",
        "ToUpper",
        "ToUpperInvariant",
        "Parse",
        "TryParse",
        "Clamp",
        "Clamp01",
        "Lerp",
        "LerpUnclamped",
        "InverseLerp",
        "MoveTowards",
        "SmoothDamp",
        "Repeat",
        "PingPong",
        "Approximately",
        "Abs",
        "Sign",
        "Round",
        "RoundToInt",
        "Floor",
        "FloorToInt",
        "Ceil",
        "CeilToInt",
        "Sin",
        "Cos",
        "Tan",
        "Asin",
        "Acos",
        "Atan",
        "Atan2",
        "Sqrt",
        "Pow",
        "Exp",
        "Distance",
        "Normalize",
        "Dot",
        "Cross",
        "Project",
        "Reflect",
        "Slerp",
        "Euler",
        "LookRotation",
        "Angle",
        "RotateTowards",
        "Raycast",
        "RaycastAll",
        "OverlapSphere",
        "OverlapCircle",
        "OverlapBox",
        "GetKey",
        "GetKeyDown",
        "GetKeyUp",
        "GetMouseButton",
        "GetMouseButtonDown",
        "GetMouseButtonUp",
        "GetAxis",
        "GetAxisRaw",
        "GetButton",
        "GetButtonDown",
        "GetButtonUp",
        "LoadScene",
        "LoadSceneAsync",
        "UnloadSceneAsync",
        "GetActiveScene",
        "GetInt",
        "SetInt",
        "GetFloat",
        "SetFloat",
        "GetString",
        "SetString",
        "HasKey",
        "DeleteKey",
        "DeleteAll",
        "PlayOneShot",
        "SetTrigger",
        "ResetTrigger",
        "SetBool",
        "GetBool",
        "SetFloat",
        "SetInteger",
        "GetInteger",
        "CrossFade",
        "AddListener",
        "RemoveListener",
        "RemoveAllListeners",
    }
)


# ---------------------------------------------------------------------------
# Tree-sitter node helpers
# ---------------------------------------------------------------------------


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


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
    "predefined_type",
    "identifier",
    "generic_name",
    "qualified_name",
    "nullable_type",
    "array_type",
    "tuple_type",
    "void_keyword",
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


def _extract_custom_types(node, src: bytes, own_name: str = "") -> list[str]:
    """
    Extract all custom UpperCamelCase type names referenced in a type AST node
    (including generic type arguments and array element types).
    e.g. List<WeaponData> -> ['WeaponData']
         PlayerScript     -> ['PlayerScript']
    """
    if node is None:
        return []
    found: list[str] = []
    seen: set[str] = set()
    stack = [node]
    while stack:
        cur = stack.pop()
        ctype = cur.type
        if ctype in ("predefined_type", "implicit_type", "void_keyword"):
            continue
        if ctype == "identifier":
            tname = _text(cur, src)
            if (
                tname
                and tname[0].isupper()
                and not tname.isupper()
                and tname not in _CS_IGNORE
                and tname != own_name
                and tname not in seen
            ):
                seen.add(tname)
                found.append(tname)
            continue
        if ctype == "qualified_name":
            last = _text(cur, src).split(".")[-1]
            if (
                last
                and last[0].isupper()
                and not last.isupper()
                and last not in _CS_IGNORE
                and last != own_name
                and last not in seen
            ):
                seen.add(last)
                found.append(last)
            continue
        if cur.child_count > 0:
            stack.extend(reversed(cur.children))
    return found


_CS_FACTORY_PREFIXES: tuple[str, ...] = (
    "Get_",
    "get_",
    "Find_",
    "find_",
    "Create_",
    "create_",
    "Spawn_",
    "spawn_",
    "Load_",
    "load_",
    "Get",
    "Find",
    "Create",
    "Spawn",
)


def _factory_to_class_cs(fname: str) -> str:
    """
    Convert a C#/Unity factory/accessor method name to its likely class name:
      'Get_PlayerScript' -> 'PlayerScript'
      'GetPlayerScript'  -> 'PlayerScript'
      'Create_Enemy'     -> 'Enemy'
    """
    if fname in _CS_METHOD_IGNORE:
        return ""
    for prefix in _CS_FACTORY_PREFIXES:
        if fname.startswith(prefix) and len(fname) > len(prefix):
            rem = fname[len(prefix) :].lstrip("_")
            if rem and rem[0].isupper() and len(rem) >= 3 and not rem.isupper():
                if rem not in _CS_IGNORE and rem not in _CS_METHOD_IGNORE:
                    return rem
    return ""


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
    any(c.type == "static" for c in node.children)
    name_node = _first(node, "qualified_name", "identifier", "generic_name")
    if not name_node:
        return
    full = _text(name_node, src)
    parts = full.split(".")
    module = ".".join(parts[:-1]) if len(parts) > 1 else full
    name = parts[-1] if parts else full
    out.append(
        ImportInfo(
            module=module,
            names=[name],
            is_from=True,
            is_relative=False,
            level=0,
        )
    )


# ---------------------------------------------------------------------------
# Type declaration extraction
# ---------------------------------------------------------------------------

_TYPE_DECL_TYPES = {
    "class_declaration",
    "interface_declaration",
    "struct_declaration",
    "enum_declaration",
    "record_declaration",
    "delegate_declaration",
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
        elif ntype in (
            "declaration_list",
            "namespace_declaration",
            "file_scoped_namespace_declaration",
        ):
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
    methods, class_vars, calls, method_calls, field_refs = (
        _parse_declaration_list(body, src, name) if body else ([], [], [], [], [])
    )

    out.append(
        ClassInfo(
            name=name,
            bases=bases,
            methods=methods,
            class_vars=class_vars,
            decorators=attrs,
            docstring="",
            line_start=_line(node),
            line_end=_end_line(node),
            calls=calls,
            kind=kind,
            method_calls=method_calls,
            field_refs=field_refs,
        )
    )

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

    out.append(
        ClassInfo(
            name=name,
            bases=bases,
            methods=methods,
            class_vars=[],
            decorators=attrs,
            docstring="",
            line_start=_line(node),
            line_end=_end_line(node),
            calls=[],
            kind="interface",
        )
    )

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
    methods, class_vars, calls, method_calls, field_refs = (
        _parse_declaration_list(body, src, name) if body else ([], [], [], [], [])
    )

    out.append(
        ClassInfo(
            name=name,
            bases=bases,
            methods=methods,
            class_vars=class_vars,
            decorators=attrs,
            docstring="",
            line_start=_line(node),
            line_end=_end_line(node),
            calls=calls,
            kind="struct",
            method_calls=method_calls,
            field_refs=field_refs,
        )
    )

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
    out.append(
        ClassInfo(
            name=name,
            bases=[],
            methods=[],
            class_vars=members,
            decorators=attrs,
            docstring="",
            line_start=_line(node),
            line_end=_end_line(node),
            calls=[],
            kind="enum",
        )
    )


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
    methods, extra_vars, calls, method_calls, field_refs = (
        _parse_declaration_list(body, src, name) if body else ([], [], [], [], [])
    )
    if body:
        _walk_decls(body, src, out)

    out.append(
        ClassInfo(
            name=name,
            bases=bases,
            methods=methods,
            class_vars=components + extra_vars,
            decorators=attrs,
            docstring="",
            line_start=_line(node),
            line_end=_end_line(node),
            calls=calls,
            kind=kind,
            method_calls=method_calls,
            field_refs=field_refs,
        )
    )


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

    out.append(
        ClassInfo(
            name=name,
            bases=[],
            methods=[],
            class_vars=components,
            decorators=[],
            docstring="",
            line_start=_line(node),
            line_end=_end_line(node),
            calls=[],
            kind="delegate",
        )
    )


# ---------------------------------------------------------------------------
# Declaration list (shared body parser for classes, structs, records)
# ---------------------------------------------------------------------------


def _parse_declaration_list(body, src: bytes, own_name: str):
    methods: list[MethodInfo] = []
    class_vars: list[str] = []
    calls: list[tuple[str, str]] = []
    seen_calls: set[tuple[str, str]] = set()
    method_calls: list[tuple[str, str, str]] = []
    seen_method_calls: set[tuple[str, str, str]] = set()
    field_refs: list[tuple[str, str, bool]] = []
    seen_field_refs: set[tuple[str, str]] = set()
    member_types: dict[str, str] = {}

    # Pass 1: Extract fields and properties (types + [SerializeField] refs)
    for child in body.children:
        if child.type == "field_declaration":
            mods = _collect_modifiers(child)
            attrs = _collect_attributes(child, src)
            is_serialized = "SerializeField" in attrs or "SerializeReference" in attrs
            is_const_or_static_ro = "const" in mods or ("static" in mods and "readonly" in mods)
            var_decl = _first(child, "variable_declaration")
            if not var_decl:
                continue
            type_node = var_decl.child_by_field_name("type") or _first(
                var_decl,
                "identifier",
                "generic_name",
                "qualified_name",
                "nullable_type",
                "array_type",
                "predefined_type",
            )
            custom_types = _extract_custom_types(type_node, src, own_name)
            primary_type = custom_types[0] if custom_types else ""

            for decl in _all(var_decl, "variable_declarator"):
                id_node = decl.child_by_field_name("name") or _first(decl, "identifier")
                if not id_node:
                    continue
                fname = _text(id_node, src)
                if is_const_or_static_ro and (
                    re.match(r"^[A-Z][A-Z0-9_]*$", fname) or "const" in mods
                ):
                    class_vars.append(fname)
                if primary_type:
                    member_types[fname] = primary_type
                if custom_types and (is_serialized or "const" not in mods):
                    for ct in custom_types:
                        if (fname, ct) not in seen_field_refs:
                            seen_field_refs.add((fname, ct))
                            field_refs.append((fname, ct, is_serialized))

        elif child.type == "property_declaration":
            attrs = _collect_attributes(child, src)
            is_serialized = "SerializeField" in attrs or "SerializeReference" in attrs
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            if name_node and type_node:
                pname = _text(name_node, src)
                custom_types = _extract_custom_types(type_node, src, own_name)
                if custom_types:
                    member_types[pname] = custom_types[0]
                    if is_serialized:
                        for ct in custom_types:
                            if (pname, ct) not in seen_field_refs:
                                seen_field_refs.add((pname, ct))
                                field_refs.append((pname, ct, True))

    # Pre-scan assignments across methods/constructors to enrich member_types
    # (e.g. _audio = GetComponent<AudioManager>() in Awake())
    for child in body.children:
        if child.type in ("method_declaration", "constructor_declaration"):
            _scan_field_assignments(child, src, member_types, own_name)

    # Pass 2: Extract methods, constructors, properties and scan their bodies for calls
    for child in body.children:
        if child.type == "method_declaration":
            m = _parse_method(child, src)
            if m:
                methods.append(m)
                _collect_method_calls(
                    child,
                    src,
                    m.name,
                    calls,
                    seen_calls,
                    method_calls,
                    seen_method_calls,
                    member_types,
                    own_name,
                )
        elif child.type == "constructor_declaration":
            c = _parse_constructor(child, src)
            if c:
                methods.append(c)
                _collect_method_calls(
                    child,
                    src,
                    c.name,
                    calls,
                    seen_calls,
                    method_calls,
                    seen_method_calls,
                    member_types,
                    own_name,
                )
        elif child.type == "property_declaration":
            p = _parse_property(child, src)
            if p:
                methods.append(p)
                _collect_method_calls(
                    child,
                    src,
                    p.name,
                    calls,
                    seen_calls,
                    method_calls,
                    seen_method_calls,
                    member_types,
                    own_name,
                )

    return methods, class_vars, calls, method_calls, field_refs


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
    is_static = "static" in mods
    is_async = "async" in mods
    attrs = _collect_attributes(node, src)

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
        name=name,
        args=args,
        return_type=return_type,
        decorators=attrs,
        is_async=is_async,
        is_property=False,
        is_classmethod=is_static,
        is_staticmethod=is_static,
        line_start=_line(node),
        line_end=_end_line(node),
    )


def _parse_property(node, src: bytes) -> MethodInfo | None:
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    name = _text(name_node, src)

    type_node = node.child_by_field_name("type")
    return_type = _type_text(type_node, src) if type_node else ""
    attrs = _collect_attributes(node, src)

    return MethodInfo(
        name=name,
        args=[],
        return_type=return_type,
        decorators=attrs,
        is_async=False,
        is_property=True,
        is_classmethod=False,
        is_staticmethod=False,
        line_start=_line(node),
        line_end=_end_line(node),
    )


def _parse_constructor(node, src: bytes) -> MethodInfo | None:
    name_node = _first(node, "identifier")
    if not name_node:
        return None
    params_node = _first(node, "parameter_list")
    args = _parse_params(params_node, src) if params_node else []
    return MethodInfo(
        name="<ctor>",
        args=args,
        return_type="",
        decorators=[],
        is_async=False,
        is_property=False,
        is_classmethod=False,
        is_staticmethod=False,
        line_start=_line(node),
        line_end=_end_line(node),
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
# Call graph & invocation extraction
# ---------------------------------------------------------------------------


def _infer_expr_type(expr_node, src: bytes, local_types: dict[str, str], own_name: str) -> str:
    """
    Attempt to infer the custom class type returned by *expr_node*:
      - new PlayerScript()             -> 'PlayerScript'
      - GetComponent<AudioManager>()   -> 'AudioManager'
      - Get_PlayerScript()             -> 'PlayerScript'
      - _player                        -> local_types['_player']
      - this._player                   -> local_types['_player']
    """
    if expr_node is None:
        return ""
    etype = expr_node.type
    if etype in ("object_creation_expression", "implicit_object_creation_expression"):
        type_node = _first(expr_node, "identifier", "generic_name", "qualified_name")
        if type_node:
            ct = _extract_custom_types(type_node, src, own_name)
            return ct[0] if ct else ""
    elif etype == "invocation_expression":
        func = expr_node.child_by_field_name("function") or _first(
            expr_node,
            "generic_name",
            "member_access_expression",
            "conditional_access_expression",
            "identifier",
        )
        if func:
            if func.type == "generic_name":
                targs = _first(func, "type_argument_list")
                ct = _extract_custom_types(targs, src, own_name)
                if ct:
                    return ct[0]
            elif func.type in ("member_access_expression", "conditional_access_expression"):
                gen = _first(func, "generic_name")
                if gen:
                    targs = _first(gen, "type_argument_list")
                    ct = _extract_custom_types(targs, src, own_name)
                    if ct:
                        return ct[0]
                name_node = func.child_by_field_name("name")
                if name_node:
                    cand = _factory_to_class_cs(_text(name_node, src))
                    if cand and cand != own_name:
                        return cand
            elif func.type == "identifier":
                cand = _factory_to_class_cs(_text(func, src))
                if cand and cand != own_name:
                    return cand
    elif etype == "identifier":
        vname = _text(expr_node, src)
        return local_types.get(vname, "")
    elif etype == "member_access_expression":
        parts = _flatten_member_chain(expr_node, src)
        if len(parts) == 2 and parts[0] == "this":
            return local_types.get(parts[1], "")
        if len(parts) == 1:
            return local_types.get(parts[0], "")
    return ""


def _flatten_member_chain(node, src: bytes) -> list[str]:
    """
    Flatten a nested member_access_expression / conditional_access_expression
    into its list of identifier segments when the chain is purely identifiers.
    e.g. GameHandler.instance.Death -> ['GameHandler', 'instance', 'Death']
         Connector.Instance.Haptics.Pulse -> ['Connector', 'Instance', 'Haptics', 'Pulse']
    If the root is an invocation (e.g. Get_PlayerScript().TriggerScreenShake),
    returns only the trailing member segments after the invocation.
    """
    parts: list[str] = []
    cur = node
    while cur is not None:
        ctype = cur.type
        if ctype == "member_access_expression":
            name_node = cur.child_by_field_name("name") or _first(cur, "generic_name", "identifier")
            if name_node:
                if name_node.type == "generic_name":
                    id_n = _first(name_node, "identifier")
                    parts.append(_text(id_n, src) if id_n else _text(name_node, src))
                else:
                    parts.append(_text(name_node, src))
            cur = cur.child_by_field_name("expression")
        elif ctype == "conditional_access_expression":
            binding = _first(cur, "member_binding_expression")
            if binding:
                bname = binding.child_by_field_name("name") or _first(
                    binding, "generic_name", "identifier"
                )
                if bname:
                    if bname.type == "generic_name":
                        id_n = _first(bname, "identifier")
                        parts.append(_text(id_n, src) if id_n else _text(bname, src))
                    else:
                        parts.append(_text(bname, src))
            cur = cur.child_by_field_name("condition")
        elif ctype == "identifier":
            parts.append(_text(cur, src))
            break
        elif ctype == "this_expression":
            parts.append("this")
            break
        elif ctype == "base_expression":
            parts.append("base")
            break
        else:
            break
    parts.reverse()
    return parts


def _root_expression(node):
    """Return the innermost receiver expression of a member/conditional access chain."""
    cur = node
    while cur is not None:
        if cur.type == "member_access_expression":
            nxt = cur.child_by_field_name("expression")
            if nxt is None:
                return cur
            cur = nxt
        elif cur.type == "conditional_access_expression":
            nxt = cur.child_by_field_name("condition")
            if nxt is None:
                return cur
            cur = nxt
        else:
            return cur
    return node


def _scan_field_assignments(
    method_node,
    src: bytes,
    member_types: dict[str, str],
    own_name: str,
) -> None:
    """Scan a method/constructor for assignments to fields (e.g. _p = GetComponent<Player>())."""
    stack = [method_node]
    while stack:
        cur = stack.pop()
        if cur.type == "assignment_expression":
            left = cur.child_by_field_name("left")
            right = cur.child_by_field_name("right")
            if left and right:
                lhs_name = ""
                if left.type == "identifier":
                    lhs_name = _text(left, src)
                elif left.type == "member_access_expression":
                    parts = _flatten_member_chain(left, src)
                    if len(parts) == 2 and parts[0] == "this":
                        lhs_name = parts[1]
                if lhs_name and lhs_name not in member_types:
                    inferred = _infer_expr_type(right, src, member_types, own_name)
                    if inferred:
                        member_types[lhs_name] = inferred
        if cur.child_count > 0:
            stack.extend(reversed(cur.children))


def _collect_method_calls(
    method_node,
    src: bytes,
    method_name: str,
    out: list[tuple[str, str]],
    seen: set[tuple[str, str]],
    method_calls: list[tuple[str, str, str]],
    seen_method_calls: set[tuple[str, str, str]],
    member_types: dict[str, str],
    own_name: str,
) -> None:
    local_types = dict(member_types)

    # Extract parameter types + add parameter custom types to calls
    params_node = _first(method_node, "parameter_list")
    if params_node:
        for param in _all(params_node, "parameter"):
            p_type = param.child_by_field_name("type")
            p_name = param.child_by_field_name("name")
            ctypes = _extract_custom_types(p_type, src, own_name)
            if ctypes:
                if p_name:
                    local_types[_text(p_name, src)] = ctypes[0]
                for ct in ctypes:
                    pair = (ct, method_name)
                    if pair not in seen:
                        seen.add(pair)
                        out.append(pair)

    # Extract return type custom types
    ret_node = method_node.child_by_field_name("returns") or method_node.child_by_field_name("type")
    if ret_node:
        for ct in _extract_custom_types(ret_node, src, own_name):
            pair = (ct, method_name)
            if pair not in seen:
                seen.add(pair)
                out.append(pair)

    # Scan block, arrow_expression_clause, accessor_list, constructor_initializer
    for child in method_node.children:
        if child.type in (
            "block",
            "arrow_expression_clause",
            "accessor_list",
            "constructor_initializer",
        ):
            _scan_calls(
                child,
                src,
                method_name,
                out,
                seen,
                method_calls,
                seen_method_calls,
                local_types,
                own_name,
            )


def _add_call(
    cname: str,
    ctx: str,
    own_name: str,
    out: list[tuple[str, str]],
    seen: set[tuple[str, str]],
) -> None:
    if (
        cname
        and cname[0].isupper()
        and not cname.isupper()
        and cname not in _CS_IGNORE
        and cname != own_name
    ):
        pair = (cname, ctx)
        if pair not in seen:
            seen.add(pair)
            out.append(pair)


def _add_method_call(
    receiver_hint: str,
    mname: str,
    ctx: str,
    own_name: str,
    method_calls: list[tuple[str, str, str]],
    seen_method_calls: set[tuple[str, str, str]],
) -> None:
    if not mname or mname == own_name:
        return
    if not receiver_hint and mname in _CS_METHOD_IGNORE:
        return
    if receiver_hint in _CS_IGNORE:
        return
    triple = (receiver_hint, mname, ctx)
    if triple not in seen_method_calls:
        seen_method_calls.add(triple)
        method_calls.append(triple)


def _scan_calls(
    node,
    src: bytes,
    ctx: str,
    out: list[tuple[str, str]],
    seen: set[tuple[str, str]],
    method_calls: list[tuple[str, str, str]],
    seen_method_calls: set[tuple[str, str, str]],
    local_types: dict[str, str],
    own_name: str,
) -> None:
    stack = [node]
    while stack:
        current = stack.pop()
        ntype = current.type

        # Track local variable declarations: e.g. PlayerScript p = ...; or var p = GetComponent<T>();
        if ntype == "variable_declaration":
            vtype_node = current.child_by_field_name("type") or _first(
                current,
                "identifier",
                "generic_name",
                "qualified_name",
                "nullable_type",
                "array_type",
                "implicit_type",
            )
            explicit_types = _extract_custom_types(vtype_node, src, own_name)
            for ct in explicit_types:
                _add_call(ct, ctx, own_name, out, seen)
            for decl in _all(current, "variable_declarator"):
                vname_node = decl.child_by_field_name("name") or _first(decl, "identifier")
                if not vname_node:
                    continue
                vname = _text(vname_node, src)
                if explicit_types:
                    local_types[vname] = explicit_types[0]
                else:
                    # var x = <initializer>
                    for dchild in decl.children:
                        if dchild != vname_node and dchild.type != "=":
                            inferred = _infer_expr_type(dchild, src, local_types, own_name)
                            if inferred:
                                local_types[vname] = inferred
                                _add_call(inferred, ctx, own_name, out, seen)
                                break

        # Object creation: new ClassName(...)
        elif ntype in ("object_creation_expression", "implicit_object_creation_expression"):
            type_node = _first(current, "identifier", "generic_name", "qualified_name")
            if type_node:
                for ct in _extract_custom_types(type_node, src, own_name):
                    _add_call(ct, ctx, own_name, out, seen)

        # Method invocation: Foo(), obj.Bar(), GameHandler.instance.Death(), GetComponent<T>()
        elif ntype == "invocation_expression":
            func_node = current.child_by_field_name("function") or _first(
                current,
                "member_access_expression",
                "conditional_access_expression",
                "generic_name",
                "identifier",
            )
            if func_node is not None:
                ftype = func_node.type

                # 1. Extract any generic type arguments anywhere in func_node
                #    e.g. GetComponent<AudioManager>(), FindObjectOfType<GameManager>()
                for sub in _walk_all(func_node):
                    if sub.type == "type_argument_list":
                        for ct in _extract_custom_types(sub, src, own_name):
                            _add_call(ct, ctx, own_name, out, seen)

                # 2. Bare call: Select() or Get_PlayerScript() or GetComponent<T>()
                if ftype in ("identifier", "generic_name"):
                    id_n = _first(func_node, "identifier") if ftype == "generic_name" else func_node
                    mname = _text(id_n, src) if id_n else ""
                    if mname:
                        factory_cls = _factory_to_class_cs(mname)
                        if factory_cls:
                            _add_call(factory_cls, ctx, own_name, out, seen)
                        _add_method_call("", mname, ctx, own_name, method_calls, seen_method_calls)

                # 3. Member or conditional access chain:
                #    GameHandler.instance.Death()
                #    Connector.Instance.Haptics.Pulse()
                #    Get_PlayerScript().TriggerScreenShake()
                #    _player.On_Damage(10)
                elif ftype in ("member_access_expression", "conditional_access_expression"):
                    parts = _flatten_member_chain(func_node, src)
                    called_method = parts[-1] if parts else ""
                    root_expr = _root_expression(func_node)

                    # Strip leading 'this' / 'base'
                    chain = parts[:-1]
                    if chain and chain[0] in ("this", "base"):
                        chain = chain[1:]

                    receiver_cls = ""
                    # Case A: Root of chain is another expression (e.g. Get_PlayerScript().TriggerScreenShake())
                    if root_expr is not None and root_expr.type not in (
                        "identifier",
                        "this_expression",
                        "base_expression",
                    ):
                        receiver_cls = _infer_expr_type(root_expr, src, local_types, own_name)
                        if receiver_cls:
                            _add_call(receiver_cls, ctx, own_name, out, seen)

                    # Case B: Root is an identifier in chain
                    elif chain:
                        root_id = chain[0]
                        if root_id in local_types:
                            receiver_cls = local_types[root_id]
                            _add_call(receiver_cls, ctx, own_name, out, seen)
                        elif (
                            root_id[0].isupper()
                            and root_id not in _CS_SINGLETON_NAMES
                            and root_id not in _CS_IGNORE
                        ):
                            # Static / singleton root class, e.g. GameHandler or Connector
                            receiver_cls = root_id
                            _add_call(root_id, ctx, own_name, out, seen)
                        elif root_id in _CS_IGNORE:
                            # Built-in class static call like Debug.Log, Mathf.Clamp, Physics2D.Raycast
                            receiver_cls = root_id

                    # Check intermediate segments for subsystem hints (e.g. Connector.Instance.Haptics.Pulse)
                    intermediate_hints: list[str] = []
                    for seg in chain[1:]:
                        if (
                            seg
                            and seg[0].isupper()
                            and not seg.isupper()
                            and seg not in _CS_SINGLETON_NAMES
                            and seg not in _CS_IGNORE
                        ):
                            intermediate_hints.append(seg)

                    if called_method:
                        factory_cls = _factory_to_class_cs(called_method)
                        if factory_cls:
                            _add_call(factory_cls, ctx, own_name, out, seen)

                        if intermediate_hints:
                            for hint in intermediate_hints:
                                _add_method_call(
                                    hint,
                                    called_method,
                                    ctx,
                                    own_name,
                                    method_calls,
                                    seen_method_calls,
                                )
                            if receiver_cls and receiver_cls not in _CS_IGNORE:
                                _add_method_call(
                                    receiver_cls,
                                    called_method,
                                    ctx,
                                    own_name,
                                    method_calls,
                                    seen_method_calls,
                                )
                            elif receiver_cls not in _CS_IGNORE:
                                _add_method_call(
                                    "",
                                    called_method,
                                    ctx,
                                    own_name,
                                    method_calls,
                                    seen_method_calls,
                                )
                        elif receiver_cls and receiver_cls not in _CS_IGNORE:
                            _add_method_call(
                                receiver_cls,
                                called_method,
                                ctx,
                                own_name,
                                method_calls,
                                seen_method_calls,
                            )
                        elif receiver_cls not in _CS_IGNORE:
                            _add_method_call(
                                "",
                                called_method,
                                ctx,
                                own_name,
                                method_calls,
                                seen_method_calls,
                            )

        if current.child_count > 0:
            stack.extend(reversed(current.children))


def _walk_all(node):
    """Yield *node* and all its descendants."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        if cur.child_count > 0:
            stack.extend(reversed(cur.children))


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
            path=path,
            language="csharp",
            line_count=line_count,
            module_docstring="",
            classes=[],
            functions=[],
            imports=[],
            all_exports=[],
            constants=[],
            parse_errors=[
                "tree-sitter-c-sharp not installed — run: "
                'pip install "tree-sitter>=0.23.0" tree-sitter-c-sharp'
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

        namespace = _extract_namespace(root, src)
        imports = _extract_imports(root, src)
        classes = _extract_type_declarations(root, src)
        functions = _extract_functions(root, src)

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
            path=path,
            language="csharp",
            line_count=line_count,
            module_docstring="",
            classes=[],
            functions=[],
            imports=[],
            all_exports=[],
            constants=[],
            parse_errors=[f"AnalysisError: {exc}"],
        )
