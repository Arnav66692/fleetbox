import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from ._attempts import Attempt


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def snapshot_head(repo: str) -> tuple[Path, str]:
    """Attempts start from the last commit, so uncommitted work in the real checkout is never touched."""
    root = Path(_git(Path(repo), "rev-parse", "--show-toplevel").strip())
    head = _git(root, "rev-parse", "HEAD").strip()
    archive = subprocess.run(["git", "-C", str(root), "archive", head], capture_output=True, check=True).stdout
    dest = Path(tempfile.mkdtemp(prefix="fleetbox-src-"))
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(dest, filter="data")
    return dest, head


def make_branch(repo: str, head: str, attempt: Attempt, task: str, prefix: str) -> str:
    root = Path(_git(Path(repo), "rev-parse", "--show-toplevel").strip())
    branch = f"{prefix}-{attempt.index}"
    worktree = Path(tempfile.mkdtemp(prefix="fleetbox-wt-")) / "wt"
    _git(root, "worktree", "add", "-q", "-b", branch, str(worktree), head)
    try:
        result = Path(attempt.result_dir)
        for rel in attempt.changed:
            (worktree / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result / rel, worktree / rel)
        if attempt.changed:
            _git(worktree, "add", "--", *attempt.changed)
        if attempt.deleted:
            _git(worktree, "rm", "-q", "--", *attempt.deleted)
        message = f"fleetbox attempt {attempt.index}: {task[:60]}\n\nCheck passed. Run id {attempt.run_id}."
        _git(worktree, "commit", "-q", "--no-verify", "-m", message)
    finally:
        _git(root, "worktree", "remove", "--force", str(worktree))
    return branch
