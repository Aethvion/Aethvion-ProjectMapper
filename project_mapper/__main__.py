"""
Allows the package to be run as:
    python -m project_mapper [args...]

Equivalent to:
    python -m project_mapper.mcp.server [args...]
"""
from .mcp.server import main

main()
