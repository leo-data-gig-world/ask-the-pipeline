"""Read-only SQL tool with layered guardrails.

Defence in depth, so a confused or manipulated model still can't do harm:
  1. The database file holds only the published tables (a serving copy, not the warehouse).
  2. It is opened read-only, with external file/network access disabled and the
     configuration locked, so a query can't re-enable either.
  3. Exactly one SELECT statement is allowed; everything else is rejected before it runs.
  4. Results are capped in rows, and slow queries are interrupted.
"""
from __future__ import annotations

import datetime as dt
import decimal
import threading
from pathlib import Path

import duckdb

MAX_ROWS = 200
TIMEOUT_S = 10.0


def connect(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True,
                          config={"enable_external_access": False, "lock_configuration": True})


def _plain(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def run_sql(con: duckdb.DuckDBPyConnection, query: str, timeout_s: float = TIMEOUT_S) -> dict:
    """Run one read-only SELECT. Returns rows, or {"error": ...} the model can learn from."""
    q = (query or "").strip().rstrip(";").strip()
    try:
        statements = con.extract_statements(q)
    except duckdb.Error as e:
        return {"error": f"could not parse SQL: {e}"[:500]}
    if len(statements) != 1:
        return {"error": "exactly one statement is allowed"}
    if statements[0].type != duckdb.StatementType.SELECT:
        return {"error": f"only SELECT is allowed, got {statements[0].type.name}"}

    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        cur = con.execute(f"SELECT * FROM ({q}) AS agent_query LIMIT {MAX_ROWS + 1}")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    except duckdb.Error as e:
        msg = str(e)
        if "INTERRUPT" in msg.upper():
            msg = f"query took longer than {timeout_s:g}s and was stopped"
        return {"error": msg[:500]}
    finally:
        timer.cancel()
    return {"columns": cols,
            "rows": [[_plain(v) for v in r] for r in rows[:MAX_ROWS]],
            "row_count": min(len(rows), MAX_ROWS),
            "truncated": len(rows) > MAX_ROWS}
