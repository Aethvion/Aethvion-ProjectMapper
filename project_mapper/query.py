"""
project_mapper/query.py
Agent-optimized query engine for ProjectMapper.

Five query primitives:
  impact_query   — "what is affected if I change entity X?" (directed BFS)
  context_query  — "I'm working on X, what should I know?" (keyword + expansion)
  shortest_path  — "how does entity A connect to entity B?" (undirected BFS)
  find_query     — "where is symbol X defined, who calls it?" (name lookup)
  orphan_query   — "what entities have no inbound dependencies?" (dead code)

All functions accept a pre-loaded entity_map for performance. Build it once per
request with build_entity_map() and pass it to whichever queries you need.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Relation kinds that propagate impact TOWARD entities that depend on X.
# If entity A has relation KIND → entity X, then changing X may affect A.
IMPACT_INCOMING_KINDS: frozenset[str] = frozenset({
    "calls",
    "imports",
    "depends_on",
    "uses",
    "reads_from",
    "writes_to",
    "triggered_by",
    "implements",
    "extends",
    "configured_by",
    "tests",
})

# Entity types shown at each detail level (from coarsest to finest)
_DETAIL_LEVELS: dict[str, frozenset[str]] = {
    "high":   frozenset({"module", "service", "decision", "goal", "constraint", "workflow"}),
    "medium": frozenset({"module", "service", "class", "component", "decision",
                         "goal", "constraint", "workflow", "config", "dependency"}),
    "low":    frozenset({"module", "service", "class", "component", "function",
                         "endpoint", "model", "decision", "goal", "constraint",
                         "workflow", "config", "dependency"}),
}

# Rough token estimate per entity (name + summary + key properties)
_TOKENS_PER_ENTITY = 80


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def build_entity_map(writer: Any) -> dict[str, dict]:
    """
    Load all non-deleted entities into a dict keyed by entity_id.
    Expensive the first time; cache at the call site if making multiple queries.
    """
    return {e["id"]: e for e in writer.list_all(include_deleted=False)}


def _resolve_entity(
    name_or_id: str,
    entity_map: dict[str, dict],
    index: Any,
) -> Optional[dict]:
    """Resolve a name or ID to an entity dict."""
    # Try direct ID lookup first
    if name_or_id in entity_map:
        return entity_map[name_or_id]
    # Try NameIndex
    eid = index.get(name_or_id)
    if eid and eid in entity_map:
        return entity_map[eid]
    return None


def _entity_stub(
    entity:      dict,
    hop:         int  = 0,
    via:         str  = "",
    slim:        bool = False,
    max_summary: int  = 180,
) -> dict:
    """
    Return an agent-friendly representation of an entity.

    slim=False (default) — full stub: id, name, type, kind, status, summary,
                           tags, file_path, architectural_pattern, hop, via.
    slim=True            — minimal stub: name, file_path only (+ hop/via when
                           present).  ~16 tokens per entity vs ~90 for full.
    max_summary          — maximum characters of the summary field to include
                           (default 180, full).  Pass 0 to strip the summary
                           entirely.  Ignored when slim=True.
    """
    props = entity.get("sections", {}).get("properties", {})

    if slim:
        stub: dict[str, Any] = {"name": entity.get("name", "")}
        if props.get("file_path"):
            stub["file_path"] = props["file_path"]
        if props.get("line_start"):
            stub["line"] = props["line_start"]
        if hop > 0:
            stub["hop"] = hop
        if via:
            stub["via"] = via
        return stub

    core    = entity.get("sections", {}).get("core", {})
    summary = core.get("summary", "")
    stub = {
        "id":     entity["id"],
        "name":   entity.get("name", ""),
        "type":   entity.get("type", ""),
        "kind":   entity.get("kind"),
        "status": entity.get("status", "active"),
        "tags":   core.get("tags", [])[:5],
    }
    if max_summary > 0 and summary:
        stub["summary"] = summary[:max_summary]
    if props.get("file_path"):
        stub["file_path"] = props["file_path"]
    if props.get("line_start"):
        stub["line"] = props["line_start"]
    if props.get("architectural_pattern"):
        stub["architectural_pattern"] = props["architectural_pattern"]
    if hop > 0:
        stub["hop"] = hop
    if via:
        stub["via"] = via
    return stub


def _is_test_entity(entity: dict) -> bool:
    """Return True if the entity lives in a test file or test directory."""
    file_path = (
        entity.get("sections", {})
              .get("properties", {})
              .get("file_path", "")
    )
    if not file_path:
        return False
    return (
        "tests/" in file_path
        or "/test_" in file_path
        or file_path.startswith("test_")
    )


# ---------------------------------------------------------------------------
# 1. Impact Analysis
# ---------------------------------------------------------------------------

def build_reverse_impact_adj(
    entity_map: dict[str, dict],
) -> dict[str, list[tuple[str, str, str]]]:
    """
    Build a reverse adjacency map for impact traversal.

    Returns  { target_id → [(source_id, source_name, relation_kind)] }
    for all entities whose relation kind is in IMPACT_INCOMING_KINDS.
    """
    rev: dict[str, list[tuple[str, str, str]]] = {}
    for eid, entity in entity_map.items():
        ename = entity.get("name", eid)
        for rel in entity.get("sections", {}).get("relations", []):
            kind      = rel.get("kind", "")
            target_id = rel.get("target_id", "")
            if kind in IMPACT_INCOMING_KINDS and target_id:
                rev.setdefault(target_id, []).append((eid, ename, kind))
    return rev


def impact_query(
    subject:       str,
    entity_map:    dict[str, dict],
    index:         Any,
    max_depth:     int = 2,
    via_kinds:     Optional[list[str]] = None,
    exclude_tests: bool = True,
    slim:          bool = False,
    summary_depth: int = 1,
) -> dict[str, Any]:
    """
    Find all entities that would be affected if *subject* changes.

    via_kinds, when provided, restricts which incoming relation types are
    followed during traversal.

    exclude_tests=True (default) removes entities whose file_path lives inside
    a tests/ directory or whose filename starts with test_.

    slim=True returns only name + file_path (+ hop/via) per affected entity,
    cutting per-entity token cost from ~90 to ~16.

    summary_depth controls how far out summaries are included (ignored when
    slim=True). Default is 1: hop=1 entities get full summaries, hop=2+
    entities have their summary stripped.

    Returns a dict with:
      subject      — the resolved entity (always full, regardless of slim)
      affected     — list of affected entity stubs (with hop + via)
      total        — count of affected entities
      depth_used   — actual depth reached
      not_found    — True if subject could not be resolved
    """
    subject_entity = _resolve_entity(subject, entity_map, index)
    if subject_entity is None:
        return {
            "subject":   None,
            "affected":  [],
            "total":     0,
            "depth_used": 0,
            "not_found": True,
        }

    max_depth  = max(1, min(max_depth, 4))
    rev_adj    = build_reverse_impact_adj(entity_map)
    subject_id = subject_entity["id"]

    visited: dict[str, tuple[int, str]] = {}   # entity_id → (hop, via_path)
    queue:   deque[tuple[str, int, str]] = deque()
    queue.append((subject_id, 0, ""))

    while queue:
        current_id, hop, via_path = queue.popleft()
        if hop > max_depth:
            break

        for source_id, source_name, rel_kind in rev_adj.get(current_id, []):
            if source_id == subject_id or source_id in visited:
                continue
            if via_kinds is not None and rel_kind not in via_kinds:
                continue
            current_name = entity_map.get(current_id, {}).get("name", current_id)
            via = f"{rel_kind} → {current_name}" if via_path else rel_kind
            if via_path:
                via = f"{via_path} → {rel_kind}"
            visited[source_id] = (hop + 1, via)
            if hop + 1 <= max_depth:
                queue.append((source_id, hop + 1, via))

    affected = []
    for eid, (hop, via) in sorted(visited.items(), key=lambda x: x[1][0]):
        e = entity_map.get(eid)
        if e:
            if exclude_tests and _is_test_entity(e):
                continue
            ms = 180 if hop <= summary_depth else 0
            affected.append(_entity_stub(e, hop=hop, via=via, slim=slim, max_summary=ms))

    return {
        "subject":    _entity_stub(subject_entity),   # subject always full
        "affected":   affected,
        "total":      len(affected),
        "depth_used": max_depth,
        "not_found":  False,
    }


# ---------------------------------------------------------------------------
# 2. Task-Contextual Retrieval
# ---------------------------------------------------------------------------

def _name_words(entity_name: str) -> set[str]:
    """
    Split a PascalCase / camelCase name into lowercase words.
    'ProviderManager' → {'provider', 'manager'}
    'get_provider_manager' → {'get', 'provider', 'manager'}
    """
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", entity_name)
    spaced = re.sub(r"([a-z\d])([A-Z])", r"\1 \2", spaced)
    return set(re.findall(r"[a-z0-9]{2,}", spaced.lower()))


def _keyword_score(tokens: list[str], entity: dict) -> float:
    """
    Score an entity against query tokens using structure-aware field weighting.
    """
    core  = entity.get("sections", {}).get("core", {})
    props = entity.get("sections", {}).get("properties", {})

    name    = entity.get("name", "").lower()
    summary = core.get("summary", "").lower()
    tags    = " ".join(core.get("tags", [])).lower()
    aliases = " ".join(core.get("aliases", [])).lower()

    nwords     = _name_words(entity.get("name", ""))
    methods    = [m.strip().lower() for m in props.get("methods", "").split(",") if m.strip()]
    base_cls   = props.get("base_classes", "").lower()
    file_parts = [p for p in re.split(r"[/._\\]", props.get("file_path", "").lower())
                  if len(p) >= 2]
    signature  = props.get("signature", "").lower()

    score = 0.0
    for tok in tokens:
        if tok == name:
            score += 1.0
        elif tok in name:
            score += 0.7
        elif tok in nwords:
            score += 0.5

        if tok in summary[:300]:
            score += 0.6 if len(summary) > 60 else 0.4

        if tok in tags:
            score += 0.4

        if tok in base_cls:
            score += 0.45

        if tok in aliases:
            score += 0.35

        for method in methods:
            if tok in method or method in tok:
                score += 0.35
                break

        for part in file_parts:
            if tok == part:
                score += 0.3
                break
            if len(tok) >= 2 and tok in part:
                score += 0.15
                break

        if tok in signature:
            score += 0.15

    return round(score, 3)


# ---------------------------------------------------------------------------
# Vocabulary synonym map
# ---------------------------------------------------------------------------

_QUERY_SYNONYMS: dict[str, list[str]] = {
    # Security / auth
    "authentication":  ["security", "firewall", "auth"],
    "authorization":   ["security", "permissions", "auth"],
    "auth":            ["security", "firewall"],
    "login":           ["security", "auth"],
    "permissions":     ["security", "firewall"],
    # Logging / observability
    "logging":         ["logger"],
    "logs":            ["logger"],
    "log":             ["logger"],
    # Data persistence
    "database":        ["db", "aethviondb", "storage"],
    "persistence":     ["db", "storage"],
    "storage":         ["db", "aethviondb"],
    # Configuration
    "configuration":   ["config", "settings"],
    "settings":        ["config", "preferences"],
    "preferences":     ["config", "settings"],
    # Networking / web
    "routing":         ["router", "routes"],
    "routes":          ["router", "route"],
    "endpoint":        ["router", "routes"],
    "websocket":       ["ws"],
    "http":            ["server", "routes", "api"],
    # AI / models
    "llm":             ["provider", "model"],
    "model":           ["provider", "model"],
    "inference":       ["provider"],
    "generation":      ["provider", "generate"],
    # UI
    "interface":       ["ui", "dashboard", "routes"],
    "frontend":        ["dashboard", "ui"],
    "dashboard":       ["ui", "server"],
    # CLI
    "commandline":     ["cli"],
    "command":         ["cli", "routes"],
    # Task / workflow
    "queue":           ["task", "worker"],
    "worker":          ["task", "queue"],
    "job":             ["task", "queue"],
    "async":           ["worker", "task"],
}


# ---------------------------------------------------------------------------
# Constants for orphan / dead-code detection
# ---------------------------------------------------------------------------

# Names that are commonly entry points — not dead even if nothing calls them.
_ORPHAN_ENTRY_NAMES: frozenset[str] = frozenset({
    "main", "run", "start", "setup", "teardown", "configure", "create_app",
    "application", "app", "wsgi", "asgi", "celery", "init_app",
})

# Files whose entities are framework entry points or test fixtures — skip them.
_ORPHAN_SKIP_FILES: tuple[str, ...] = (
    "setup.py", "conftest.py", "wsgi.py", "asgi.py",
    "__init__.py", "__main__.py", "manage.py", "cli.py",
)

# Path segments that indicate third-party vendored assets.
# Entities from these directories are excluded from orphan results because
# nothing in the project graph calls into vendor internals directly.
# Kept at the query layer (not scan-time) so pm_find can still locate them.
_ORPHAN_VENDOR_DIRS: frozenset[str] = frozenset({
    "vendor", "node_modules", "bower_components",
})

# Any __dunder__ method — used implicitly by Python, never "called" in the graph.
_DUNDER_PAT: re.Pattern = re.compile(r"^__[a-z_]+__$")


_TOKENIZE_STOP: frozenset[str] = frozenset({
    "a","an","the","i","im","is","are","was","be","been","being",
    "in","on","at","to","for","of","and","or","but","not","with",
    "this","that","these","those","what","how","when","where","which",
    "my","me","we","our","if","do","did","have","has","had","it",
    "working","adding","need","want","know","should","would","could",
    "about","from","will","let","get","just","like","also","more",
    "use","used","uses","using","make","makes","made","take","takes",
    "its","all","can","into","via","new","do",
})


def _tokenize(text: str) -> list[str]:
    """
    Tokenize query text for keyword scoring.
    Splits on whitespace, punctuation AND camelCase/PascalCase boundaries.
    Deduplicates so repeated sub-tokens (e.g. 'format' in formatParams + formatStrategyName)
    don't double-score a single entity.
    """
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    spaced = re.sub(r"([a-z\d])([A-Z])", r"\1 \2", spaced)
    seen: set[str] = set()
    result: list[str] = []
    for t in re.findall(r"[a-z0-9_]{2,}", spaced.lower()):
        if t not in _TOKENIZE_STOP and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def context_query(
    q:            str,
    entity_map:   dict[str, dict],
    index:        Any,
    anchor_names: Optional[list[str]] = None,
    max_seeds:    int = 8,
    expansion_hops: int = 1,
    detail_level: str = "medium",
    max_results:  int = 40,
    slim:         bool = False,
) -> dict[str, Any]:
    """
    Return a focused context package relevant to the task described in *q*.

    slim=True returns only name + file_path per entity — useful when building
    a file-read list before diving into implementation detail.
    """
    base_tokens = _tokenize(q)
    extra: list[str] = []
    for tok in base_tokens:
        for syn in _QUERY_SYNONYMS.get(tok, []):
            if syn not in base_tokens and syn not in extra:
                extra.append(syn)
    tokens       = base_tokens + extra
    detail_types = _DETAIL_LEVELS.get(detail_level, _DETAIL_LEVELS["medium"])

    # ---- 1. Score all entities -------------------------------------------
    scored: list[tuple[float, dict]] = []
    for entity in entity_map.values():
        if entity.get("status") in ("deleted", "stub"):
            continue
        s = _keyword_score(tokens, entity)
        if s > 0:
            scored.append((s, entity))
    scored.sort(key=lambda x: -x[0])

    # ---- 2. Seed set: top-N from scoring + explicitly anchored names ------
    seed_ids: dict[str, float] = {}
    for score, entity in scored[:max_seeds]:
        seed_ids[entity["id"]] = score

    if anchor_names:
        for name in anchor_names:
            e = _resolve_entity(name, entity_map, index)
            if e and e["id"] not in seed_ids:
                seed_ids[e["id"]] = 1.5

    # ---- 3. Expand seed set by following relations -----------------------
    expanded_ids: dict[str, tuple[float, int]] = {}
    for sid, score in seed_ids.items():
        expanded_ids[sid] = (score, 0)

    if expansion_hops > 0:
        for sid in list(seed_ids.keys()):
            seed_entity = entity_map.get(sid, {})
            for rel in seed_entity.get("sections", {}).get("relations", []):
                tid = rel.get("target_id")
                if tid and tid in entity_map and tid not in expanded_ids:
                    expanded_ids[tid] = (0.1, 1)

    # ---- 4. Collect, filter by detail level, categorize ------------------
    by_type: dict[str, list[dict]] = {}
    all_stubs: list[dict] = []

    for eid, (score, hop) in sorted(expanded_ids.items(), key=lambda x: -x[1][0]):
        entity = entity_map.get(eid)
        if not entity:
            continue
        etype = entity.get("type", "other")
        if etype not in detail_types and hop > 0:
            continue
        stub = _entity_stub(entity, hop=hop, slim=slim)
        if not slim:
            stub["relevance_score"] = score
        by_type.setdefault(etype, []).append(stub)
        all_stubs.append(stub)
        if len(all_stubs) >= max_results:
            break

    for bucket in by_type.values():
        bucket.sort(key=lambda x: -x.get("relevance_score", 0))

    total = len(all_stubs)
    return {
        "query":          q,
        "tokens":         tokens[:12],
        "detail_level":   detail_level,
        "seeds_found":    len(seed_ids),
        "by_type":        by_type,
        "total":          total,
        "token_estimate": total * _TOKENS_PER_ENTITY,
    }


# ---------------------------------------------------------------------------
# 3. Shortest Path  (two-phase: semantic edges first, structural fallback)
# ---------------------------------------------------------------------------

_SEMANTIC_EDGE_KINDS: frozenset[str] = frozenset({
    "calls",
    "extends",
    "implements",
    "uses",
    "reads_from",
    "writes_to",
    "triggered_by",
    "configured_by",
    "tests",
})

_EXCEPTION_NAME_PAT: re.Pattern = re.compile(
    r"(Error|Exception|Warning|NotFound|NotSupported|Forbidden|Denied|Invalid)$",
    re.IGNORECASE,
)

_STRUCTURAL_EDGE_KINDS: frozenset[str] = frozenset({
    "contains",
    "imports",
    "depends_on",
    "related_to",
})


def _build_adjacency(
    entity_map: dict[str, dict],
    allowed_kinds: Optional[frozenset[str]],
) -> tuple[dict[str, list[tuple[str, str, str]]], dict[str, list[tuple[str, str, str]]]]:
    """
    Build forward and reverse adjacency dicts from the entity graph.

    Each adjacency entry is a 3-tuple: (neighbor_id, relation_kind, note).
    The *note* field carries the optional annotation stored on the relation
    (e.g. "via method_name" for calls edges).
    """
    fwd: dict[str, list[tuple[str, str, str]]] = {}
    rev: dict[str, list[tuple[str, str, str]]] = {}
    for eid, entity in entity_map.items():
        for rel in entity.get("sections", {}).get("relations", []):
            tid  = rel.get("target_id", "")
            kind = rel.get("kind", "related_to")
            note = rel.get("note", "")
            if tid and tid in entity_map:
                if allowed_kinds is None or kind in allowed_kinds:
                    fwd.setdefault(eid, []).append((tid, kind, note))
                    rev.setdefault(tid, []).append((eid, kind, note))
    return fwd, rev


_HUB_CALLS_THRESHOLD = 20


def _compute_skip_ids(
    entity_map: dict[str, dict],
    from_id:    str,
    to_id:      str,
) -> frozenset[str]:
    """
    Return entity IDs that should be skipped as BFS intermediaries.

    Skips: exception-named classes, test-file entities, high-fanin hub nodes.
    Source and destination are NEVER skipped.
    """
    protected = {from_id, to_id}
    skip: set[str] = set()

    calls_in_degree: dict[str, int] = {}
    for entity in entity_map.values():
        for rel in entity.get("sections", {}).get("relations", []):
            if rel.get("kind") == "calls":
                tid = rel.get("target_id", "")
                if tid and tid not in protected:
                    calls_in_degree[tid] = calls_in_degree.get(tid, 0) + 1

    for eid, entity in entity_map.items():
        if eid in protected:
            continue
        name      = entity.get("name", "")
        file_path = (
            entity.get("sections", {})
                  .get("properties", {})
                  .get("file_path", "")
        )
        if _EXCEPTION_NAME_PAT.search(name):
            skip.add(eid)
        elif file_path and (
            "tests/" in file_path
            or "/test_" in file_path
            or file_path.startswith("test_")
        ):
            skip.add(eid)
        elif calls_in_degree.get(eid, 0) >= _HUB_CALLS_THRESHOLD:
            skip.add(eid)

    return frozenset(skip)


def _bfs_path(
    from_id:    str,
    to_id:      str,
    to_entity:  dict,
    entity_map: dict[str, dict],
    fwd:        dict[str, list[tuple[str, str, str]]],
    rev:        dict[str, list[tuple[str, str, str]]],
    max_hops:   int,
    skip_ids:   frozenset[str] = frozenset(),
    slim:       bool = False,
) -> Optional[list[dict]]:
    """
    BFS from *from_id* to *to_id* using the given adjacency dicts.
    Returns the path as a list of entity stubs, or None if no path is found.
    """
    visited: set[str] = {from_id}
    # path step: (neighbor_id, rel_kind, edge_note, is_reverse)
    queue: deque[tuple[str, list[tuple[str, str, str, bool]]]] = deque()
    queue.append((from_id, []))

    while queue:
        current_id, path_so_far = queue.popleft()
        if len(path_so_far) >= max_hops:
            continue

        fwd_nb = [(nid, kind, note, False) for nid, kind, note in fwd.get(current_id, [])]
        rev_nb = [(nid, kind, note, True)  for nid, kind, note in rev.get(current_id, [])]
        for neighbor_id, rel_kind, edge_note, is_reverse in fwd_nb + rev_nb:
            if neighbor_id in visited:
                continue
            if neighbor_id != to_id and neighbor_id in skip_ids:
                continue
            visited.add(neighbor_id)
            new_path = path_so_far + [(neighbor_id, rel_kind, edge_note, is_reverse)]

            if neighbor_id == to_id:
                path_entities: list[dict] = []
                prev_id = from_id
                for step_id, edge_label, note, edge_rev in new_path:
                    node = _entity_stub(entity_map.get(prev_id, {}), slim=slim)
                    node["relation"] = edge_label
                    node["relation_reverse"] = edge_rev
                    if note:
                        node["note"] = note
                    path_entities.append(node)
                    prev_id = step_id
                path_entities.append(_entity_stub(to_entity, slim=slim))
                return path_entities

            queue.append((neighbor_id, new_path))

    return None


def shortest_path(
    from_entity: str,
    to_entity:   str,
    entity_map:  dict[str, dict],
    index:       Any,
    max_hops:    int = 6,
    slim:        bool = False,
) -> dict[str, Any]:
    """
    Find the shortest meaningful path between two entities.

    Two-phase search:
      Phase 1 — semantic edges only (calls, extends, implements, …).
      Phase 2 — all edges including structural ones (contains, imports, …).

    path_type field: "semantic" | "structural" | "none"
    """
    from_e = _resolve_entity(from_entity, entity_map, index)
    to_e   = _resolve_entity(to_entity,   entity_map, index)

    if not from_e:
        return {"found": False, "error": f"Entity not found: {from_entity!r}"}
    if not to_e:
        return {"found": False, "error": f"Entity not found: {to_entity!r}"}

    from_id = from_e["id"]
    to_id   = to_e["id"]

    if from_id == to_id:
        return {
            "found": True, "path": [_entity_stub(from_e, slim=slim)],
            "length": 0, "path_type": "semantic",
        }

    skip_ids = _compute_skip_ids(entity_map, from_id, to_id)

    # ---- Phase 1: semantic edges only -----------------------------------
    fwd_sem, rev_sem = _build_adjacency(entity_map, _SEMANTIC_EDGE_KINDS)
    path = _bfs_path(from_id, to_id, to_e, entity_map, fwd_sem, rev_sem,
                     max_hops, skip_ids, slim=slim)
    if path is None and skip_ids:
        path = _bfs_path(from_id, to_id, to_e, entity_map, fwd_sem, rev_sem,
                         max_hops, slim=slim)
    if path is not None:
        return {
            "found":     True,
            "path":      path,
            "length":    len(path) - 1,
            "path_type": "semantic",
        }

    # ---- Phase 2: full graph (semantic + structural) --------------------
    fwd_all, rev_all = _build_adjacency(entity_map, None)
    path = _bfs_path(from_id, to_id, to_e, entity_map, fwd_all, rev_all,
                     max_hops, skip_ids, slim=slim)
    if path is None and skip_ids:
        path = _bfs_path(from_id, to_id, to_e, entity_map, fwd_all, rev_all,
                         max_hops, slim=slim)
    if path is not None:
        return {
            "found":     True,
            "path":      path,
            "length":    len(path) - 1,
            "path_type": "structural",
        }

    return {
        "found":     False,
        "path":      [],
        "length":    0,
        "path_type": "none",
        "error":     f"No path found between {from_entity!r} and {to_entity!r} within {max_hops} hops",
    }


# ---------------------------------------------------------------------------
# 4. Agent Contribution — helper (write-back)
# ---------------------------------------------------------------------------

def apply_contribution(
    entity:      dict,
    properties:  dict[str, str],
    relations:   list[dict],
    rationale:   str,
    source:      str,
    writer:      Any,
    index:       Any,
) -> dict[str, Any]:
    """
    Apply a structured agent contribution to an existing entity.

    - Merges new property key-values.
    - Adds new relations (resolves target_name → ID, creating stubs if needed).
    - Appends a timeline event with the rationale.

    Returns a summary of what changed.
    """
    entity_id  = entity["id"]
    mutations:  dict[str, Any] = {}
    added_rels: list[str] = []
    now_iso    = datetime.now(timezone.utc).isoformat(timespec="seconds")[:10]

    if properties:
        mutations.setdefault("sections", {})["properties"] = properties

    if relations:
        existing_rels = entity.get("sections", {}).get("relations", [])
        existing_pairs = {(r["kind"], r["target_id"]) for r in existing_rels}
        new_rels: list[dict] = []
        for rel_spec in relations:
            kind        = rel_spec.get("kind", "related_to")
            target_name = rel_spec.get("target_name", "")
            note        = rel_spec.get("note", "")
            if not target_name:
                continue
            target_id = index.get(target_name)
            if not target_id:
                stub, _ = writer.create(
                    name=target_name, entity_type="other",
                    source="stub", status="stub",
                )
                target_id = stub["id"]
            if (kind, target_id) not in existing_pairs:
                entry: dict[str, Any] = {"kind": kind, "target_id": target_id}
                if note:
                    entry["note"] = note
                new_rels.append(entry)
                added_rels.append(f"{kind} → {target_name}")
        if new_rels:
            mutations.setdefault("sections", {})["relations"] = new_rels

    if rationale:
        timeline_event = {
            "date":  now_iso,
            "event": f"[{source}] {rationale[:300]}",
        }
        mutations.setdefault("sections", {})["timeline"] = [timeline_event]

    changes_made = bool(mutations)
    if changes_made:
        writer.update(entity_id, mutations)

    return {
        "entity_id":      entity_id,
        "entity_name":    entity.get("name"),
        "properties_set": list(properties.keys()),
        "relations_added": added_rels,
        "rationale_stored": bool(rationale),
        "changes_made":   changes_made,
    }


# ---------------------------------------------------------------------------
# 5. Symbol Lookup
# ---------------------------------------------------------------------------

def find_query(
    name:        str,
    entity_map:  dict[str, dict],
    index:       Any,
    max_results: int = 10,
) -> dict[str, Any]:
    """
    Look up a symbol by exact or partial name.

    Match priority (lowest number wins):
      0 — case-insensitive exact match on entity name
      1 — entity name ends with .<name> or _<name>  (method/suffix match)
      2 — entity name contains <name>  (substring)

    Returns up to max_results matches, each with full location context,
    callers (inbound dependency relations), and callees (outbound relations).
    """
    name_lower = name.lower()
    scored: list[tuple[int, str]] = []

    for eid, entity in entity_map.items():
        if entity.get("status") == "deleted":
            continue
        ename = entity.get("name", "").lower()
        if ename == name_lower:
            scored.append((0, eid))
        elif ename.endswith(f".{name_lower}") or ename.endswith(f"_{name_lower}"):
            scored.append((1, eid))
        elif name_lower in ename:
            scored.append((2, eid))

    if not scored:
        return {"query": name, "matches": [], "total": 0, "not_found": True}

    scored.sort(key=lambda x: x[0])
    seen:    set[str]  = set()
    ordered: list[str] = []
    for _, eid in scored:
        if eid not in seen:
            seen.add(eid)
            ordered.append(eid)
    ordered = ordered[:max_results]

    rev_adj  = build_reverse_impact_adj(entity_map)
    _OUTBOUND = frozenset({"calls", "imports", "depends_on", "uses",
                           "extends", "implements"})

    _STD_PROPS = frozenset({
        "file_path", "line_start", "line_end", "signature",
        "architectural_pattern", "language", "size", "last_scanned", "hash",
    })

    matches: list[dict] = []
    for eid in ordered:
        entity    = entity_map[eid]
        props     = entity.get("sections", {}).get("properties", {})
        core      = entity.get("sections", {}).get("core", {})
        relations = entity.get("sections", {}).get("relations", [])

        callers: list[dict] = []
        for caller_id, _cname, rel_kind in rev_adj.get(eid, [])[:8]:
            caller = entity_map.get(caller_id)
            if caller:
                callers.append({
                    "name":      caller.get("name", ""),
                    "type":      caller.get("type", ""),
                    "via":       rel_kind,
                    "file_path": caller.get("sections", {})
                                       .get("properties", {})
                                       .get("file_path", ""),
                })

        callees: list[dict] = []
        for rel in relations[:8]:
            if rel.get("kind") in _OUTBOUND:
                target = entity_map.get(rel.get("target_id", ""))
                if target:
                    callees.append({
                        "name": target.get("name", ""),
                        "type": target.get("type", ""),
                        "via":  rel.get("kind", ""),
                    })

        custom   = {k: v for k, v in props.items() if k not in _STD_PROPS and v}
        timeline = entity.get("sections", {}).get("timeline", [])

        matches.append({
            "id":         eid,
            "name":       entity.get("name", ""),
            "type":       entity.get("type", ""),
            "kind":       entity.get("kind"),
            "status":     entity.get("status", "active"),
            "file_path":  props.get("file_path", ""),
            "line_start": props.get("line_start", ""),
            "line_end":   props.get("line_end", ""),
            "summary":    core.get("summary", "")[:200],
            "signature":  props.get("signature", ""),
            "tags":       core.get("tags", [])[:6],
            "callers":    callers,
            "callees":    callees,
            "custom_properties": custom,
            "timeline":   timeline[-3:],
        })

    return {
        "query":     name,
        "matches":   matches,
        "total":     len(matches),
        "not_found": False,
    }


# ---------------------------------------------------------------------------
# 6. Orphan / Dead-Code Detection
# ---------------------------------------------------------------------------

def orphan_query(
    entity_map:      dict[str, dict],
    types:           Optional[list[str]] = None,
    include_modules: bool = False,
    max_results:     int  = 100,
) -> dict[str, Any]:
    """
    Find entities with no inbound dependency-forming relations — potential dead code.

    An entity is an orphan if no other entity has a relation in
    IMPACT_INCOMING_KINDS pointing to it. Known false positives are filtered:
      - dunder methods  (__init__, __str__, …)
      - named entry points  (main, run, create_app, …)
      - test entities  (test_* files / tests/ directories)
      - entities living in framework entry-point files  (wsgi.py, manage.py, …)
      - module-level entities  (unless include_modules=True)
    """
    referenced_ids: set[str] = set()
    for entity in entity_map.values():
        for rel in entity.get("sections", {}).get("relations", []):
            if rel.get("kind") in IMPACT_INCOMING_KINDS:
                tid = rel.get("target_id", "")
                if tid:
                    referenced_ids.add(tid)

    allowed_types = set(types) if types else None
    orphans:       list[dict] = []
    skipped_count: int        = 0

    for eid, entity in entity_map.items():
        if entity.get("status") in ("deleted", "stub"):
            continue
        if eid in referenced_ids:
            continue

        etype = entity.get("type", "")
        if etype == "module" and not include_modules:
            continue
        if allowed_types and etype not in allowed_types:
            continue

        name      = entity.get("name", "")
        props     = entity.get("sections", {}).get("properties", {})
        file_path = props.get("file_path", "")

        fp_parts = set(file_path.replace("\\", "/").split("/"))
        is_false_positive = (
            name.lower() in _ORPHAN_ENTRY_NAMES
            or bool(_DUNDER_PAT.match(name))
            or _is_test_entity(entity)
            or any(file_path.endswith(skip) for skip in _ORPHAN_SKIP_FILES)
            or bool(fp_parts & _ORPHAN_VENDOR_DIRS)
        )
        if is_false_positive:
            skipped_count += 1
            continue

        orphans.append({
            "id":         eid,
            "name":       name,
            "type":       etype,
            "kind":       entity.get("kind"),
            "file_path":  file_path,
            "line_start": props.get("line_start", ""),
            "summary":    entity.get("sections", {})
                               .get("core", {})
                               .get("summary", "")[:120],
        })

    orphans.sort(key=lambda x: (x["type"], x["name"]))

    return {
        "orphans":          orphans[:max_results],
        "total":            len(orphans),
        "skipped_count":    skipped_count,
        "referenced_count": len(referenced_ids),
    }
