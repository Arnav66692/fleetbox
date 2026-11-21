import argparse
import os
import shutil
import sys
import time

from . import brain

DEFAULT_MODEL = os.environ.get("FLEETBOX_MODEL", "ollama/qwen2.5-coder:7b")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleetbox", description="Run several sandboxed agents on one task")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="try a task N times on a copy of a git repo and keep what passes")
    run.add_argument("task")
    run.add_argument("--check", required=True, help="command that must exit 0, e.g. 'python -m pytest -q'")
    run.add_argument("--repo", default=".")
    run.add_argument("-n", type=int, default=5)
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--temperature", type=float, default=0.7)
    run.add_argument("--steps", type=int, default=20)
    run.add_argument("--parallel", type=int, default=5)
    run.add_argument("--protect", action="append", default=[],
                     help="file or folder restored before the check, so tests cannot be edited (repeatable)")
    run.add_argument("--no-branches", action="store_true", help="report only, create no git branches")
    return parser


def run_command(args: argparse.Namespace) -> int:
    source, head = brain.snapshot_head(args.repo)
    print(f"fleetbox: {args.n} attempts, model {args.model}, from commit {head[:8]}", flush=True)
    start = time.perf_counter()
    try:
        attempts = brain.run_attempts(str(source), args.task, args.check, args.model, n=args.n,
                                      temperature=args.temperature, protect=args.protect,
                                      max_steps=args.steps, parallel=args.parallel)
    finally:
        shutil.rmtree(source, ignore_errors=True)
    prefix = f"fleetbox/{time.strftime('%Y%m%d-%H%M%S')}"
    for a in attempts:
        line = f"  attempt {a.index}: {a.status:7} {a.steps:2} steps {a.seconds:6.1f}s  changed {len(a.changed) + len(a.deleted)} files"
        if a.passed and (a.changed or a.deleted) and not args.no_branches:
            line += f"  -> branch {brain.make_branch(args.repo, head, a, args.task, prefix)}"
        elif a.passed:
            line += "  (no changes, no branch)" if not (a.changed or a.deleted) else ""
        print(line, flush=True)
    passed = sum(a.passed for a in attempts)
    print(f"{passed}/{len(attempts)} passed in {time.perf_counter() - start:.0f}s. "
          f"Attempt files are in {attempts[0].result_dir.rsplit('/', 1)[0] if attempts[0].result_dir else 'data/attempts'}")
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return run_command(args)
    except (ValueError, RuntimeError) as err:
        print(f"fleetbox: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
