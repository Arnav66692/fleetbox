import os
import uuid
from concurrent.futures import ThreadPoolExecutor

from .. import harness, sandbox, store

MAX_CONCURRENT = int(os.environ.get("FLEETBOX_MAX_CONCURRENT", "8"))
MAX_FLEET = 100
_pool = ThreadPoolExecutor(MAX_CONCURRENT, thread_name_prefix="agent")


def _execute(run_id: str, task: str, model: str) -> None:
    store.set_status(run_id, "starting")
    sid = None
    try:
        client = harness.make_client(model)
        sid = sandbox.create()
        store.set_status(run_id, "running")
        result = harness.run_agent(task, sid, client, on_event=lambda e: store.add_event(run_id, e))
        store.save_files(run_id, sandbox.snapshot(sid))
        store.finish_run(run_id, result.status, result.summary, result.steps, result.input_tokens,
                         result.output_tokens, result.seconds)
    except Exception as err:
        store.add_event(run_id, {"type": "error", "message": str(err)})
        store.finish_run(run_id, "error", str(err), 0, 0, 0, 0.0)
    finally:
        if sid:
            sandbox.destroy(sid)


def launch(tasks: list[str], model: str) -> dict:
    tasks = [t.strip() for t in tasks if t and t.strip()]
    if not tasks:
        raise ValueError("at least one non-empty task is required")
    if len(tasks) > MAX_FLEET:
        raise ValueError(f"at most {MAX_FLEET} agents per fleet")
    harness.make_client(model)
    fleet_id = uuid.uuid4().hex[:8]
    run_ids = []
    for task in tasks:
        run_id = uuid.uuid4().hex[:12]
        store.create_run(run_id, fleet_id, task, model)
        _pool.submit(_execute, run_id, task, model)
        run_ids.append(run_id)
    return {"fleet_id": fleet_id, "run_ids": run_ids}
