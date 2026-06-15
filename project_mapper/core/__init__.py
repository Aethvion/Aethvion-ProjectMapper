"""
project_mapper.core
Transport-agnostic engine: scanning, ingestion, querying, caching, cleanup,
delta detection, watching, and security analysis.

Used by both the MCP and HTTP interface layers; it never imports from them.
Shared infrastructure (config, db, analyzers) lives one level up.
"""
