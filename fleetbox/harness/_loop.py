import time
from collections.abc import Callable
from dataclasses import dataclass

from ._tools import TOOLS, execute

SYSTEM = (
    "You are a coding agent working inside an isolated Linux sandbox at /workspace. "
    "Use the tools to write files and run commands until the task is done. "
    "Always run your code to check it works. When finished, reply with a short summary and no tool calls."
)

Event = dict
OnEvent = Callable[[Event], None]


@dataclass(frozen=True)
class AgentResult:
    status: str
    summary: str
    steps: int
    input_tokens: int
    output_tokens: int
    seconds: float


def run_agent(task: str, sandbox_id: str, client, on_event: OnEvent = lambda e: None,
              max_steps: int = 15) -> AgentResult:
    messages: list[dict] = [{"role": "user", "content": task}]
    tokens_in = tokens_out = 0
    start = time.perf_counter()
    for step in range(1, max_steps + 1):
        try:
            reply = client.complete(SYSTEM, messages, TOOLS)
        except Exception as err:
            on_event({"type": "error", "step": step, "message": str(err)})
            return AgentResult("error", str(err), step, tokens_in, tokens_out, time.perf_counter() - start)
        tokens_in += reply.input_tokens
        tokens_out += reply.output_tokens
        messages.append({"role": "assistant", "text": reply.text, "tool_calls": reply.tool_calls})
        if reply.text and reply.tool_calls:
            on_event({"type": "thought", "step": step, "text": reply.text})
        if not reply.tool_calls:
            on_event({"type": "done", "step": step, "text": reply.text})
            return AgentResult("done", reply.text, step, tokens_in, tokens_out, time.perf_counter() - start)
        for call in reply.tool_calls:
            on_event({"type": "tool_call", "step": step, "name": call.name, "args": call.args})
            output = execute(sandbox_id, call.name, call.args)
            on_event({"type": "tool_result", "step": step, "name": call.name, "output": output[:2000]})
            messages.append({"role": "tool", "id": call.id, "name": call.name, "content": output})
    on_event({"type": "error", "step": max_steps, "message": "step limit reached"})
    return AgentResult("step_limit", "step limit reached", max_steps, tokens_in, tokens_out,
                       time.perf_counter() - start)
