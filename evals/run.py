"""Run the eval suite.

    python evals/run.py              # replay recorded LLM replies (CI default: free, no key)
    python evals/run.py --record     # call the real model and save its replies as cassettes
    python evals/run.py --live       # call the real model, save nothing

Replay still executes every tool call for real against the fixture database, and
checks that the SQL and its results match what was recorded. A change to the data,
the guardrails or the tools is caught even though the model's replies are frozen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import config  # noqa: E402
from agent.catalog import Catalog  # noqa: E402
from agent.llm import LiveLLM, RecordingLLM, ReplayLLM  # noqa: E402
from agent.loop import answer  # noqa: E402
from agent.sql import connect, run_sql  # noqa: E402
from evals import fixture  # noqa: E402

HERE = Path(__file__).parent
CASSETTES = HERE / "cassettes"


def _matches(needle: str, text: str) -> bool:
    if needle.startswith("^"):                       # anchored regex: whole answer
        return re.fullmatch(needle[1:].rstrip("$"), text.strip(), re.I) is not None
    return needle.lower() in text.lower()


def check(case: dict, res) -> list[str]:
    text, fails = res.answer, []
    fails += [f"missing {s!r}" for s in case.get("all", []) if not _matches(str(s), text)]
    if case.get("any") and not any(_matches(str(s), text) for s in case["any"]):
        fails.append(f"none of {case['any']}")
    fails += [f"contains {s!r}" for s in case.get("none", []) if _matches(str(s), text)]
    if case.get("sql") is True and not res.sql_run:
        fails.append("no SQL ran")
    if case.get("sql") is False and res.sql_run:
        fails.append(f"SQL ran: {res.sql_run}")
    if res.stopped:
        fails.append(res.stopped)
    return fails


def digest(con, queries: list[str]) -> str:
    rows = [run_sql(con, q).get("rows") for q in queries]
    return hashlib.sha1(json.dumps(rows, default=str).encode()).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--live", action="store_true")
    a = ap.parse_args()
    config.load_dotenv()

    db = fixture.build(HERE / "fixture.duckdb")
    con, catalog = connect(db), Catalog()
    cases = yaml.safe_load((HERE / "cases.yaml").read_text(encoding="utf-8"))
    model_args = dict(model=config.get("LLM_MODEL", config.DEFAULT_MODEL),
                      base_url=config.get("LLM_BASE_URL", config.DEFAULT_BASE_URL),
                      api_key=config.get("LLM_API_KEY"))
    rows, failed = [], 0
    for case in cases:
        cassette = CASSETTES / f"{case['id']}.json"
        if a.record:
            llm = RecordingLLM(path=cassette, **model_args)
        elif a.live:
            llm = LiveLLM(**model_args)
        elif cassette.exists():
            llm = ReplayLLM(cassette)
        else:
            rows.append((case["id"], "FAIL", "-", "-", "-", "no cassette recorded"))
            failed += 1
            continue
        try:
            res = answer(case["question"], llm, con, catalog)
            fails = check(case, res)
        except Exception as e:  # a crash is a failed case, not a crashed suite
            res, fails = None, [f"error: {e}"]
        if res is not None:
            d = digest(con, res.sql_run)
            if a.record:
                data = json.loads(cassette.read_text(encoding="utf-8"))
                data.update(sql_run=res.sql_run, results_digest=d, answer=res.answer)
                cassette.write_text(json.dumps(data, indent=2), encoding="utf-8")
            elif not a.live:
                rec = json.loads(cassette.read_text(encoding="utf-8"))
                if rec.get("sql_run") != res.sql_run or rec.get("results_digest") != d:
                    fails.append("SQL or its results differ from the recording")
        failed += bool(fails)
        rows.append((case["id"], "PASS" if not fails else "FAIL",
                     len(res.trace) if res else "-",
                     (res.prompt_tokens + res.completion_tokens) if res else "-",
                     res.ms if res else "-", "; ".join(fails)))

    model = model_args["model"]
    lines = [f"# Eval report\n\nModel: `{model}` · mode: "
             f"{'record' if a.record else 'live' if a.live else 'replay'} · "
             f"**{len(cases) - failed}/{len(cases)} passed**\n",
             "| Case | Result | Tool calls | Tokens | ms | Notes |", "|---|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |" for r in rows]
    (HERE / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
