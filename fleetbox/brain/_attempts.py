import filecmp
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .. import harness, sandbox, store

REPO_PREAMBLE = (
    "A project is already checked out at /workspace. Read the relevant files before you change them, "
    "prefer edit_file for small changes, and run the check command yourself before you finish.\n"
    "Check command: {check}\n\nTask: {task}"
)
OUT_ROOT = Path(__file__).resolve().parents[2] / "data" / "attempts"
IGNORED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


@dataclass(frozen=True)
class Attempt:
    index: int
    run_id: str
    status: str
    passed: bool
    check_output: str
    changed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    result_dir: str = ""
    steps: int = 0
    seconds: float = 0.0
    agent_status: str = ""
    agent_summary: str = ""


def _files(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix() for p in root.rglob("*")
        if p.is_file() and not IGNORED_PARTS.intersection(p.relative_to(root).parts) and p.suffix != ".pyc"
    }


def diff_trees(before: Path, after: Path) -> tuple[list[str], list[str]]:
    old, new = _files(before), _files(after)
    changed = sorted(p for p in new if p not in old or not filecmp.cmp(before / p, after / p, shallow=False))
    return changed, sorted(old - new)


def _restore(sid: str, source: Path, protect: list[str]) -> None:
    for rel in protect:
        target = source / rel
        paths = [target] if target.is_file() else sorted(p for p in target.rglob("*") if p.is_file())
        for path in paths:
            sandbox.write_file(sid, path.relative_to(source).as_posix(), path.read_text())


def _one(index: int, fleet_id: str, source: Path, task: str, check: str, model: str, temperature: float,
         protect: list[str], max_steps: int, out_root: Path) -> Attempt:
    run_id = uuid.uuid4().hex[:12]
    store.create_run(run_id, fleet_id, f"[attempt {index}] {task}", model)
    sid = None
    try:
        client = harness.make_client(model, temperature=temperature)
        sid = sandbox.create()
        sandbox.put_dir(sid, str(source))
        store.set_status(run_id, "running")
        prompt = REPO_PREAMBLE.format(check=check, task=task)
        result = harness.run_agent(prompt, sid, client, on_event=lambda e: store.add_event(run_id, e),
                                   max_steps=max_steps)
        _restore(sid, source, protect)
        verdict = sandbox.run(sid, check, timeout=300)
        passed = verdict.exit_code == 0
        store.add_event(run_id, {"type": "check", "passed": passed, "output": verdict.output[-2000:]})
        result_dir = out_root / f"attempt-{index}"
        result_dir.mkdir(parents=True)
        sandbox.get_dir(sid, str(result_dir))
        changed, deleted = diff_trees(source, result_dir)
        status = "passed" if passed else "failed"
        store.finish_run(run_id, status, result.summary, result.steps, result.input_tokens,
                         result.output_tokens, result.seconds)
        return Attempt(index, run_id, status, passed, verdict.output[-2000:], changed, deleted,
                       str(result_dir), result.steps, result.seconds,
                       result.status, result.summary[:500])
    except Exception as err:
        store.add_event(run_id, {"type": "error", "message": str(err)})
        store.finish_run(run_id, "error", str(err), 0, 0, 0, 0.0)
        return Attempt(index, run_id, "error", False, str(err))
    finally:
        if sid:
            sandbox.destroy(sid)


def run_attempts(source: str, task: str, check: str, model: str, n: int = 5, temperature: float = 0.7,
                 protect: list[str] | None = None, max_steps: int = 20, parallel: int = 5,
                 out_dir: str | None = None) -> list[Attempt]:
    """Run n independent agents on copies of `source`; each attempt is judged only by `check`."""
    src = Path(source).resolve()
    if not src.is_dir():
        raise ValueError(f"{source} is not a directory")
    if not task.strip() or not check.strip():
        raise ValueError("task and check are both required")
    if not 1 <= n <= 20:
        raise ValueError("n must be between 1 and 20")
    harness.make_client(model)
    fleet_id = uuid.uuid4().hex[:8]
    out_root = Path(out_dir) if out_dir else OUT_ROOT / fleet_id
    out_root.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(min(parallel, n)) as pool:
        futures = [pool.submit(_one, i, fleet_id, src, task, check, model, temperature, protect or [],
                               max_steps, out_root) for i in range(1, n + 1)]
        return [f.result() for f in futures]

