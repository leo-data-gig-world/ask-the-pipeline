"""LLM clients behind one tiny interface: chat(messages, tools) -> dict.

LiveLLM talks to any OpenAI-compatible endpoint (OpenRouter, Ollama, OpenAI, Z.AI).
RecordingLLM saves each reply; ReplayLLM plays them back, so CI runs the evals
deterministically with no API key and no cost.
"""
from __future__ import annotations

import json
from pathlib import Path


def _normalise(msg, usage) -> dict:
    calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"}
             for c in (msg.tool_calls or [])]
    return {"content": msg.content or "", "tool_calls": calls,
            "usage": {"prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                      "completion_tokens": getattr(usage, "completion_tokens", 0) or 0}}


class LiveLLM:
    def __init__(self, model: str, base_url: str, api_key: str):
        from openai import OpenAI
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key or "not-needed-for-ollama")

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        r = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools,
                                                temperature=0)
        return _normalise(r.choices[0].message, r.usage)


class RecordingLLM(LiveLLM):
    def __init__(self, *args, path: Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.path, self.replies = Path(path), []

    def chat(self, messages, tools):
        reply = super().chat(messages, tools)
        self.replies.append(reply)
        self.path.write_text(json.dumps({"model": self.model, "replies": self.replies}, indent=2),
                             encoding="utf-8")
        return reply


class ReplayLLM:
    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.model, self.replies = data["model"], list(data["replies"])

    def chat(self, messages, tools):
        if not self.replies:
            raise RuntimeError("cassette exhausted: the agent made more LLM calls than were recorded")
        return self.replies.pop(0)
