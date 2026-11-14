"""Build the agent's serving database from the live pipeline.

1. Clone (or update) the pipeline repo into .cache/
2. Run its dbt build and docs (needs dbt-duckdb: pip install -r requirements-warehouse.txt)
3. Refresh context/catalog.json from the dbt docs
4. Copy the published models into .cache/agent.duckdb as plain tables

The agent never touches the warehouse itself. It opens this serving copy read-only,
with external file access off, so it can only see the three published tables.

    python scripts/build_warehouse.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_context import MODELS, OUT, build  # noqa: E402

CACHE = ROOT / ".cache"
REPO = "https://github.com/leo-data-gig-world/pokemon-price-pipeline.git"


def run(cmd, **kw):
    print("$", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True, **kw)


def main() -> None:
    CACHE.mkdir(exist_ok=True)
    pipe = CACHE / "pokemon-price-pipeline"
    if (pipe / ".git").exists():
        run(["git", "-C", str(pipe), "pull", "-q", "--ff-only"])
    else:
        run(["git", "clone", "-q", "--depth", "1", REPO, str(pipe)])

    warehouse = CACHE / "dbt.duckdb"
    env = {**os.environ, "DUCKDB_PATH": warehouse.as_posix(), "LAKE_DIR": (pipe / "lake").as_posix()}
    dbt = os.environ.get("DBT_BIN", "dbt")
    for args in (["build"], ["docs", "generate"]):
        run([dbt, *args, "--project-dir", "dbt", "--profiles-dir", "dbt"], cwd=pipe, env=env)

    import json
    OUT.write_text(json.dumps(build(pipe / "dbt" / "target"), indent=2), encoding="utf-8")

    tmp = CACHE / "agent.duckdb.tmp"
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(f"attach '{warehouse.as_posix()}' as w (read_only)")
    for m in MODELS:
        con.execute(f"create table {m} as select * from w.main.{m}")
    latest = con.execute("select max(price_date), count(*) from fct_daily_prices").fetchone()
    con.close()
    os.replace(tmp, CACHE / "agent.duckdb")       # swap in atomically
    print(f"agent.duckdb ready: data up to {latest[0]}, {latest[1]} fact rows")


if __name__ == "__main__":
    main()
