"""
Allows the package to be run as:
    python -m project_mapper [args...]

Equivalent to:
    python -m project_mapper.mcp_server [args...]
"""
from .mcp_server import main

main()
