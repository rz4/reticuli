"""Condition 4 of the closure bar: the reconstruction reconstructs.

*Research tooling — not normative, not pinned.*

docs/transitions.md (k = 3, keyholder-signed 2026-10-05) requires each
qualifying trial to show the RECURSIVE step: the reconstructed
implementation, operating through ITS OWN CLI, takes a claim's blind
room and produces another conforming claim that lands the same root. A
tree that passes every suite but cannot do this is a decoy, not a
member — the r4 tree is the witness (its kernel jailed producers, so
its rebuilds killed codex on arrival).

This runner performs that step against a lineage tree:

    export (blind, via the TRIAL tool) -> import (via the TRIAL tool)
    -> rebuild with a real producer (via the TRIAL tool) -> the child's
    root equals the parent claim's root, and the ORIGINAL tool's verify
    accepts the child (the parent judges the grandchild).

CLI flag spellings are an unpinned seam (measured 2026-10-05:
`--into` vs `-o`), so the rebuild step tries the known spellings and
records which one the tree speaks — era data, not a failure.

    python3 trial.py --lineage codex --run r5 \
        --claim <sealed claim dir>            # default: the run's core scaffold

Writes trial_<lineage>_<run>.json beside itself. Exit 0 only if the
recursive step completed and the roots agree.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SUC = REPO / "research" / "harness" / "succession"
VENV_PY = str(REPO / ".venv" / "bin" / "python")
MODELS = {"claude": "sonnet", "codex": "gpt-6-sol"}


def tool_env(pypath: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pypath)
    return env


def run_tool(pypath: Path, *argv, timeout=3900):
    return subprocess.run([VENV_PY, "-P", "-m", "reticuli", *argv],
                          check=False, capture_output=True, text=True,
                          env=tool_env(pypath), timeout=timeout, cwd=REPO)


def original_root(claim: str) -> str:
    sys.path.insert(0, str(REPO / "src"))
    from reticuli import kernel
    return kernel.read_manifest(claim)["root"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the recursive step, through the trial tool's CLI")
    ap.add_argument("--lineage", required=True, choices=sorted(MODELS))
    ap.add_argument("--run", default="", help="lineage run tag (e.g. r5)")
    ap.add_argument("--claim", default=None,
                    help="sealed claim to reconstruct (default: the run's core scaffold)")
    a = ap.parse_args(argv)

    tag = ("-" + a.run) if a.run else ""
    pypath = SUC / f"lineages{tag}" / a.lineage / "pypath"
    assert (pypath / "reticuli").exists(), f"no lineage tree at {pypath}"
    claim = a.claim or str(SUC / "scratch" /
                           f"{a.lineage}{('_' + a.run) if a.run else ''}_00_core_claim")
    assert os.path.isdir(claim), f"no sealed claim at {claim}"
    want = original_root(claim)

    report = {"lineage": a.lineage, "run": a.run, "claim": claim,
              "root": want, "steps": {}, "when":
              time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def step(name, proc, extra=None):
        row = {"rc": proc.returncode,
               "tail": (proc.stderr or proc.stdout or "").strip()[-400:]}
        if extra:
            row.update(extra)
        report["steps"][name] = row
        return proc.returncode == 0

    work = Path(tempfile.mkdtemp(prefix=f"closure-trial-{a.lineage}-"))
    tar = work / "claim.tar"
    room = work / "blindroom"
    child = work / "child"
    ok = False
    try:
        if not step("export_blind",
                    run_tool(pypath, "export", claim, str(tar), "--blind")):
            raise SystemExit
        if not step("import_room",
                    run_tool(pypath, "import", str(tar), str(room))):
            raise SystemExit
        producer = (f"env PYTHONPATH={REPO / 'src'} "
                    f"RETICULI_MODEL={MODELS[a.lineage]} "
                    f"RETICULI_VENDOR={a.lineage} {VENV_PY} -P "
                    f"-m reticuli.producers.{a.lineage}")
        # the rebuild verb is pinned; its flag spellings are not (an open
        # register item). Speak the spellings until one lands; record which.
        spellings = [("--producer", producer, "--into", str(child)),
                     ("--producer", producer, "-o", str(child)),
                     ("--producer", producer, "--output", str(child))]
        rebuilt = None
        for sp in spellings:
            proc = run_tool(pypath, "rebuild", str(room), *sp)
            if proc.returncode == 0:
                rebuilt = proc
                step("rebuild", proc, {"spelling": " ".join(sp[::2])})
                break
            if "unrecognized" not in (proc.stderr or "") \
                    and "required" not in (proc.stderr or ""):
                step("rebuild", proc, {"spelling": " ".join(sp[::2])})
                raise SystemExit
        if rebuilt is None:
            step("rebuild", proc, {"spelling": "none accepted"})
            raise SystemExit
        got = original_root(str(child))
        report["child_root"] = got
        if got != want:
            report["steps"]["root_equality"] = {"rc": 1,
                                                "tail": f"{got} != {want}"}
            raise SystemExit
        report["steps"]["root_equality"] = {"rc": 0, "tail": "roots agree"}
        verify = subprocess.run(
            [VENV_PY, "-P", "-m", "reticuli", "verify", str(child)],
            check=False, capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=str(REPO / "src")), timeout=600)
        if not step("parent_verifies_child", verify):
            raise SystemExit
        ok = True
    except SystemExit:
        pass
    report["ok"] = ok
    out = HERE / f"trial_{a.lineage}{('_' + a.run) if a.run else ''}.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"recursive step {'OK' if ok else 'FAILED'} -> {out.relative_to(REPO)}")
    for name, row in report["steps"].items():
        print(f"  {name}: rc={row['rc']}"
              + (f" [{row.get('spelling')}]" if row.get("spelling") else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
