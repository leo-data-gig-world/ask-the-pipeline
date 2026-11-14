"""Guardrail and loop tests. No network, no API key."""
import json

import pytest

from agent.catalog import Catalog
from agent.loop import answer
from agent.sql import connect, run_sql
from evals import fixture


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    return connect(fixture.build(tmp_path_factory.mktemp("db") / "fixture.duckdb"))


# --- guardrails ---------------------------------------------------------------

def test_select_works_and_reports_rows(con):
    out = run_sql(con, "select card_name, market from fct_daily_prices where price_date = '2026-11-10';")
    assert out["row_count"] == 8 and not out["truncated"]


def test_rows_are_capped(con):
    out = run_sql(con, "select * from range(1000)")
    assert out["row_count"] == 200 and out["truncated"]


@pytest.mark.parametrize("bad", [
    "delete from price_spikes",
    "drop table fct_daily_prices",
    "create table x as select 1",
    "select 1; select 2",
    "set enable_external_access = true",
    "attach 'other.duckdb' as o",
])
def test_non_select_is_rejected(con, bad):
    assert "error" in run_sql(con, bad)


def test_external_files_are_blocked(con):
    out = run_sql(con, "select * from read_csv('C:/Windows/win.ini')")
    assert "error" in out


def test_slow_query_is_interrupted(con):
    out = run_sql(con, "select count(*) from range(1000000000) a, range(1000000000) b", timeout_s=0.5)
    assert "error" in out and "stopped" in out["error"]


def test_data_is_untouched_after_attempts(con):
    assert run_sql(con, "select count(*) from price_spikes")["rows"] == [[1]]


# --- agent loop with a scripted model -----------------------------------------

class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, tools):
        return self.replies.pop(0)


def call(name, args, i=0):
    return {"content": "", "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "tool_calls": [{"id": f"c{i}", "name": name, "arguments": json.dumps(args)}]}


def final(text):
    return {"content": text, "tool_calls": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def test_answer_shows_the_sql_that_really_ran(con):
    q = "select card_name, market from fct_daily_prices order by market desc limit 1"
    llm = ScriptedLLM([call("run_sql", {"query": "delete from price_spikes"}, 0),   # rejected
                       call("run_sql", {"query": q}, 1),
                       final("Umbreon ex at 1500 USD.")])
    res = answer("top card?", llm, con, Catalog())
    assert res.sql_run == [q]                       # only the query that actually ran
    assert res.models_used == ["fct_daily_prices"]
    assert res.data_as_of == "2026-11-10"
    assert "```sql" in res.render() and res.trace[0]["error"]


def test_tool_output_is_wrapped_as_untrusted_data(con):
    seen = {}

    class Spy(ScriptedLLM):
        def chat(self, messages, tools):
            if messages[-1]["role"] == "tool":
                seen["payload"] = json.loads(messages[-1]["content"])
            return super().chat(messages, tools)

    q = "select card_name from fct_daily_prices where card_name like 'Pikachu%' limit 1"
    answer("x", Spy([call("run_sql", {"query": q}), final("done")]), con, Catalog())
    assert "untrusted_data" in seen["payload"]


def test_step_limit_stops_runaway_loops(con):
    llm = ScriptedLLM([call("list_models", {}, i) for i in range(10)])
    res = answer("loop forever", llm, con, Catalog(), max_steps=3)
    assert res.stopped and len(res.trace) == 3


def test_unknown_tool_is_reported_not_crashed(con):
    res = answer("x", ScriptedLLM([call("rm_rf", {}), final("ok")]), con, Catalog())
    assert res.trace[0]["error"]
