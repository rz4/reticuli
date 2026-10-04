"""Audit this repository as its layered chain, paying only for what changed.

`ret audit .` runs the one gate (gate.py, every criterion) cold, always —
O(the whole claim) every time. This audits the SAME criteria the layered
way: each layer of scripts/selfclaim.py is re-earned against the live
`src/` bytes it judges, through the shipped reuse primitive
(`reticuli.reuse.layered_audit`), so a layer already earned on this host is
skipped and reported `reused`. Change one module and only its layer (and
the layers that ship it) is re-earned; change nothing and the whole
self-audit is a handful of cache hits.

    python3 scripts/selfaudit.py            # reuse earned layers
    python3 scripts/selfaudit.py --cold     # earn every layer (no reuse)

This is repo tooling, like selfclaim.py: it lives beside the chain
declaration it reads, not inside the shipped tool. The general capability
it leans on — `reuse.layered_audit` — is in `src`; the reticuli-specific
layer decomposition stays here. Nothing it does moves a root.
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import reuse                 # noqa: E402
import importlib.util                      # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "selfclaim", os.path.join(ROOT, "scripts", "selfclaim.py"))
_selfclaim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_selfclaim)
LAYERS = _selfclaim.LAYERS


def _spec_for_repo() -> list:
    """Turn selfclaim's (name, modules-it-adds, check, verdict) chain into
    layered_audit's spec: each layer judged against every module up to and
    including it, by its own check, staged under reticuli/ with the check
    under checks/."""
    src = os.path.join(ROOT, "src", "reticuli")
    layers, carried = [], []
    for name, adds, check, verdict in LAYERS:
        carried = carried + adds
        check_name = os.path.basename(check)
        if name == "reference":
            # the standalone twentieth layer (2026-10-04): vectors_check
            # expects the repository layout — the package under src/ and
            # the vectors beside it — so its room is staged that way, the
            # same shape scripts/selfclaim.py seals it in.
            files = {f"src/reticuli/{m}": os.path.join(src, m)
                     for m in carried}
            vec = os.path.join(ROOT, "spec", "vectors")
            # sorted full paths: readdir order is not identity (see the
            # matching note in scripts/selfclaim.py)
            for rel in sorted(
                    os.path.relpath(os.path.join(base, fn), ROOT)
                    for base, _dirs, names in os.walk(vec) for fn in names):
                files[rel] = os.path.join(ROOT, rel)
        else:
            files = {f"reticuli/{m}": os.path.join(src, m) for m in carried}
        layers.append({
            "name": name,
            "files": files,
            "check": (f"checks/{check_name}", os.path.join(ROOT, check)),
            "gate": f"python3 checks/{check_name}",
            "verdict": verdict,
        })
    return layers


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="layered self-audit with reuse")
    ap.add_argument("--cold", action="store_true",
                    help="earn every layer; do not reuse")
    ap.add_argument("--trust", default="self", metavar="POLICY",
                    help="self (default), signed:<id>, or quorum:<k>")
    a = ap.parse_args(argv)

    layers = _spec_for_repo()
    started = time.time()

    def progress(i, n, name):
        print(f"  [{i:2}/{n}] {name}", end="\r", flush=True)

    result = reuse.layered_audit(layers, reuse=not a.cold, policy=a.trust,
                                 progress=progress)
    elapsed = time.time() - started

    print(" " * 40, end="\r")
    reused = sum(1 for r in result["layers"] if r["status"] == "reused")
    earned = sum(1 for r in result["layers"] if r["status"] == "earned")
    for r in result["layers"]:
        mark = {"reused": "·", "earned": "+", "failed": "x"}[r["status"]]
        extra = (f"  ({r['seconds']}s)" if r["seconds"] else "") \
            + (f"  {r.get('detail', '')}" if r["status"] == "failed" else "")
        print(f"  {mark} {r['name']:12} {r['status']}{extra}")
    n = len(result["layers"])
    print(f"\n  {'self-audit OK' if result['ok'] else 'self-audit FAILED'}: "
          f"{reused}/{n} reused, {earned}/{n} earned this run — {elapsed:.1f}s")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
