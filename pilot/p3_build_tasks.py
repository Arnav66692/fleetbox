import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fleetbox import sandbox  # noqa: E402

DESKTOP = Path.home() / "Desktop"
TREES = ROOT / "data" / "pilot-trees"
CANDIDATES = [
    ("AI-Engineering/arc3-kestrel", "f006d47"),
    ("AI-Engineering/arc3-kestrel", "3669e50"),
    ("AI-Engineering/gemma4-dev-agent", "5fa7764"),
    ("AI-Engineering/gemma4-dev-agent", "2813807"),
    ("AI-Engineering/gemma4-dev-agent", "0469a96"),
    ("Research-and-Papers/workspace-dynamics", "74d68dd"),
    ("Research-and-Papers/workspace-dynamics", "534e8f9"),
]


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def extract(repo: Path, rev: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(git(repo, "archive", rev)), mode="r:") as tar:
        tar.extractall(dest, filter="data")


def check_tree(tree: Path, check: str) -> tuple[int, str]:
    sid = sandbox.create()
    try:
        sandbox.put_dir(sid, str(tree))
        res = sandbox.run(sid, check, timeout=240)
        return res.exit_code, res.output[-600:]
    finally:
        sandbox.destroy(sid)


def build(rel: str, fix: str) -> dict:
    repo = DESKTOP / rel
    tests = [p for p in git(repo, "show", "--name-only", "--format=", fix).decode().split() if is_test(p)]
    name = f"{repo.name}-{fix}"
    base, good = TREES / name / "base", TREES / name / "fixed"
    extract(repo, f"{fix}^", base)
    extract(repo, fix, good)
    for t in tests:
        (base / t).parent.mkdir(parents=True, exist_ok=True)
        (base / t).write_bytes(git(repo, "show", f"{fix}:{t}"))
    check = "python -m pytest -q -x -p no:cacheprovider " + " ".join(tests)
    base_code, base_out = check_tree(base, check)
    good_code, good_out = check_tree(good, check)
    usable = base_code != 0 and good_code == 0 and "ModuleNotFoundError" not in base_out
    return {"name": name, "repo": rel, "fix": fix, "subject": git(repo, "log", "-1", "--format=%s", fix).decode().strip(),
            "tests": tests, "check": check, "base_exit": base_code, "fixed_exit": good_code,
            "usable": usable, "base_tail": base_out[-300:], "fixed_tail": good_out[-300:]}


if __name__ == "__main__":
    rows = []
    for rel, fix in CANDIDATES:
        row = build(rel, fix)
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("name", "base_exit", "fixed_exit", "usable")}), flush=True)
    (Path(__file__).with_name("p3_tasks.json")).write_text(json.dumps(rows, indent=2))
