"""The context layer: dbt model and column docs, exported from the pipeline.

The agent reads these definitions instead of guessing from raw table names, so
two people asking the same question get the same, documented answer.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.config import ROOT

CATALOG = ROOT / "context" / "catalog.json"


class Catalog:
    def __init__(self, path: Path = CATALOG):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.models = {m["name"]: m for m in data["models"]}

    def list_models(self) -> list[dict]:
        return [{"name": m["name"], "description": m["description"]} for m in self.models.values()]

    def describe_model(self, name: str) -> dict:
        m = self.models.get(name)
        if not m:
            return {"error": f"unknown model {name!r}; choose from {sorted(self.models)}"}
        return m

    def models_in(self, sql: str) -> list[str]:
        low = sql.lower()
        return [n for n in self.models if n in low]
