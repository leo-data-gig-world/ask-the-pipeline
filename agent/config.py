"""Settings come from environment variables first.

In production a secret manager injects them (see deploy/cloud-run.md). On a
developer machine, secrets can instead live in the OS credential store (Windows
Credential Manager, macOS Keychain) via `keyring`, so no key sits in a plain file:

    python -m keyring set ask-the-pipeline LLM_API_KEY

Non-secret settings (model, endpoint) can go in a git-ignored .env file.
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


SECRETS = {"LLM_API_KEY", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"}
KEYRING_SERVICE = "ask-the-pipeline"


def get(name: str, default: str = "") -> str:
    value = os.environ.get(name, "")
    if not value and name in SECRETS:
        try:                                    # optional: OS credential store
            import keyring
            value = keyring.get_password(KEYRING_SERVICE, name) or ""
        except Exception:                       # no keyring backend (e.g. CI): fall through
            value = ""
    return value or default


DEFAULT_DB = ROOT / ".cache" / "agent.duckdb"
DEFAULT_MODEL = "z-ai/glm-5.3-flash"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
