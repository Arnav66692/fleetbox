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

## P3 best-of-N on real repo tasks (written 2026-11-21, before any P3 attempt ran)
Question: do several sandboxed attempts plus a test check give real fixes on Arnav's own code that one attempt misses?

Tasks (5, all in Research-and-Papers/workspace-dynamics, built by pilot/p3_build_tasks.py and pilot/p3_seed_bugs.py):
- 1 real past fix: commit 74d68dd "Fix task generator review findings". Start from its parent, with the commit's new tests added. Check: tests/test_tasks.py.
- 4 planted bugs in src/wsdyn/evaluation.py at HEAD (auroc-midrank, cf7-gate, duplicate-claims, blind-metadata). Each one was confirmed to make tests/test_evaluation.py fail. Two other planted bugs were dropped because the tests did not catch them.
Each task was confirmed to fail its check at the start and (for the real fix) to pass at the fixed commit.

Model: ollama/qwen2.5-coder:7b. Max 20 steps per attempt.
- Baseline: 1 attempt per task at temperature 0.
- Best-of-5: 5 attempts per task at temperature 0.7.
- Test files are restored from the original before the check runs, so an attempt cannot pass by editing tests.

PASS if best-of-5 solves at least 3 of 5 tasks AND at least 1 solved task is one the baseline failed.
FAIL otherwise. On FAIL with the local model, fleetbox stays a portfolio piece unless a stronger model (Anthropic key) is tested.
