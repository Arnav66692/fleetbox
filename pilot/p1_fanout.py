import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fleetbox import sandbox  # noqa: E402

N = 20


def one(i: int) -> dict:
    t0 = time.perf_counter()
    sid = sandbox.create()
    t1 = time.perf_counter()
    res = sandbox.run(sid, f"python -c 'print({i}*{i})'")
    t2 = time.perf_counter()
    sandbox.destroy(sid)
    return {"ok": res.exit_code == 0 and res.output.strip() == str(i * i),
            "create_s": t1 - t0, "exec_s": t2 - t1}


def main() -> None:
    start = time.perf_counter()
    with ThreadPoolExecutor(N) as pool:
        rows = list(pool.map(one, range(N)))
    total = time.perf_counter() - start
    ok = sum(r["ok"] for r in rows)
    med_exec = statistics.median(r["exec_s"] for r in rows)
    med_create = statistics.median(r["create_s"] for r in rows)
    verdict = ok == N and med_exec < 1.0 and total < 30
    result = {"n": N, "ok": ok, "median_exec_s": round(med_exec, 3),
              "median_create_s": round(med_create, 3), "total_s": round(total, 2),
              "verdict": "PASS" if verdict else "FAIL"}
    Path(__file__).with_name("p1_result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
