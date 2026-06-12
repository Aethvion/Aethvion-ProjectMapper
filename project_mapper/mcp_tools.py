"""
project_mapper/mcp_tools.py
MCP tool schemas and handler functions for ProjectMapper.

Each handler takes (args: dict, ctx: MCPContext) and returns a plain-text string
suitable for AI agents to read.  No JSON, no markdown fences — just clear prose
that agents can parse and act on.

Tools
-----
1. pm_context    — task-contextual knowledge retrieval (highest value for agents)
2. pm_impact     — blast-radius analysis for a named entity
3. pm_path       — shortest graph path between two entities
4. pm_contribute — write agent-discovered knowledge back into the graph
5. pm_stats      — database overview + last scan status
6. pm_delta      — filesystem diff vs. the manifest (no DB writes)
7. pm_scan       — synchronous full or incremental project scan
8. pm_find       — exact/partial symbol lookup with location, callers, callees
9. pm_orphans    — dead-code detection: entities with no inbound dependencies
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Context object (passed to every handler)
# ---------------------------------------------------------------------------

@dataclass
class MCPContext:
    db_root:        Path
    db_name:        str
    writer:         Any    # EntityWriter
    index:          Any    # NameIndex
    file_manifest:  Any    # FileManifest
    project_root:   Optional[str] = None   # default project dir for scan/delta
    scan_lock:      Optional[Any] = None   # threading.Lock — shared with AutoScanner
    auto_scanner:   Optional[Any] = None   # AutoScanner instance (when --watch active)


# ---------------------------------------------------------------------------
# Tool schemas  (MCP 2024-11-05 format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "pm_context",
        "description": (
            "Retrieve a focused context package relevant to a coding task. "
            "Keyword-scores all entities in the knowledge graph against the task "
            "description, seeds from the best matches (and any named anchor entities), "
            "then expands by following relations. "
            "Use this BEFORE starting any non-trivial feature or refactor so you "
            "understand the existing architecture and avoid breaking changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language description of the task, e.g. 'add rate limiting to the auth endpoints'.",
                },
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of entity names to anchor the search on (boosted in scoring).",
                    "default": [],
                },
                "detail_level": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": (
                        "high=modules/services/decisions/goals/constraints, "
                        "medium=+classes/components, "
                        "low=+functions/endpoints/models (default: medium)"
                    ),
                    "default": "medium",
                },
                "depth": {
                    "type": "integer",
                    "description": "Relation-expansion hops beyond keyword seeds (0–2). Default 1.",
                    "default": 1,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum entities to include (default 30).",
                    "default": 30,
                },
                "slim": {
                    "type": "boolean",
                    "description": (
                        "Slim output: one line per entity showing name + file:line only. "
                        "Cuts token cost ~65% vs full mode. "
                        "Use when you only need to know what files to read, not what the entities do."
                    ),
                    "default": False,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "pm_impact",
        "description": (
            "Find all entities that would be affected if the named entity changes. "
            "Traverses dependency-propagating relations (calls, imports, depends_on, "
            "uses, reads_from, etc.) outward from the subject. "
            "Use before refactoring or deleting a module/class to understand the blast radius."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Name or ID of the entity to analyse.",
                },
                "depth": {
                    "type": "integer",
                    "description": "BFS depth: 1=direct dependents, 2=transitive (default), 3–4=wide radius.",
                    "default": 2,
                },
                "slim": {
                    "type": "boolean",
                    "description": (
                        "Slim output: one line per entity showing name + file:line only. "
                        "Cuts token cost ~65% vs full mode."
                    ),
                    "default": False,
                },
            },
            "required": ["entity"],
        },
    },
    {
        "name": "pm_path",
        "description": (
            "Find the shortest connection between two entities in the knowledge graph. "
            "Traverses all relation kinds in both directions (undirected). "
            "Useful for answering 'how does the auth system connect to the payment flow?' "
            "or tracing why a change in one module might affect another."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_entity": {
                    "type": "string",
                    "description": "Name or ID of the starting entity.",
                },
                "to_entity": {
                    "type": "string",
                    "description": "Name or ID of the destination entity.",
                },
                "max_hops": {
                    "type": "integer",
                    "description": "Maximum path length to search (default 6).",
                    "default": 6,
                },
            },
            "required": ["from_entity", "to_entity"],
        },
    },
    {
        "name": "pm_contribute",
        "description": (
            "Record agent-discovered knowledge back into the project graph. "
            "Accepts property updates, new relation declarations, and a free-text "
            "rationale that is stored as a dated timeline event. "
            "Call this after implementing a feature or making an architectural decision "
            "so future agents (and developers) can see why things are the way they are."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity to update.",
                },
                "properties": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Key-value property updates to merge into the entity.",
                    "default": {},
                },
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind":        {"type": "string"},
                            "target_name": {"type": "string"},
                            "note":        {"type": "string"},
                        },
                        "required": ["kind", "target_name"],
                    },
                    "description": "New relations to add, e.g. [{kind: depends_on, target_name: RateLimiter}].",
                    "default": [],
                },
                "rationale": {
                    "type": "string",
                    "description": "Free-text explanation stored as a timeline event.",
                    "default": "",
                },
                "source": {
                    "type": "string",
                    "description": "Identifier for the calling agent (default: 'agent').",
                    "default": "agent",
                },
            },
            "required": ["entity_name"],
        },
    },
    {
        "name": "pm_stats",
        "description": (
            "Return a quick overview of the ProjectMapper database: "
            "entity counts by type, file manifest coverage, and last scan status. "
            "Use at the start of a session to understand what's already been indexed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "pm_delta",
        "description": (
            "Show what has changed in the project since the last scan — "
            "new files, modified files, and deleted files — without making any "
            "database changes. "
            "Use to decide whether a re-scan is needed, or to preview "
            "what an incremental scan would process."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Absolute path to the project directory. "
                                   "Uses the server default if omitted.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "pm_find",
        "description": (
            "Look up a symbol by name and return its definition location, callers, "
            "and callees. Searches by exact name first (case-insensitive), then "
            "suffix/method match, then substring. "
            "Use this when you know — or partially know — the name of a function, "
            "class, or module and need to find where it lives, what calls it, "
            "and what it calls. Faster and more precise than pm_context for "
            "direct symbol lookups."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Symbol name to look up, e.g. 'UserService', 'get_user', "
                        "'auth'. Exact match tried first; partial matches returned "
                        "if no exact match."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matches to return when multiple symbols share the name (default 10).",
                    "default": 10,
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "pm_orphans",
        "description": (
            "Find entities that have no inbound calls, imports, or dependencies — "
            "potential dead code. Entry points, dunder methods, and test functions "
            "are filtered out automatically. "
            "Use before a cleanup pass to identify candidates for removal. "
            "Note: dynamic dispatch, decorator-registered handlers, and public API "
            "won't have graph callers — review results before deleting anything."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Limit to specific entity types, e.g. ['function', 'class']. "
                        "Returns all code types if omitted."
                    ),
                    "default": [],
                },
                "include_modules": {
                    "type": "boolean",
                    "description": "Include module-level entities (files/packages, often entry points). Default false.",
                    "default": False,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum entities to return (default 100).",
                    "default": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "pm_scan",
        "description": (
            "Scan a project directory and populate the knowledge graph via static AST analysis. "
            "Creates module/class/function entities and wires their relations. "
            "With incremental=true (default) only changed files are reprocessed. "
            "By default this call BLOCKS until the scan completes. "
            "Pass background=true to return immediately and poll pm_stats for progress — "
            "recommended for large projects (500+ files) over MCP to avoid timeouts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Absolute path to the project directory to scan.",
                },
                "incremental": {
                    "type": "boolean",
                    "description": "Skip files whose hash hasn't changed (default true).",
                    "default": True,
                },
                "concurrency": {
                    "type": "integer",
                    "description": "Parallel file processing limit (default 4).",
                    "default": 4,
                },
                "background": {
                    "type": "boolean",
                    "description": (
                        "Start scan in a background thread and return immediately (default false). "
                        "Use background=true for large projects to avoid MCP client timeouts; "
                        "then call pm_stats to check when the scan completes."
                    ),
                    "default": False,
                },
            },
            "required": ["project_root"],
        },
    },
]


# ---------------------------------------------------------------------------
# Text-formatting helpers
# ---------------------------------------------------------------------------

def _prop_line(entity: dict[str, Any]) -> str:
    """Single-line label: 'Name [type/kind] — summary'"""
    name    = entity.get("name", "?")
    etype   = entity.get("type", "")
    kind    = entity.get("kind", "")
    summary = entity.get("sections", {}).get("core", {}).get("summary", "")
    label   = kind if kind and kind != etype else etype
    summary_part = f" — {summary[:80]}" if summary else ""
    return f"  * {name} [{label}]{summary_part}"


def _entity_block(entity: dict[str, Any], *, show_relations: bool = False) -> str:
    """Multi-line entity description for context results."""
    # Slim stub: returned by _entity_stub(slim=True) — only name + file_path + line.
    # No id, no type, no sections. Render as a compact single line.
    if "sections" not in entity and "id" not in entity and "type" not in entity:
        name = entity.get("name", "?")
        fp   = entity.get("file_path", "")
        line = entity.get("line", "")
        via  = entity.get("via", "")
        loc  = f" — {fp}:{line}" if fp and line else (f" — {fp}" if fp else "")
        via_part = f" (via: {via})" if via else ""
        return f"  * {name}{loc}{via_part}"

    name      = entity.get("name", "?")
    etype     = entity.get("type", "")
    kind      = entity.get("kind", "")
    status    = entity.get("status", "active")

    if "sections" in entity:
        core      = entity["sections"].get("core", {})
        props     = entity["sections"].get("properties", {})
        relations = entity["sections"].get("relations", [])
    else:
        # Flat stub from context_query / _entity_stub() — fields live at root level
        core      = entity
        props     = entity
        relations = []

    label = kind if kind and kind != etype else etype
    if status not in ("active", ""):
        label += f", {status}"

    lines = [f"  [{name}] ({label})"]

    summary = core.get("summary", "")
    if summary:
        lines.append(f"    Summary: {summary[:200]}")

    tags = core.get("tags", [])
    if tags:
        lines.append(f"    Tags:    {', '.join(tags[:8])}")

    # Exclude stub meta-fields so they don't appear as spurious properties
    _SKIP = {"file_path", "line_start", "line_end", "id", "name", "type",
              "kind", "status", "tags", "summary", "relevance_score", "hop", "via"}
    useful_props = {k: v for k, v in props.items() if k not in _SKIP and v}
    if useful_props:
        for k, v in list(useful_props.items())[:4]:
            lines.append(f"    {k}: {str(v)[:80]}")

    if show_relations and relations:
        for r in relations[:5]:
            lines.append(f"    -> {r.get('kind')} {r.get('target_name', r.get('target_id', '?'))}")

    if "sections" in entity:
        timeline = entity["sections"].get("timeline", [])
        if timeline:
            lines.append("    Timeline:")
            for entry in timeline[-3:]:
                lines.append(f"      [{entry.get('date', '')}] {entry.get('event', '')[:120]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_pm_context(args: dict[str, Any], ctx: MCPContext) -> str:
    from .query import build_entity_map, context_query

    q            = args.get("query", "").strip()
    anchors      = args.get("entities") or []
    detail_level = args.get("detail_level", "medium")
    depth        = max(0, min(int(args.get("depth", 1)), 2))
    max_results  = min(int(args.get("max_results", 30)), 60)
    slim         = bool(args.get("slim", False))

    if not q:
        raise ValueError("'query' is required")

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = context_query(
        q, entity_map, ctx.index,
        anchor_names=anchors,
        max_seeds=10,
        expansion_hops=depth,
        detail_level=detail_level,
        max_results=max_results,
        slim=slim,
    )

    if not result.get("total"):
        return f"No entities found for: {q!r}\nTry running pm_scan to populate the graph."

    lines = [
        f"Context for task: {q!r}",
        f"Detail level: {detail_level}  |  Entities: {result['total']}  |  ~{result.get('token_estimate', 0)} tokens",
        "",
    ]

    by_type: dict[str, list[dict]] = result.get("by_type", {})
    # Sort by type priority
    type_order = ["decision", "goal", "constraint", "service", "module",
                  "workflow", "component", "class", "config", "dependency",
                  "function", "endpoint", "model"]
    ordered_types = [t for t in type_order if t in by_type] + \
                    [t for t in by_type if t not in type_order]

    for etype in ordered_types:
        entities = by_type[etype]
        if not entities:
            continue
        heading = etype.upper() + ("S" if not etype.endswith("s") else "")
        lines.append(f"{heading} ({len(entities)}):")
        for e in entities:
            lines.append(_entity_block(e))
        lines.append("")

    return "\n".join(lines).rstrip()


def handle_pm_impact(args: dict[str, Any], ctx: MCPContext) -> str:
    from .query import build_entity_map, impact_query

    entity_name = args.get("entity", "").strip()
    depth       = max(1, min(int(args.get("depth", 2)), 4))
    slim        = bool(args.get("slim", False))

    if not entity_name:
        raise ValueError("'entity' is required")

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = impact_query(entity_name, entity_map, ctx.index, max_depth=depth, slim=slim)

    if result.get("not_found"):
        return (
            f"Entity {entity_name!r} not found in the graph.\n"
            "Check spelling or run pm_stats to see what's indexed."
        )

    # subject is an _entity_stub dict (name, type, kind, …)
    subject_raw = result.get("subject", {})
    subject     = subject_raw.get("name", entity_name) if isinstance(subject_raw, dict) else str(subject_raw)
    affected    = result.get("affected", [])
    total    = result.get("total", 0)

    if total == 0:
        return (
            f"Impact analysis for: {subject}\n\n"
            "No dependents found. Nothing in the graph depends on this entity."
        )

    lines = [
        f"Impact analysis for: {subject}",
        f"Depth: {depth} hops  |  Affected: {total} entit{'y' if total == 1 else 'ies'}",
        "",
    ]

    # Group by hop
    by_hop: dict[int, list[dict]] = {}
    for item in affected:
        h = item.get("hop", 1)
        by_hop.setdefault(h, []).append(item)

    for hop in sorted(by_hop):
        items = by_hop[hop]
        label = "direct dependent" if hop == 1 else f"transitive (hop {hop})"
        lines.append(f"HOP {hop} — {label} ({len(items)}):")
        for item in items:
            name  = item.get("name", item.get("entity_id", "?"))
            via   = item.get("via", "")
            via_str = f"  (via: {via})" if via else ""
            if slim or ("type" not in item and "entity_id" not in item):
                fp   = item.get("file_path", "")
                line = item.get("line", "")
                loc  = f" — {fp}:{line}" if fp and line else (f" — {fp}" if fp else "")
                lines.append(f"  * {name}{loc}{via_str}")
            else:
                etype = item.get("type", "")
                summary = item.get("summary", "")
                desc  = f" — {summary[:60]}" if summary else ""
                lines.append(f"  * {name} [{etype}]{desc}{via_str}")
        lines.append("")

    lines.append(
        "If you change or delete this entity, review all listed dependents."
    )
    return "\n".join(lines).rstrip()


def handle_pm_path(args: dict[str, Any], ctx: MCPContext) -> str:
    from .query import build_entity_map, shortest_path

    from_name = args.get("from_entity", "").strip()
    to_name   = args.get("to_entity", "").strip()
    max_hops  = max(2, min(int(args.get("max_hops", 6)), 8))

    if not from_name or not to_name:
        raise ValueError("'from_entity' and 'to_entity' are required")

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = shortest_path(from_name, to_name, entity_map, ctx.index, max_hops=max_hops)

    not_found_msg = result.get("not_found_message", "")
    if not_found_msg:
        return (
            f"Could not find path: {from_name!r} -> {to_name!r}\n{not_found_msg}"
        )

    if not result.get("found"):
        return (
            f"No path found between {from_name!r} and {to_name!r} "
            f"within {max_hops} hops.\n"
            "They may be in disconnected parts of the graph."
        )

    path   = result.get("path", [])
    length = result.get("length", 0)

    lines = [
        f"Shortest path: {from_name} -> {to_name}",
        f"Length: {length} hop{'s' if length != 1 else ''}",
        "",
        "Chain:",
    ]

    # Path steps are _entity_stub dicts: {name, type, kind, relation, relation_reverse}
    # relation_reverse=True means this node was reached via a reversed edge —
    # i.e. the actual graph edge points the other way.
    chain_parts = []
    for step in path:
        node    = step.get("name", step.get("id", "?"))
        rel     = step.get("relation", "")
        is_rev  = step.get("relation_reverse", False)
        if rel:
            chain_parts.append(f"{node} {'<--' + rel + '--' if is_rev else '--' + rel + '-->'}")
        else:
            chain_parts.append(node)

    # Format chain: wrap at ~80 chars
    chain_str = " ".join(chain_parts)
    lines.append(f"  {chain_str}")

    return "\n".join(lines)


def handle_pm_contribute(args: dict[str, Any], ctx: MCPContext) -> str:
    from .query import build_entity_map, apply_contribution, _resolve_entity

    entity_name = args.get("entity_name", "").strip()
    properties  = args.get("properties", {}) or {}
    relations   = args.get("relations", []) or []
    rationale   = args.get("rationale", "") or ""
    source      = args.get("source", "agent") or "agent"

    if not entity_name:
        raise ValueError("'entity_name' is required")

    entity_map = build_entity_map(ctx.writer)
    entity     = _resolve_entity(entity_name, entity_map, ctx.index)
    if not entity:
        return (
            f"Entity {entity_name!r} not found. "
            "Check spelling or run pm_stats to see what's indexed."
        )

    summary = apply_contribution(
        entity, properties, relations, rationale, source,
        ctx.writer, ctx.index,
    )

    # Both properties_set and relations_added are lists of strings
    props_set  = summary.get("properties_set", [])
    rels_added = summary.get("relations_added", [])
    props_count = len(props_set) if isinstance(props_set, list) else int(props_set)
    rels_count  = len(rels_added) if isinstance(rels_added, list) else int(rels_added)

    lines = [
        f"Contribution recorded for: {entity_name}",
        f"  Entity ID: {summary.get('entity_id', '?')}",
        f"  Properties set: {props_count}",
        f"  Relations added: {rels_count}",
    ]

    if rationale:
        lines.append(f"  Timeline event: {rationale[:120]}")

    if not summary.get("changes_made", True):
        lines.append("  (no new changes — everything was already up to date)")

    return "\n".join(lines)


def handle_pm_stats(args: dict[str, Any], ctx: MCPContext) -> str:
    from .scanner import scan_status, SCANINFO

    scan = scan_status(ctx.db_root)
    fm   = ctx.file_manifest.stats()

    pm_types = {
        "module", "service", "component", "class", "function",
        "endpoint", "model", "workflow", "config", "dependency",
        "decision", "goal", "constraint",
    }
    type_counts: dict[str, int] = {}
    total = 0
    stubs = 0
    try:
        for e in ctx.writer.list_all():
            t = e.get("type", "other")
            if t in pm_types:
                type_counts[t] = type_counts.get(t, 0) + 1
                total += 1
        for e in ctx.writer.list_stubs():
            if e.get("type") in pm_types:
                stubs += 1
    except Exception:
        pass

    lines = [
        f"Database: {ctx.db_name}",
        f"Root:     {ctx.db_root}",
        "",
        f"Entities: {total} active  ({stubs} stubs)",
    ]

    if type_counts:
        by_count = sorted(type_counts.items(), key=lambda x: -x[1])
        lines.append("  Breakdown: " + "  ".join(f"{t}:{c}" for t, c in by_count))

    lines.append("")
    lines.append(f"Files tracked: {fm.get('total_files', 0)}")
    by_lang = fm.get("by_language", {})
    if by_lang:
        lang_str = "  ".join(f"{lang}:{n}" for lang, n in list(by_lang.items())[:5])
        lines.append(f"  By language: {lang_str}")

    lines.append("")
    status    = scan.get("status", "never run")
    started   = scan.get("started_at", "")
    completed = scan.get("completed_at", "")
    proj      = scan.get("project_root", "")
    lines.append(f"Last scan: {status}")
    if proj:
        lines.append(f"  Project:   {proj}")
    if started:
        lines.append(f"  Started:   {started}")
    if completed:
        lines.append(f"  Completed: {completed}")

    scan_stats = scan.get("stats", {})
    if scan_stats:
        lines.append(
            f"  Files:     {scan_stats.get('files_scanned', 0)} scanned  "
            f"{scan_stats.get('files_skipped_unchanged', 0)} skipped  "
            f"{scan_stats.get('files_deleted', 0)} deleted"
        )
        lines.append(
            f"  Entities:  {scan_stats.get('entities_created', 0)} created  "
            f"{scan_stats.get('entities_updated', 0)} updated  "
            f"{scan_stats.get('entities_pruned', 0)} pruned"
        )

    lines.append("")
    if ctx.auto_scanner is not None:
        ws = ctx.auto_scanner.status_dict()
        state = "active" if ws["active"] else "stopped"
        lines.append(
            f"Auto-scan: {state}  "
            f"(poll={ws['poll_interval_s']:.0f}s  debounce={ws['debounce_s']:.0f}s)"
        )
        lines.append(f"  Project:    {ws['project_root']}")
        lines.append(f"  Scans run:  {ws['scan_count']}")
        last_scan_info = ws["last_scan"]
        if ws["last_scan_files"] and ws["last_scan"] != "never":
            last_scan_info += f"  ({ws['last_scan_files']} file(s))"
        lines.append(
            f"  Last check: {ws['last_check']}  |  Last scan: {last_scan_info}"
        )
    else:
        lines.append("Auto-scan: off  (start server with --watch to enable)")

    return "\n".join(lines)


def handle_pm_delta(args: dict[str, Any], ctx: MCPContext) -> str:
    from .delta import compute_delta

    project_root = args.get("project_root") or ctx.project_root
    if not project_root:
        return (
            "No project_root specified and no default configured.\n"
            "Pass project_root or start the server with --project-root."
        )

    project_root = str(Path(project_root).resolve())

    try:
        delta = compute_delta(project_root, ctx.file_manifest)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ValueError(str(exc))

    lines = [
        f"Delta for: {project_root}",
        f"Database:  {ctx.db_name}",
        "",
        f"  New files:      {len(delta.new_files)}",
        f"  Modified files: {len(delta.modified_files)}",
        f"  Deleted files:  {len(delta.deleted_files)}",
        f"  Unchanged:      {delta.unchanged_count}",
        f"  Total on disk:  {delta.total_on_disk}",
        f"  In manifest:    {delta.total_in_manifest}",
        "",
    ]

    if not delta.has_changes:
        lines.append("No changes detected — graph is up to date.")
        return "\n".join(lines)

    lines.append("Changes detected:")

    if delta.modified_files:
        lines.append(f"\nModified ({len(delta.modified_files)}):")
        for f in delta.modified_files[:20]:
            eids = f.entity_ids
            note = f"  [{len(eids)} entit{'y' if len(eids) == 1 else 'ies'}]" if eids else ""
            lines.append(f"  * {f.path}{note}")
        if len(delta.modified_files) > 20:
            lines.append(f"  ... and {len(delta.modified_files) - 20} more")

    if delta.new_files:
        lines.append(f"\nNew ({len(delta.new_files)}):")
        for f in delta.new_files[:20]:
            lines.append(f"  + {f.path}")
        if len(delta.new_files) > 20:
            lines.append(f"  ... and {len(delta.new_files) - 20} more")

    if delta.deleted_files:
        lines.append(f"\nDeleted ({len(delta.deleted_files)}):")
        for path in delta.deleted_files[:20]:
            lines.append(f"  - {path}")
        if len(delta.deleted_files) > 20:
            lines.append(f"  ... and {len(delta.deleted_files) - 20} more")

    lines.append("")
    lines.append("Run pm_scan with incremental=true to process these changes.")
    return "\n".join(lines)


def handle_pm_scan(args: dict[str, Any], ctx: MCPContext) -> str:
    import asyncio, threading, time
    from .scanner import run_scan

    project_root = args.get("project_root") or ctx.project_root
    incremental  = bool(args.get("incremental", True))
    concurrency  = max(1, min(int(args.get("concurrency", 4)), 8))
    background   = bool(args.get("background", False))

    if not project_root:
        raise ValueError(
            "project_root is required (or start the server with --project-root)"
        )

    project_path = Path(project_root).resolve()
    project_root = str(project_path)
    if not project_path.exists():
        raise ValueError(f"Project root does not exist: {project_root}")
    if not project_path.is_dir():
        raise ValueError(f"Not a directory: {project_root}")

    lock = ctx.scan_lock

    if background:
        # Non-blocking: start scan in background thread, return immediately
        def _run_bg():
            if lock is not None:
                lock.acquire()
            try:
                asyncio.run(
                    run_scan(
                        db_root=ctx.db_root,
                        project_root=project_root,
                        db_name=ctx.db_name,
                        writer=ctx.writer,
                        index=ctx.index,
                        file_manifest=ctx.file_manifest,
                        concurrency=concurrency,
                        incremental=incremental,
                    )
                )
            finally:
                if lock is not None:
                    lock.release()

        t = threading.Thread(target=_run_bg, daemon=True)
        t.start()
        mode = "incremental" if incremental else "full"
        return (
            f"Scan started ({mode}): {project_root}\n"
            f"Database: {ctx.db_name}\n\n"
            "Scan is running in the background.\n"
            "Call pm_stats to check progress — status will change from 'scanning' to 'completed'."
        )

    # Blocking mode (default)
    if lock is not None:
        lock.acquire()
    t0 = time.monotonic()
    try:
        asyncio.run(
            run_scan(
                db_root=ctx.db_root,
                project_root=project_root,
                db_name=ctx.db_name,
                writer=ctx.writer,
                index=ctx.index,
                file_manifest=ctx.file_manifest,
                concurrency=concurrency,
                incremental=incremental,
            )
        )
    finally:
        elapsed = time.monotonic() - t0
        if lock is not None:
            lock.release()

    # Read the final scan stats
    from .scanner import scan_status
    status = scan_status(ctx.db_root)
    stats  = status.get("stats", {})

    lines = [
        f"Scan {'completed' if status.get('status') == 'completed' else status.get('status', '?')}: "
        f"{project_root}",
        f"Database:   {ctx.db_name}",
        f"Duration:   {elapsed:.1f}s",
        "",
        f"Files:    {stats.get('files_scanned', 0)} scanned  "
        f"{stats.get('files_skipped_unchanged', 0)} skipped (unchanged)  "
        f"{stats.get('files_skipped_unsupported', 0)} skipped (binary/empty)  "
        f"{stats.get('files_deleted', 0)} deleted",
        f"Entities: {stats.get('entities_created', 0)} created  "
        f"{stats.get('entities_updated', 0)} updated  "
        f"{stats.get('entities_pruned', 0)} pruned  "
        f"{stats.get('entities_retired', 0)} retired",
    ]
    errs = stats.get("errors", [])
    if errs:
        lines.append(f"Errors:   {len(errs)} (first: {errs[0].get('error', '')[:80]})")

    return "\n".join(lines)


def _format_find_result(m: dict[str, Any]) -> str:
    """Format a single pm_find match as a detailed block."""
    name      = m.get("name", "?")
    etype     = m.get("type", "")
    kind      = m.get("kind") or etype
    fp        = m.get("file_path", "")
    line_start = str(m.get("line_start", ""))
    line_end   = str(m.get("line_end", ""))

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
            lines.append(f"  * {c['name']} [{c.get('type', '?')}]  → {c.get('via', '?')}")
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


def handle_pm_find(args: dict[str, Any], ctx: MCPContext) -> str:
    from .query import build_entity_map, find_query

    name = args.get("name", "").strip()
    if not name:
        raise ValueError("'name' is required")

    max_results = min(int(args.get("max_results", 10)), 20)

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = find_query(name, entity_map, ctx.index, max_results=max_results)

    if result.get("not_found"):
        return (
            f"Symbol {name!r} not found in the graph.\n"
            "Check spelling, or run pm_scan if the codebase hasn't been indexed yet."
        )

    matches = result.get("matches", [])
    total   = result.get("total", 0)

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
        fp    = m.get("file_path", "")
        line  = str(m.get("line_start", ""))
        loc   = f"  {fp}:{line}" if fp and line else f"  {fp}" if fp else ""
        label = m.get("kind") or m.get("type") or "?"
        desc  = f" — {m['summary'][:60]}" if m.get("summary") else ""
        lines.append(f"  {i}. {m['name']} [{label}]{loc}{desc}")

    lines.append("")
    lines.append(
        "Use a more specific name to get the detailed view, "
        "or pm_context for task-oriented search."
    )
    return "\n".join(lines)


def handle_pm_orphans(args: dict[str, Any], ctx: MCPContext) -> str:
    from .query import build_entity_map, orphan_query

    types_filter    = args.get("types") or None
    include_modules = bool(args.get("include_modules", False))
    max_results     = min(int(args.get("max_results", 100)), 200)

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = orphan_query(
        entity_map,
        types=types_filter,
        include_modules=include_modules,
        max_results=max_results,
    )

    total     = result.get("total", 0)
    skipped   = result.get("skipped_count", 0)
    orphans   = result.get("orphans", [])

    if total == 0:
        return (
            "No orphaned entities found — everything has at least one inbound dependency.\n"
            f"({skipped} entry points / dunder methods / test functions filtered out.)"
        )

    lines = [
        f"Orphaned entities (no inbound calls/imports): {total}",
        f"Filtered out: {skipped} entry points / dunder methods / test functions",
        "",
        "Note: dynamic callers (decorators, dynamic dispatch, reflection) won't",
        "      appear in the graph. Review before removing anything.",
        "",
    ]

    by_type: dict[str, list[dict]] = {}
    for o in orphans:
        by_type.setdefault(o.get("type", "other"), []).append(o)

    type_order = ["class", "function", "endpoint", "model", "service",
                  "component", "workflow", "config", "module", "other"]
    ordered_types = [t for t in type_order if t in by_type] + \
                    [t for t in by_type if t not in type_order]

    for etype in ordered_types:
        items = by_type[etype]
        heading = etype.upper() + ("S" if not etype.endswith("s") else "")
        lines.append(f"{heading} ({len(items)}):")
        for o in items:
            name    = o.get("name", "?")
            fp      = o.get("file_path", "")
            line    = str(o.get("line_start", ""))
            loc     = f"  {fp}:{line}" if fp and line else f"  {fp}" if fp else ""
            summary = o.get("summary", "")
            desc    = f"\n      {summary[:80]}" if summary else ""
            lines.append(f"  * {name}{loc}{desc}")
        lines.append("")

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

HANDLERS = {
    "pm_context":    handle_pm_context,
    "pm_impact":     handle_pm_impact,
    "pm_path":       handle_pm_path,
    "pm_contribute": handle_pm_contribute,
    "pm_stats":      handle_pm_stats,
    "pm_delta":      handle_pm_delta,
    "pm_scan":       handle_pm_scan,
    "pm_find":       handle_pm_find,
    "pm_orphans":    handle_pm_orphans,
}
