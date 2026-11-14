"""Slack bot: mention @pricebot with a question and it answers in the thread.

Socket Mode: the bot opens an outbound websocket to Slack, so it needs no public
URL. Tokens come from the environment (a secret manager in production).
"""
from __future__ import annotations

import re

from agent import config
from agent.catalog import Catalog
from agent.cli import build_llm, log
from agent.loop import answer
from agent.sql import connect


def main() -> None:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    config.load_dotenv()
    app = App(token=config.get("SLACK_BOT_TOKEN"))
    catalog = Catalog()
    db_path = config.get("AGENT_DB", str(config.DEFAULT_DB))

    @app.event("app_mention")
    def on_mention(event, say, client):
        question = re.sub(r"<@[^>]+>", "", event.get("text", "")).strip()
        thread = event.get("thread_ts") or event["ts"]
        if not question:
            say(text="Ask me about card prices, e.g. _which cards spiked today?_", thread_ts=thread)
            return
        pending = say(text=":mag: Looking that up...", thread_ts=thread)
        res = answer(question, build_llm(), connect(db_path), catalog)
        log(res)
        footer = f"\n_{len(res.trace)} tool calls · {res.ms / 1000:.1f}s_"
        client.chat_update(channel=event["channel"], ts=pending["ts"], text=res.render() + footer)

    SocketModeHandler(app, config.get("SLACK_APP_TOKEN")).start()


if __name__ == "__main__":
    main()
