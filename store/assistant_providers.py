"""Replaceable AI provider layer for the GachGhar AI Gardener.

Each provider implements chat(system, messages, tools) -> ProviderReply and speaks one vendor's HTTP API.
Messages use one neutral format, converted per vendor:
    {"role": "user" | "assistant", "content": str, "tool_calls": [ToolCall dict, ...]}   (assistant turn)
    {"role": "tool", "tool_call_id": str, "name": str, "content": str}                    (tool result)
Credentials, model name and base URL come only from environment variables (see .env.example).
No third-party SDK is required; only the Python standard library is used.
"""
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger("store.assistant")


class ProviderError(Exception):
    """Raised for any provider failure. The message is safe to log but never shown to customers."""


@dataclass
class ProviderReply:
    text: str = ""
    tool_calls: list = field(default_factory=list)  # [{"id", "name", "arguments": dict}]


def _post_json(url, headers, payload, timeout):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https endpoints from env
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        # Log only the status code, never the key or the request body.
        raise ProviderError(f"provider returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        raise ProviderError(f"provider request failed: {type(error).__name__}") from error


class OpenAICompatibleProvider:
    """OpenAI Chat Completions with tool calling. Works with other OpenAI-compatible APIs via AI_BASE_URL."""
    name = "openai"

    def __init__(self):
        self.api_key = settings.AI_PROVIDER_API_KEY
        self.model = settings.AI_MODEL
        self.url = (settings.AI_BASE_URL or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

    def chat(self, system, messages, tools):
        wire = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "tool":
                wire.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                wire.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                    for c in m["tool_calls"]]})
            else:
                wire.append({"role": m["role"], "content": m["content"]})
        payload = {"model": self.model, "messages": wire, "max_tokens": settings.AI_MAX_OUTPUT_TOKENS,
                   "temperature": 0.3,
                   "tools": [{"type": "function", "function": t} for t in tools]}
        data = _post_json(self.url, {"Authorization": f"Bearer {self.api_key}"}, payload, settings.AI_TIMEOUT_SECONDS)
        try:
            message = data["choices"][0]["message"]
            calls = []
            for call in message.get("tool_calls") or []:
                try:
                    arguments = json.loads(call["function"].get("arguments") or "{}")
                except ValueError:
                    arguments = {}
                calls.append({"id": call["id"], "name": call["function"]["name"], "arguments": arguments})
            return ProviderReply(text=(message.get("content") or "").strip(), tool_calls=calls)
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("unexpected provider response shape") from error


class AnthropicProvider:
    """Anthropic Messages API with tool use."""
    name = "anthropic"

    def __init__(self):
        self.api_key = settings.AI_PROVIDER_API_KEY
        self.model = settings.AI_MODEL
        self.url = (settings.AI_BASE_URL or "https://api.anthropic.com").rstrip("/") + "/v1/messages"

    def chat(self, system, messages, tools):
        wire = []
        for m in messages:
            if m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if wire and wire[-1]["role"] == "user" and isinstance(wire[-1]["content"], list):
                    wire[-1]["content"].append(block)  # parallel tool results share one user turn
                else:
                    wire.append({"role": "user", "content": [block]})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]}
                           for c in m["tool_calls"]]
                wire.append({"role": "assistant", "content": blocks})
            else:
                wire.append({"role": m["role"], "content": m["content"]})
        payload = {"model": self.model, "system": system, "messages": wire,
                   "max_tokens": settings.AI_MAX_OUTPUT_TOKENS, "temperature": 0.3,
                   "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                             for t in tools]}
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        data = _post_json(self.url, headers, payload, settings.AI_TIMEOUT_SECONDS)
        try:
            text, calls = [], []
            for block in data["content"]:
                if block["type"] == "text":
                    text.append(block["text"])
                elif block["type"] == "tool_use":
                    calls.append({"id": block["id"], "name": block["name"], "arguments": block.get("input") or {}})
            return ProviderReply(text="\n".join(text).strip(), tool_calls=calls)
        except (KeyError, TypeError) as error:
            raise ProviderError("unexpected provider response shape") from error


PROVIDERS = {"openai": OpenAICompatibleProvider, "anthropic": AnthropicProvider}


def get_provider():
    """Return a configured provider instance, or None when AI is not configured (normal shopping still works)."""
    name = (settings.AI_PROVIDER or "").strip().lower()
    if not name or name not in PROVIDERS:
        return None
    if not settings.AI_PROVIDER_API_KEY or not settings.AI_MODEL:
        return None
    return PROVIDERS[name]()
