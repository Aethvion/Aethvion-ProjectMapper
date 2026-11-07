"""
project_mapper/analyzers/unity.py
Unity asset & metadata extractor (.unity scenes, .prefab prefabs, .asset ScriptableObjects, .meta GUIDs).

Parses Unity YAML serialization files to map script <-> scene/prefab/asset
dependencies and Inspector UnityEvent method bindings without requiring a
running Unity Editor.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import CodeAnalysis

_RE_META_GUID = re.compile(r"^guid:\s*([0-9a-fA-F]{32})\b", re.MULTILINE)
_RE_YAML_GUID = re.compile(r"\bguid:\s*([0-9a-fA-F]{32})\b")
_RE_SCRIPT_GUID = re.compile(r"m_Script:\s*\{[^}]*\bguid:\s*([0-9a-fA-F]{32})\b")
_RE_UNITY_EVENT = re.compile(
    r"(?:m_TargetAssemblyTypeName:\s*([^\r\n]+)\s*\r?\n\s*)?"
    r"m_MethodName:\s*([A-Za-z_][A-Za-z0-9_]*)"
)

_IGNORE_EVENT_METHODS: frozenset[str] = frozenset(
    {
        "SetActive",
        "Play",
        "Stop",
        "Pause",
        "SendMessage",
        "BroadcastMessage",
        "Destroy",
    }
)


def extract_meta_guid(meta_content: str) -> str:
    """Extract the 32-hex-character GUID from a Unity .meta file."""
    m = _RE_META_GUID.search(meta_content)
    return m.group(1).lower() if m else ""


def read_meta_guid_for_file(file_path: Path) -> str:
    """Read the sidecar <file_path>.meta if it exists and return its GUID."""
    meta_path = Path(str(file_path) + ".meta")
    if not meta_path.is_file():
        return ""
    try:
        with meta_path.open("r", encoding="utf-8", errors="replace") as f:
            head = f.read(1024)
        return extract_meta_guid(head)
    except OSError:
        return ""


def analyze_unity(path: str, content: str) -> CodeAnalysis:
    """
    Analyze a Unity YAML file (.unity, .prefab, .asset) and extract:
      - Referenced asset/script GUIDs (m_Script and serialized object refs)
      - Inspector UnityEvent method calls (m_PersistentCalls)
    """
    line_count = content.count("\n") + 1
    ext = Path(path).suffix.lower()

    if ext == ".unity":
        kind = "unity.scene"
    elif ext == ".prefab":
        kind = "unity.prefab"
    elif ext == ".asset":
        kind = "unity.asset"
    else:
        kind = "unity.asset"

    stripped = content.lstrip("\ufeff \t\r\n")
    if not stripped.startswith("%YAML"):
        # Binary asset or non-Unity .asset file
        return CodeAnalysis(
            path=path,
            language="unity",
            line_count=line_count,
            module_docstring="",
            classes=[],
            functions=[],
            imports=[],
            all_exports=[],
            constants=[],
            parse_errors=[],
            entity_kind_override=kind,
        )

    # For .asset files, only index ScriptableObject assets that reference a
    # script via m_Script: {..., guid: ...}. Built-in Unity settings/lighting
    # assets without m_Script are skipped to avoid noise.
    if ext == ".asset" and not _RE_SCRIPT_GUID.search(content):
        return CodeAnalysis(
            path=path,
            language="unity",
            line_count=line_count,
            module_docstring="",
            classes=[],
            functions=[],
            imports=[],
            all_exports=[],
            constants=[],
            parse_errors=[],
            entity_kind_override=kind,
        )

    seen_guids: set[str] = set()
    guids: list[str] = []
    for m in _RE_YAML_GUID.finditer(content):
        g = m.group(1).lower()
        if g not in seen_guids:
            seen_guids.add(g)
            guids.append(g)

    event_calls: list[tuple[str, str, str]] = []
    seen_events: set[tuple[str, str]] = set()
    for m in _RE_UNITY_EVENT.finditer(content):
        raw_type = (m.group(1) or "").strip()
        method_name = m.group(2).strip()
        if not method_name:
            continue
        if raw_type.startswith("UnityEngine.") or raw_type.startswith("TMPro."):
            continue
        target_type = ""
        if raw_type:
            type_part = raw_type.split(",")[0].strip()
            target_type = type_part.split(".")[-1].strip()
        if not target_type and method_name in _IGNORE_EVENT_METHODS:
            continue
        pair = (target_type, method_name)
        if pair not in seen_events:
            seen_events.add(pair)
            event_calls.append((target_type, method_name, "UnityEvent"))

    return CodeAnalysis(
        path=path,
        language="unity",
        line_count=line_count,
        module_docstring="",
        classes=[],
        functions=[],
        imports=[],
        all_exports=[],
        constants=[],
        parse_errors=[],
        unity_guid_refs=guids,
        unity_event_calls=event_calls,
        entity_kind_override=kind,
    )
