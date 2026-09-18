"""Swarm-safe capture. Many agents and their subprocesses append to one trace
at once; each append is lock-serialized so a line never tears, and every event
carries capture provenance (a unique id, and the run/parent a coordinator
declares) so the swarm's causal tree is reconstructable from one shared file.

    pytest tests/test_trace_concurrency.py   (or: python3 tests/test_trace_concurrency.py)
"""
import concurrent.futures as cf
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reticuli import _util


def _hammer(args: tuple) -> int:
    path, tag, n = args
    # Lines far larger than any single-write atomic size, so an unlocked append
    # would tear and the JSON parse below would catch it.
    payload = tag * 6000
    for i in range(n):
        _util.trace_append(path, {"event": "bash", "cmd": payload, "i": i})
    return n


def test_concurrent_appends_do_not_tear() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, ".reticuli", "draft.jsonl")
        procs, per = 8, 40
        work = [(path, chr(65 + k), per) for k in range(procs)]
        with cf.ProcessPoolExecutor(max_workers=procs) as ex:
            landed = sum(ex.map(_hammer, work))
        assert landed == procs * per
        with open(path, encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        assert len(lines) == procs * per, \
            f"every concurrent append landed as one whole line: {len(lines)}"
        for ln in lines:
            json.loads(ln)               # a torn line would raise here


def test_stamp_threads_the_causal_tree() -> None:
    ev = _util.stamp({"event": "bash", "cmd": "x"})
    assert len(ev["id"]) == 16 and "ts" in ev, "every event gets an id and a ts"
    assert "run" not in ev and "parent" not in ev, \
        "no run/parent unless a coordinator declared one"
    saved = {k: os.environ.get(k) for k in ("RETICULI_RUN", "RETICULI_PARENT")}
    try:
        os.environ["RETICULI_RUN"] = "agent-7"
        os.environ["RETICULI_PARENT"] = "swarm-root"
        threaded = _util.stamp({"event": "write", "path": "a.py"})
        assert threaded["run"] == "agent-7" and threaded["parent"] == "swarm-root", \
            "a swarm coordinator's run and parent ride every event"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_event_ids_do_not_collide() -> None:
    ids = {_util.stamp({"event": "bash", "cmd": "x"})["id"] for _ in range(2000)}
    assert len(ids) == 2000, "event ids are unique"


if __name__ == "__main__":
    test_concurrent_appends_do_not_tear()
    test_stamp_threads_the_causal_tree()
    test_event_ids_do_not_collide()
    print("trace-concurrency-ok")
