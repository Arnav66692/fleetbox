import json
import os
import urllib.request
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass(frozen=True)
class Reply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


MODEL_TIMEOUT = float(os.environ.get("FLEETBOX_MODEL_TIMEOUT", "300"))


def _post(url: str, body: dict, headers: dict, timeout: float = MODEL_TIMEOUT) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


class OllamaClient:
    """Messages are kept in a provider-neutral list; this class translates them."""

    def __init__(self, model: str = "qwen2.5:1.5b", host: str | None = None, temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.label = f"ollama/{model}"

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> Reply:
        wire = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "tool":
                wire.append({"role": "tool", "content": m["content"], "tool_name": m["name"]})
            elif m["role"] == "assistant":
                wire.append({
                    "role": "assistant", "content": m["text"],
                    "tool_calls": [{"function": {"name": c.name, "arguments": c.args}} for c in m["tool_calls"]],
                })
            else:
                wire.append({"role": "user", "content": m["content"]})
        data = _post(f"{self.host}/api/chat", {
            "model": self.model, "messages": wire, "stream": False,
            "tools": [{"type": "function", "function": t} for t in tools],
            "options": {"temperature": self.temperature, "num_ctx": 16384, "num_predict": 2048},
        }, {})
        msg = data.get("message", {})
        text = msg.get("content", "")
        calls = [
            ToolCall(f"call_{i}", c["function"]["name"], _as_dict(c["function"].get("arguments")))
            for i, c in enumerate(msg.get("tool_calls") or [])
        ]
        if not calls:
            calls = parse_text_tool_calls(text, {t["name"] for t in tools})
            if calls:
                text = ""
        return Reply(text, calls, data.get("prompt_eval_count", 0), data.get("eval_count", 0))


class AnthropicClient:
    def __init__(self, model: str = "claude-sonnet-5-5", temperature: float = 0.0):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.key = key
        self.model = model
        self.temperature = temperature
        self.label = f"anthropic/{model}"

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> Reply:
        wire: list[dict] = []
        for m in messages:
            if m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["id"], "content": m["content"]}
                if wire and wire[-1]["role"] == "user" and isinstance(wire[-1]["content"], list):
                    wire[-1]["content"].append(block)
                else:
                    wire.append({"role": "user", "content": [block]})
            elif m["role"] == "assistant":
                content = [{"type": "text", "text": m["text"]}] if m["text"] else []
                content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.args} for c in m["tool_calls"]]
                wire.append({"role": "assistant", "content": content})
            else:
                wire.append({"role": "user", "content": m["content"]})
        data = _post("https://api.anthropic.com/v1/messages", {
            "model": self.model, "max_tokens": 4096, "system": system, "messages": wire,
            "temperature": self.temperature,
            "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools],
        }, {"x-api-key": self.key, "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
        calls = [ToolCall(b["id"], b["name"], b["input"]) for b in data["content"] if b["type"] == "tool_use"]
        usage = data.get("usage", {})
        return Reply(text, calls, usage.get("input_tokens", 0), usage.get("output_tokens", 0))


def _as_dict(args) -> dict:
    if isinstance(args, dict):
        return args
    try:
        parsed = json.loads(args or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def parse_text_tool_calls(text: str, tool_names: set[str]) -> list[ToolCall]:
    """Some local models print {"name": ..., "arguments": ...} as text instead of using the tool-call field."""
    decoder = json.JSONDecoder()
    calls: list[ToolCall] = []
    i = 0
    while (i := text.find("{", i)) != -1:
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict) and obj.get("name") in tool_names:
            args = obj.get("arguments", obj.get("parameters", {}))
            calls.append(ToolCall(f"text_{len(calls)}", obj["name"], _as_dict(args)))
        i = end
    return calls


def make_client(spec: str, temperature: float = 0.0):
    provider, _, model = spec.partition("/")
    if provider == "ollama":
        return OllamaClient(model or "qwen2.5:1.5b", temperature=temperature)
    if provider == "anthropic":
        return AnthropicClient(model or "claude-sonnet-5-5", temperature=temperature)
    raise ValueError(f"unknown model spec {spec!r}, use ollama/<model> or anthropic/<model>")
