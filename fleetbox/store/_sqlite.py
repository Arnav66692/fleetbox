import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "fleetbox.db"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
create table if not exists runs (
  id text primary key, fleet_id text, task text, model text, status text,
  summary text, steps int, input_tokens int, output_tokens int,
  seconds real, created_at real
);
create table if not exists events (
  run_id text, seq int, at real, body text, primary key (run_id, seq)
);
create table if not exists files (
  run_id text, path text, content text, primary key (run_id, path)
);
"""


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def create_run(run_id: str, fleet_id: str, task: str, model: str) -> None:
    with _lock:
        _db().execute(
            "insert into runs (id, fleet_id, task, model, status, steps, created_at) values (?,?,?,?,?,0,?)",
            (run_id, fleet_id, task, model, "queued", time.time()),
        )
        _db().commit()


def set_status(run_id: str, status: str) -> None:
    with _lock:
        _db().execute("update runs set status=? where id=?", (status, run_id))
        _db().commit()


def finish_run(run_id: str, status: str, summary: str, steps: int, input_tokens: int,
               output_tokens: int, seconds: float) -> None:
    with _lock:
        _db().execute(
            "update runs set status=?, summary=?, steps=?, input_tokens=?, output_tokens=?, seconds=? where id=?",
            (status, summary, steps, input_tokens, output_tokens, seconds, run_id),
        )
        _db().commit()


def add_event(run_id: str, event: dict) -> None:
    with _lock:
        seq = _db().execute("select coalesce(max(seq), 0) + 1 from events where run_id=?", (run_id,)).fetchone()[0]
        _db().execute("insert into events values (?,?,?,?)", (run_id, seq, time.time(), json.dumps(event)))
        if "step" in event:
            _db().execute("update runs set steps=max(steps, ?) where id=?", (event["step"], run_id))
        _db().commit()


def save_files(run_id: str, files: dict[str, str]) -> None:
    with _lock:
        _db().executemany("insert or replace into files values (?,?,?)",
                          [(run_id, p, c) for p, c in files.items()])
        _db().commit()


def get_run(run_id: str) -> dict | None:
    with _lock:
        row = _db().execute("select * from runs where id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(limit: int = 200) -> list[dict]:
    with _lock:
        rows = _db().execute("select * from runs order by created_at desc limit ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_events(run_id: str, after: int = 0) -> list[dict]:
    with _lock:
        rows = _db().execute("select seq, at, body from events where run_id=? and seq>? order by seq",
                             (run_id, after)).fetchall()
    return [{"seq": r["seq"], "at": r["at"], **json.loads(r["body"])} for r in rows]


def get_files(run_id: str) -> dict[str, str]:
    with _lock:
        rows = _db().execute("select path, content from files where run_id=? order by path", (run_id,)).fetchall()
    return {r["path"]: r["content"] for r in rows}
