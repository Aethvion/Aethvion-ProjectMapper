"""project_mapper.core.query.context — context query."""
from __future__ import annotations

import logging
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

from ._common import (
    _resolve_entity,
    _entity_stub,
)


_DETAIL_LEVELS: dict[str, frozenset[str]] = {
    "high":   frozenset({"module", "service", "decision", "goal", "constraint", "workflow"}),
    "medium": frozenset({"module", "service", "class", "component", "decision",
                         "goal", "constraint", "workflow", "config", "dependency"}),
    "low":    frozenset({"module", "service", "class", "component", "function",
                         "endpoint", "model", "decision", "goal", "constraint",
                         "workflow", "config", "dependency"}),
}


_TOKENS_PER_ENTITY = 80


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


_STRUCTURAL_EDGE_KINDS: frozenset[str] = frozenset({
    "contains",
    "imports",
    "depends_on",
    "related_to",
})


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
