"""The outside re-earn: condition 5 of the closure bar, as one command.

*Research tooling — not normative, not pinned. See outside.md for the
operator's protocol and what the result means.*

Re-earns a qualifying trial's verdicts on THIS machine, under THIS
operator:

  1. the repository verifies (the root is the published one);
  2. the substituted full gate — the repository's own claim audited
     with every generated module replaced by the trial tree's
     (`kernel.audit(repo, produce_from=...)`), the same judgment the
     trial's record reports;
  3. optionally (--recursive, needs a codex/claude CLI configured with
     the OPERATOR'S account): the recursive step through the trial
     tree's own command line, via trial.py.

Writes outside_reearn_<lineage>_<run>.json beside this file: host,
platform, quarantine backend, timings, verdicts. Exit 0 only if every
requested leg re-earned.

    python3 research/harness/closure/outside_reearn.py \
        --lineage codex --run r13 [--recursive]
"""
import argparse
import importlib.util
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the outside re-earn")
    ap.add_argument("--lineage", required=True, choices=["claude", "codex"])
    ap.add_argument("--run", required=True, help="lineage run tag (e.g. r13)")
    ap.add_argument("--recursive", action="store_true",
                    help="also re-earn the recursive step (needs YOUR "
                         "producer CLI configured)")
    a = ap.parse_args(argv)

    from reticuli import kernel
    from reticuli._kernel.run import sandbox_backend

    spec = importlib.util.spec_from_file_location(
        "selfclaim", REPO / "scripts" / "selfclaim.py")
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)

    tree = REPO / "research" / "harness" / "succession" / \
        f"lineages-{a.run}" / a.lineage / "tree"
    assert tree.is_dir(), f"no trial tree at {tree} — wrong --run/--lineage?"

    report = {"lineage": a.lineage, "run": a.run,
              "operator_note": "fill in or sign the record — this file "
                               "carries the measurements, the record "
                               "carries the oath",
              "host": {"platform": sys.platform,
                       "machine": platform.machine(),
                       "python": platform.python_version(),
                       "quarantine": sandbox_backend()},
              "legs": {}}

    # leg 1: the repository verifies
    t0 = time.time()
    v = kernel.verify(str(REPO))
    report["legs"]["verify_repo"] = {"ok": bool(v["ok"]), "root": v["root"],
                                     "seconds": round(time.time() - t0, 1)}
    print(f"verify: ok={v['ok']} root={v['root'][:16]}…")
    ok = bool(v["ok"])

    # leg 2: the substituted full gate — the trial's central verdict,
    # re-earned here
    mapping = {f"src/reticuli/{m}": str(tree / m)
               for _n, adds, _c, _v in sc.LAYERS for m in adds}
    print(f"substituted gate: {len(mapping)} modules from the "
          f"{a.lineage}-{a.run} tree; expect ~an hour…")
    t0 = time.time()
    r = kernel.audit(str(REPO), produce_from=mapping)
    gate = r["gates"][0] if r.get("gates") else {}
    report["legs"]["substituted_gate"] = {
        "ok": bool(r["ok"]), "status": gate.get("status"),
        "quarantine": gate.get("quarantine"),
        "seconds": round(time.time() - t0, 1)}
    print(f"substituted gate: ok={r['ok']} "
          f"({report['legs']['substituted_gate']['seconds']}s, "
          f"quarantine={gate.get('quarantine')})")
    ok = ok and bool(r["ok"])

    # leg 3 (optional): the recursive step, with the operator's producer
    if a.recursive:
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(HERE / "trial.py"),
             "--lineage", a.lineage, "--run", a.run],
            check=False, capture_output=True, text=True, cwd=REPO)
        report["legs"]["recursive_step"] = {
            "ok": proc.returncode == 0,
            "seconds": round(time.time() - t0, 1),
            "tail": (proc.stdout + proc.stderr)[-400:].strip()}
        print(f"recursive step: ok={proc.returncode == 0}")
        ok = ok and proc.returncode == 0

    out = HERE / f"outside_reearn_{a.lineage}_{a.run}.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"{'RE-EARNED' if ok else 'NOT RE-EARNED'} -> {out.relative_to(REPO)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
