import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fleetbox import brain  # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "ollama/qwen2.5-coder:7b"
PARALLEL = int(sys.argv[2]) if len(sys.argv) > 2 else 5
TAG = sys.argv[3] if len(sys.argv) > 3 else ""
OUT = Path(__file__).with_name(f"p3{TAG}_result_{MODEL.replace('/', '_').replace(':', '-')}.json")


def attempt_rows(attempts):
    return [{"index": a.index, "status": a.status, "passed": a.passed, "steps": a.steps,
             "seconds": round(a.seconds, 1), "agent_status": a.agent_status, "timed_out": a.agent_status == "error" and "timed out" in a.agent_summary, "changed": a.changed, "check_tail": a.check_output[-300:]}
            for a in attempts]


def main() -> None:
    tasks = json.loads(Path(__file__).with_name("p3_tasks_final.json").read_text())
    done = json.loads(OUT.read_text())["tasks"] if OUT.exists() else []
    finished = {t["name"] for t in done}
    for t in tasks:
        if t["name"] in finished:
            continue
        tree = str(ROOT / t["tree"])
        start = time.perf_counter()
        base = brain.run_attempts(tree, t["task"], t["check"], MODEL, n=1, temperature=0.0,
                                  protect=t["protect"], max_steps=20)
        best = brain.run_attempts(tree, t["task"], t["check"], MODEL, n=5, temperature=0.7,
                                  protect=t["protect"], max_steps=20, parallel=PARALLEL)
        row = {"name": t["name"], "kind": t["kind"], "baseline_passed": base[0].passed,
               "best_of_5_passed": sum(a.passed for a in best), "seconds": round(time.perf_counter() - start),
               "baseline": attempt_rows(base), "attempts": attempt_rows(best)}
        done.append(row)
        print(json.dumps({k: row[k] for k in ("name", "baseline_passed", "best_of_5_passed", "seconds")}), flush=True)
        OUT.write_text(json.dumps({"model": MODEL, "tasks": done}, indent=2))
    solved = [t for t in done if t["best_of_5_passed"] > 0]
    rescued = [t for t in solved if not t["baseline_passed"]]
    verdict = "PASS" if len(solved) >= 3 and rescued else "FAIL"
    summary = {"model": MODEL, "tasks": done, "solved_best_of_5": len(solved),
               "solved_baseline": sum(t["baseline_passed"] for t in done),
               "rescued_by_best_of_5": [t["name"] for t in rescued], "of": len(tasks), "verdict": verdict}
    OUT.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "tasks"}))


if __name__ == "__main__":
    main()
