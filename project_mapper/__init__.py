"""
project_mapper
Aethvion Project Mapper — standalone codebase knowledge graph.

Scans a software project via static AST analysis and populates an AethvionDB
database with a rich knowledge graph of modules, classes, functions,
dependencies, and their relationships.

Quick start (HTTP API)
----------------------
  python server.py
  POST /api/project-mapper/scan   body: { project_root, db }
  GET  /api/project-mapper/stats?db=my_project
  POST /api/project-mapper/query/impact  body: { entity, db }

Quick start (MCP stdio)
-----------------------
  python -m project_mapper --db my_project --project-root /path/to/project
"""
