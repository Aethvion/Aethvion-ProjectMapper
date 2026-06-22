"""find MCP tool."""

from __future__ import annotations

from typing import Any

from .base import MCPContext

SCHEMA = {
    "name": "pm_find",
    "description": "Look up a symbol by name and return its definition location, callers, and "
    "callees. Searches by exact name first (case-insensitive), then suffix/method "
    "match, then substring. Prefer this over grep when you know — or partially "
    "know — the name of a function, class, or module: one call returns the exact "
    "definition site plus every caller and callee, instead of raw grep matches "
    "you'd have to open and trace by hand. Faster and more precise than "
    "pm_context for direct symbol lookups.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Symbol name to look up, e.g. "
                "'UserService', 'get_user', 'auth'. "
                "Exact match tried first; partial "
                "matches returned if no exact match.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum matches to return when "
                "multiple symbols share the "
                "name (default 10).",
                "default": 10,
            },
        },
        "required": ["name"],
    },
}


def _format_find_result(m: dict[str, Any]) -> str:
    """Format a single pm_find match as a detailed block."""
    name = m.get("name", "?")
    etype = m.get("type", "")
    kind = m.get("kind") or etype
    fp = m.get("file_path", "")
    line_start = str(m.get("line_start", ""))
    line_end = str(m.get("line_end", ""))

    loc = ""
    if fp:
        loc = fp
        if line_start:
            loc += f"  line {line_start}"
            if line_end and line_end != line_start:
                loc += f"–{line_end}"

    lines = [f"Symbol: {name} [{kind}]"]
    if loc:
        lines.append(f"File:   {loc}")

    status = m.get("status", "active")
    if status not in ("active", ""):
        lines.append(f"Status: {status}")

    summary = m.get("summary", "")
    if summary:
        lines.append(f"Summary: {summary}")

    tags = m.get("tags", [])
    if tags:
        lines.append(f"Tags:   {', '.join(tags)}")

    sig = m.get("signature", "")
    if sig:
        lines.append(f"Signature: {sig[:120]}")

    callers = m.get("callers", [])
    if callers:
        lines.append(f"\nCallers ({len(callers)}):")
        for c in callers:
            lines.append(f"  * {c['name']} [{c.get('type', '?')}]  -> {c.get('via', '?')}")
    else:
        lines.append("\nCallers: none found in graph")

    callees = m.get("callees", [])
    if callees:
        lines.append(f"\nCalls/uses ({len(callees)}):")
        for c in callees:
            lines.append(f"  * {c['name']} [{c.get('type', '?')}]  ({c.get('via', '?')})")

    custom = m.get("custom_properties", {})
    if custom:
        lines.append("\nContributed properties:")
        for k, v in list(custom.items())[:6]:
            lines.append(f"  {k}: {str(v)[:80]}")

    timeline = m.get("timeline", [])
    if timeline:
        lines.append("\nTimeline:")
        for entry in timeline:
            lines.append(f"  [{entry.get('date', '')}] {entry.get('event', '')[:120]}")

    return "\n".join(lines)


def _format_method_find(queried: str, result: dict[str, Any]) -> str:
    """Format pm_find result when the query matched a class method, not a top-level entity."""
    method_name = result.get("matched_method", queried)
    matches = result.get("matches", [])
    total = result.get("total", 0)

    note = (
        f"Note: {queried!r} matched as a method, not a top-level entity — "
        "methods are stored as properties of their parent class.\n"
    )

    if total == 1:
        return note + _format_find_result(matches[0])

    lines = [
        note,
        f"Found method {method_name!r} in {total} classes:",
        "",
    ]
    for m in matches:
        fp = m.get("file_path", "")
        line = str(m.get("line_start", ""))
        loc = f"  {fp}:{line}" if fp and line else (f"  {fp}" if fp else "")
        label = m.get("kind") or m.get("type") or "?"
        desc = f" — {m['summary'][:60]}" if m.get("summary") else ""
        lines.append(f"  * {m['name']} [{label}]{loc}{desc}")
    lines.append("")
    lines.append("Use pm_find <ClassName> to get the full class detail.")
    return "\n".join(lines)


def handle_pm_find(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.query import build_entity_map, find_by_method, find_query

    name = args.get("name", "").strip()
    if not name:
        raise ValueError("'name' is required")

    max_results = min(int(args.get("max_results", 10)), 20)

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = find_query(name, entity_map, ctx.index, max_results=max_results)

    if result.get("not_found"):
        method_result = find_by_method(name, entity_map, ctx.index, max_results=max_results)
        if not method_result.get("not_found"):
            return _format_method_find(name, method_result)
        return (
            f"Symbol {name!r} not found in the graph.\n"
            "Check spelling, or run pm_scan if the codebase hasn't been indexed yet."
        )

    matches = result.get("matches", [])
    total = result.get("total", 0)

    if total == 0:
        return f"No symbols found for {name!r}."

    if total == 1:
        return _format_find_result(matches[0])

    # If there is exactly one exact-name match, show its full detail even when
    # substring matches also exist (e.g. "ChatRequest" + "SyncChatRequest").
    exact = [m for m in matches if m.get("name", "").lower() == name.lower()]
    if len(exact) == 1:
        note = (
            f"\n(Note: {total - 1} additional symbol(s) contain '{name}' as a substring — "
            "use pm_context for broader search.)"
        )
        return _format_find_result(exact[0]) + note

    lines = [
        f"Found {total} symbols matching {name!r}:",
        "",
    ]
    for i, m in enumerate(matches, 1):
        fp = m.get("file_path", "")
        line = str(m.get("line_start", ""))
        loc = f"  {fp}:{line}" if fp and line else f"  {fp}" if fp else ""
        label = m.get("kind") or m.get("type") or "?"
        desc = f" — {m['summary'][:60]}" if m.get("summary") else ""
        lines.append(f"  {i}. {m['name']} [{label}]{loc}{desc}")

    lines.append("")
    lines.append(
        "Use a more specific name to get the detailed view, or pm_context for task-oriented search."
    )
    return "\n".join(lines)
