"""Load pipeline configuration from config.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

# project root = two levels up from this file (src/phase2/config.py)
ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load(path: str | Path | None = None) -> dict:
    """Return the parsed config dict, cached for the process lifetime."""
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path) as fh:
        return yaml.safe_load(fh)


def db_path() -> Path:
    """Absolute path to the SQLite database."""
    return ROOT / load()["database"]["path"]
