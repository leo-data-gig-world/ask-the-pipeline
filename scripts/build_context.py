"""Export the dbt docs (manifest + catalog) into context/catalog.json.

This is the agent's context layer: model grains, column meanings and types, written
once in dbt and reused here, so the agent and the docs site can never disagree.

    python scripts/build_context.py <path-to-pipeline>/dbt/target
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

MODELS = ["fct_daily_prices", "price_spikes", "stg_prices"]   # what the agent may see
OUT = Path(__file__).resolve().parents[1] / "context" / "catalog.json"


def build(target: Path) -> dict:
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((target / "catalog.json").read_text(encoding="utf-8"))
    nodes = {n["name"]: (uid, n) for uid, n in manifest["nodes"].items() if n["resource_type"] == "model"}
    # Columns passed through from upstream keep their upstream description
    # (documented once, inherited along the lineage).
    inherited: dict[str, str] = {}
    for name in ["stg_prices", "fct_daily_prices"]:
        for c, v in nodes[name][1]["columns"].items():
            if v.get("description"):
                inherited[c.lower()] = " ".join(v["description"].split())
    models = []
    for name in MODELS:
        uid, node = nodes[name]
        cat_cols = catalog["nodes"].get(uid, {}).get("columns", {})
        docs = {c.lower(): v.get("description", "") for c, v in node["columns"].items()}
        cols = [{"name": c["name"], "type": c["type"], "description": " ".join(docs.get(c["name"].lower(), "").split())
                 or inherited.get(c["name"].lower(), "")}
                for c in sorted(cat_cols.values(), key=lambda c: c["index"])]
        models.append({"name": name, "description": " ".join(node["description"].split()), "columns": cols})
    return {"generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "source": "dbt manifest + catalog from leo-data-gig-world/pokemon-price-pipeline",
            "models": models}


if __name__ == "__main__":
    out = build(Path(sys.argv[1]))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({sum(len(m['columns']) for m in out['models'])} columns)")
