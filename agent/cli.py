"""Ask a question from the terminal:  python -m agent.cli "Which cards spiked today?" """
from __future__ import annotations

import argparse
import json
import time

from agent import config
from agent.catalog import Catalog
from agent.llm import LiveLLM
from agent.loop import answer
from agent.sql import connect


def build_llm() -> LiveLLM:
    return LiveLLM(model=config.get("LLM_MODEL", config.DEFAULT_MODEL),
                   base_url=config.get("LLM_BASE_URL", config.DEFAULT_BASE_URL),
                   api_key=config.get("LLM_API_KEY"))


def log(result) -> None:
    """One JSON line per question: tools, SQL, tokens, latency."""
    path = config.ROOT / "logs" / "agent.jsonl"
    path.parent.mkdir(exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "question": result.question, "ms": result.ms,
           "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
           "tools": result.trace, "sql": result.sql_run, "stopped": result.stopped}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def main() -> None:
    config.load_dotenv()
    ap = argparse.ArgumentParser(description="Ask the card price warehouse a question.")
    ap.add_argument("question")
    ap.add_argument("--db", default=config.get("AGENT_DB", str(config.DEFAULT_DB)))
    a = ap.parse_args()
    res = answer(a.question, build_llm(), connect(a.db), Catalog())
    log(res)
    print(res.render())
    print(f"\n[{len(res.trace)} tool calls · {res.prompt_tokens}+{res.completion_tokens} tokens · {res.ms} ms]")


if __name__ == "__main__":
    main()
