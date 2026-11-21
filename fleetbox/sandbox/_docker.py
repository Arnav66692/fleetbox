import base64
import subprocess
import uuid
from dataclasses import dataclass

IMAGE = "python:3.12-slim"
WORKDIR = "/workspace"
LABEL = "fleetbox=1"
MAX_OUTPUT = 8000


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    output: str


def _docker(*args: str, stdin: bytes | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], input=stdin, capture_output=True, timeout=timeout
    )


def create(memory: str = "512m", cpus: str = "1", network: bool = False) -> str:
    name = f"fleetbox-{uuid.uuid4().hex[:10]}"
    args = [
        "run", "-d", "--rm", "--name", name, "--label", LABEL,
        "--memory", memory, "--cpus", cpus, "--pids-limit", "256",
        "--workdir", WORKDIR,
    ]
    if not network:
        args += ["--network", "none"]
    proc = _docker(*args, IMAGE, "sleep", "infinity")
    if proc.returncode != 0:
        raise RuntimeError(f"sandbox create failed: {proc.stderr.decode().strip()}")
    return name


def run(sandbox_id: str, command: str, timeout: float = 30) -> ExecResult:
    try:
        proc = _docker(
            "exec", sandbox_id, "timeout", str(int(timeout)), "sh", "-c", command,
            timeout=timeout + 5,
        )
    except subprocess.TimeoutExpired:
        return ExecResult(124, f"command timed out after {timeout}s")
    out = (proc.stdout + proc.stderr).decode(errors="replace")
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n...[truncated {len(out) - MAX_OUTPUT} chars]"
    return ExecResult(proc.returncode, out)


def write_file(sandbox_id: str, path: str, content: str) -> ExecResult:
    encoded = base64.b64encode(content.encode()).decode()
    script = (
        "import base64,os,sys;p=sys.argv[1];"
        "os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True);"
        "open(p,'wb').write(base64.b64decode(sys.stdin.read()))"
    )
    proc = _docker("exec", "-i", sandbox_id, "python", "-c", script, path, stdin=encoded.encode())
    return ExecResult(proc.returncode, proc.stderr.decode(errors="replace") or f"wrote {path}")


def read_file(sandbox_id: str, path: str) -> ExecResult:
    proc = _docker("exec", sandbox_id, "cat", path)
    if proc.returncode != 0:
        return ExecResult(proc.returncode, proc.stderr.decode(errors="replace"))
    return ExecResult(0, proc.stdout.decode(errors="replace")[:MAX_OUTPUT])


def snapshot(sandbox_id: str, max_bytes: int = 200_000) -> dict[str, str]:
    listing = run(sandbox_id, f"find {WORKDIR} -type f -size -64k -not -path '*/__pycache__/*' "
                              "-not -name '*.pyc' | head -200")
    files: dict[str, str] = {}
    total = 0
    for path in filter(None, listing.output.splitlines()):
        content = read_file(sandbox_id, path)
        if content.exit_code != 0:
            continue
        total += len(content.output)
        if total > max_bytes:
            break
        files[path.removeprefix(WORKDIR + "/")] = content.output
    return files


def destroy(sandbox_id: str) -> None:
    _docker("rm", "-f", sandbox_id)


def destroy_all() -> int:
    ids = _docker("ps", "-aq", "--filter", f"label={LABEL}").stdout.decode().split()
    if ids:
        _docker("rm", "-f", *ids)
    return len(ids)
