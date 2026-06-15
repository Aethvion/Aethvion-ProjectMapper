"""
project_mapper.core.query
Graph query engine, one module per query primitive. Shared infrastructure in
_common. Public API re-exported here so callers import from .query unchanged.
"""
from ._common import build_entity_map
from ._common import _resolve_entity
from .context import context_query
from .impact import impact_query
from .path import shortest_path
from .find import find_query
from .find import find_by_method
from .orphans import orphan_query
from .contribute import apply_contribution

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
