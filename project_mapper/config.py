"""
project_mapper/config.py
Single source of truth for the data directory location.

Override the default with the PM_DATA_DIR environment variable:
    PM_DATA_DIR=/var/data/pm python server.py

Default location: ~/.aethvion_pm/data
"""
import os
from pathlib import Path

DATA_DIR: Path = Path(
    os.environ.get("PM_DATA_DIR", "")
    or Path.home() / ".aethvion_pm" / "data"
)
