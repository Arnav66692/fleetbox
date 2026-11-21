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

## P3b same pilot, model gpt-oss:20b (written 2026-11-21, after P3 failed, before any P3b attempt ran)
Same 5 tasks, same checks, same protected tests, same harness as commit 35bd478, same bar:
PASS if best-of-5 solves at least 3 of 5 AND at least 1 solved task failed at baseline. FAIL otherwise.
Only the model changes (ollama/gpt-oss:20b). Harness changes allowed before the run only if the
throwaway-repo smoke test shows the model cannot use the tools at all. Any such change is listed here.
If P3b fails too, fleetbox is parked as a portfolio piece until after Nov 30.

### P3b outcome (recorded 2026-11-21)
FAIL by the bar: best-of-5 solved 2 of 5 (auroc-midrank 4/5, duplicate-claims 4/5), baseline 1 of 5.
duplicate-claims failed at baseline and was solved by best-of-5, so the rescue half of the bar was met.
Confound: 18 of 30 attempts ended at step 1 on the 300 s model-call timeout, with no model reply.
Ollama was serving other models for another program during the run (qwen3-vl:8b, gpt-oss-64k).
The 3 unsolved tasks had 17 of their 18 attempts cut off this way, so they were not a fair test of the model.
Any rerun is a new preregistered pilot (P3c), not a rescue of P3b.
