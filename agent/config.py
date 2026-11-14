"""Settings come from environment variables only.

Locally a git-ignored .env file fills them in. In production a secret manager
injects the same variables (see deploy/cloud-run.md). The code never cares which.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader: KEY=value lines; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


DEFAULT_DB = ROOT / ".cache" / "agent.duckdb"
DEFAULT_MODEL = "z-ai/glm-5.3-flash"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
