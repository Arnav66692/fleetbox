# Pilot preregistration (written 2026-11-21, before any pilot code ran)

Question: is a laptop-local agent harness (LLM tool loop plus one Docker sandbox per agent) worth building?

## P1 sandbox fan-out
Start 20 sandboxes at once, run one command in each, destroy them.
- PASS if 20 of 20 succeed, median single exec latency under 1.0 s, and the whole batch finishes in under 30 s.
- FAIL otherwise.

## P2 agent loop with a free local model
Model: qwen2.5:1.5b through Ollama (the only model on this machine with no key needed).
5 fixed tasks, each checked by a command run inside the sandbox after the agent stops.
- PASS if 3 or more of 5 tasks pass their check.
- FAIL means the loop may still be fine but this model is too weak, and the build needs a stronger model (Anthropic key or a bigger local model).

Decision rule: build the full version only if P1 passes. P2 decides which model is the default.
