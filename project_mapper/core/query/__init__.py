"""
project_mapper.core.query
Graph query engine, one module per query primitive. Shared infrastructure in
_common. Public API re-exported here so callers import from .query unchanged.
"""

from ._common import _resolve_entity, build_entity_map
from .context import context_query
from .contribute import apply_contribution
from .find import find_by_method, find_query
from .impact import impact_query
from .orphans import orphan_query
from .path import shortest_path

__all__ = [
    "build_entity_map",
    "_resolve_entity",
    "context_query",
    "impact_query",
    "shortest_path",
    "find_query",
    "find_by_method",
    "orphan_query",
    "apply_contribution",
]
