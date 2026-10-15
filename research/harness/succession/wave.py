"""Launch a wave of succession lineages without exceeding the gateway.

    python3 wave.py r31:sonnet-mag r29:haiku r30:argon:3

Each spec is `run:lineage[:stop_after]`. At most MAG_CONCURRENCY lineages
run at once, because the gateway's limits are per USER across every project
and key: twenty parallel requests and a hundred and twenty a minute. A
producer's tool-use loop runs at roughly ten to twenty requests a minute,
so concurrent lineages are one client against one bucket, not independent
experiments.

This file exists because the cap was a comment and the comment did not hold.
Eleven lineages were launched at once; the throttling that followed arrived
as stalls correlated across lineages, which read like a shared capability
wall at one layer and was a thundering herd. Two other things that went
wrong by hand are also fixed here by construction: the credential is handed
to EVERY child (a shell `source ... && A & B &` bound the source to the
first job only, and a lineage then died for want of a key), and a wave
never starts a lineage whose lock is held, so a mistaken relaunch cannot
race a live runner.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_succession import MAG_CONCURRENCY  # noqa: E402

RUNNER = [sys.executable, str(HERE / "run_succession.py")]


def _held(run: str, lineage: str):
    """Who holds this lineage's lock, if anyone does.

    Asks the kernel rather than trusting a recorded pid: a pid is not an
    identity, and a reused one reported a live holder for a lineage whose
    runners were all dead. The child's own lock is authoritative; this is
    only so a wave can say SKIP instead of starting a doomed runner.
    """
    lock = HERE / f"lineages-{run}" / lineage / "RUNNER.lock"
    if not lock.is_file():
        return None
    try:
        handle = open(lock, "a+", encoding="utf-8")
    except OSError:
        return None
    with handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.seek(0)
            return handle.read().strip() or "another process"
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return None


def _env():
    key = os.environ.get("AMSC_API_KEY") or os.environ.get("AMSC_TOKEN")
    if not key:
        raise SystemExit("wave: AMSC_API_KEY/AMSC_TOKEN is not set; a MAG "
                         "lineage cannot run without the gateway credential")
    return dict(os.environ, AMSC_API_KEY=key, NO_COLOR="1")


def main(specs: list[str]) -> int:
    env = _env()
    queue = []
    for spec in specs:
        parts = spec.split(":")
        if len(parts) not in (2, 3):
            raise SystemExit(f"wave: bad spec {spec!r}; want run:lineage[:stop]")
        run, lineage = parts[0], parts[1]
        stop = parts[2] if len(parts) == 3 else None
        pid = _held(run, lineage)
        if pid:
            print(f"wave: SKIP {run}:{lineage} — pid {pid} already holds its "
                  f"lock", flush=True)
            continue
        queue.append((run, lineage, stop))

    print(f"wave: {len(queue)} lineage(s), at most {MAG_CONCURRENCY} at once",
          flush=True)
    running, done = {}, []
    while queue or running:
        while queue and len(running) < MAG_CONCURRENCY:
            run, lineage, stop = queue.pop(0)
            cmd = RUNNER + ["--lineage", lineage]
            if stop:
                cmd += ["--stop-after", stop]
            log = HERE / f"scratch_{lineage}_{run}.log"
            handle = open(log, "a", encoding="utf-8")
            handle.write(f"\n=== wave start {time.strftime('%H:%M:%S')} ===\n")
            handle.flush()
            proc = subprocess.Popen(cmd, cwd=HERE, stdout=handle,
                                    stderr=subprocess.STDOUT,
                                    env=dict(env, SUCCESSION_RUN=run))
            running[proc.pid] = (proc, run, lineage, handle, time.time())
            print(f"wave: start {run}:{lineage}"
                  f"{' (stop after ' + stop + ')' if stop else ''} "
                  f"pid {proc.pid}", flush=True)
        for pid, (proc, run, lineage, handle, began) in list(running.items()):
            if proc.poll() is None:
                continue
            handle.close()
            mins = (time.time() - began) / 60
            tail = ""
            log = HERE / f"scratch_{lineage}_{run}.log"
            if log.is_file():
                lines = [ln for ln in log.read_text(errors="replace").splitlines()
                         if ln.strip()]
                tail = lines[-1] if lines else ""
            print(f"wave: done  {run}:{lineage} rc={proc.returncode} "
                  f"after {mins:.0f}m — {tail[:90]}", flush=True)
            done.append((run, lineage, proc.returncode))
            del running[pid]
        time.sleep(5)
    print(f"wave: finished {len(done)} lineage(s)", flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1:]))
