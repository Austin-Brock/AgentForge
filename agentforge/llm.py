"""The only provider-specific file: a thin OpenAI chat wrapper with a disk cache,
token accounting and a token budget. ScriptedLLM stands in for it in tests.
"""
import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "gpt-5.4-nano"


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Reply:
    content: str
    tool_calls: list = field(default_factory=list)
    message: dict = field(default_factory=dict)  # append this to the message list


def tool(name, description, **params):
    """Build a function-tool schema whose parameters are all required strings."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
                "required": list(params),
            },
        },
    }


class LLM:
    def __init__(self, model=None, cache_dir=".cache/llm", max_tokens_total=None):
        from openai import OpenAI

        self.model = model or os.environ.get("AGENTFORGE_MODEL") or DEFAULT_MODEL
        self.client = OpenAI(max_retries=6)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_tokens_total = max_tokens_total
        self.usage = {"input": 0, "output": 0, "calls": 0, "cached_calls": 0}
        self._lock = threading.Lock()

    def chat(self, messages, tools=None, force_tool=None, json_mode=False, salt=""):
        """One chat turn. `salt` separates otherwise identical calls (for example repeats)."""
        request = {"model": self.model, "messages": messages}
        if tools:
            request["tools"] = tools
        if force_tool:
            request["tool_choice"] = {"type": "function", "function": {"name": force_tool}}
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        key = hashlib.sha256(json.dumps([request, salt], sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            with self._lock:
                self.usage["cached_calls"] += 1
            return self._reply(json.loads(path.read_text())["message"])

        with self._lock:
            used = self.usage["input"] + self.usage["output"]
            if self.max_tokens_total and used >= self.max_tokens_total:
                raise BudgetExceeded(f"token budget of {self.max_tokens_total} reached")
        response = self.client.chat.completions.create(**request)
        message = response.choices[0].message.model_dump(exclude_none=True)
        message = {k: message[k] for k in ("role", "content", "tool_calls") if k in message}
        message.setdefault("content", None)
        with self._lock:
            self.usage["calls"] += 1
            self.usage["input"] += response.usage.prompt_tokens
            self.usage["output"] += response.usage.completion_tokens
        path.write_text(json.dumps({"message": message}))
        return self._reply(message)

    @staticmethod
    def _reply(message):
        calls = []
        for tc in message.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(tc["id"], tc["function"]["name"], args if isinstance(args, dict) else {}))
        return Reply(message.get("content") or "", calls, message)


class ScriptedLLM:
    """Test double: returns pre-written replies in order and records what it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.usage = {"input": 0, "output": 0, "calls": 0, "cached_calls": 0}
        self.model = "scripted"

    def chat(self, messages, tools=None, force_tool=None, json_mode=False, salt=""):
        self.requests.append({"messages": list(messages), "force_tool": force_tool})
        self.usage["calls"] += 1
        return self.replies.pop(0)

    @staticmethod
    def call(name, **args):
        """A reply that makes one tool call."""
        tc = {"id": f"call_{name}", "type": "function",
              "function": {"name": name, "arguments": json.dumps(args)}}
        return Reply("", [ToolCall(tc["id"], name, args)],
                     {"role": "assistant", "content": None, "tool_calls": [tc]})

    @staticmethod
    def text(content):
        return Reply(content, [], {"role": "assistant", "content": content})
