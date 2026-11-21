import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fleetbox import harness, sandbox  # noqa: E402

TASKS = [
    ("Create hello.py that prints exactly: hello fleet", "python hello.py | grep -qx 'hello fleet'"),
    ("Create fib.py that prints the 10th Fibonacci number (fib(1)=1, fib(2)=1), so it prints 55.",
     "python fib.py | grep -qx 55"),
    ("Create a file named primes.txt containing the prime numbers below 20, one per line.",
     "test \"$(cat primes.txt | tr -d ' ' | grep -v '^$' | tr '\\n' ,)\" = '2,3,5,7,11,13,17,19,'"),
    ("Create mathutil.py with a function add(a, b) that returns a + b. Then create test_mathutil.py that asserts add(2, 3) == 5 and run it with python.",
     "python -c 'import mathutil; assert mathutil.add(2,3)==5' && test -f test_mathutil.py"),
    ("Create count.py that reads words.txt and prints how many words it has. Also create words.txt with the text: the quick brown fox. Running count.py should print 4.",
     "python count.py | grep -qx 4"),
]


def main(spec: str) -> None:
    client = harness.make_client(spec)
    rows = []
    for task, check in TASKS:
        sid = sandbox.create()
        try:
            result = harness.run_agent(task, sid, client, max_steps=10)
            passed = sandbox.run(sid, check).exit_code == 0
        finally:
            sandbox.destroy(sid)
        rows.append({"task": task[:50], "status": result.status, "steps": result.steps,
                     "seconds": round(result.seconds, 1), "passed": passed})
        print(json.dumps(rows[-1]), flush=True)
    passed = sum(r["passed"] for r in rows)
    summary = {"model": client.label, "passed": passed, "of": len(rows),
               "verdict": "PASS" if passed >= 3 else "FAIL", "rows": rows}
    out = Path(__file__).with_name(f"p2_result_{spec.replace('/', '_').replace(':', '-')}.json")
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ollama/qwen2.5:1.5b")
