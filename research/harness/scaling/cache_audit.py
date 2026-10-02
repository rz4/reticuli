"""A content-addressed, trust-weighted verdict cache over the self-claim.

An audit re-earns every verdict cold, from nothing. That is the guarantee,
and it is inherently O(the whole claim) — a one-line change costs the same
full re-derivation as a rewrite. This prototype shows the version that
scales, without giving up the guarantee: each layer's verdict is cached
under a content-addressed key, and a re-audit pays only for cache misses.

The key for a layer is two content hashes:

    check_hash   the bytes of the layer's acceptance check (what it pins)
    impl_hash    the bytes of the implementation it judges — the layer's
                 own modules AND every module beneath it, so a change low
                 in the stack invalidates everything above it and nothing
                 below

A cache entry is an earned verdict with provenance: who earned it, on what
machine, when, and how long it took. A changed check or a changed module
is a new key, hence an automatic miss — content-addressing makes cache
invalidation free. The only staleness left is trust staleness: do you
still accept whoever earned the cached verdict? That is a policy, not a
correctness question, and the audit says plainly which layers it trusted
and which it re-earned cold this run — a weaker claim stated honestly,
never a strong one faked.

    python3 cache_audit.py --demo

Research tooling: it runs each layer's check in a staged room the way
scripts/selfclaim.py seals it, times the earn, and keeps the cache in a
json store beside this file. Nothing here moves a root.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SRC = REPO / "src" / "reticuli"
SCRATCH = HERE / "scratch"
CACHE_PATH = HERE / "cache_store.json"

_spec = importlib.util.spec_from_file_location(
    "selfclaim", REPO / "scripts" / "selfclaim.py")
_selfclaim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_selfclaim)
LAYERS = _selfclaim.LAYERS      # (name, modules it adds, check path, verdict)

VENV_PY = str(REPO / ".venv" / "bin" / "python")


def _me() -> dict:
    """This earner's identity: the machine, and a signer from the env or
    the OS user. A cache hit under the 'self' policy trusts exactly this."""
    return {"machine": os.environ.get("RETICULI_CACHE_MACHINE", socket.gethostname()),
            "signer": os.environ.get("RETICULI_CACHE_SIGNER",
                                     os.environ.get("USER", "unknown"))}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _modules_below(idx: int) -> list:
    """Every module the layers up to and including `idx` have put down."""
    mods: list = []
    for _name, adds, _check, _verdict in LAYERS[:idx + 1]:
        mods += adds
    return mods


def _impl_hash(idx: int, src: Path) -> str:
    """Hash of the implementation this layer judges: its own modules and
    all beneath, in path order, so the key moves with any of them."""
    h = hashlib.sha256()
    for rel in sorted(_modules_below(idx)):
        h.update(rel.encode() + b"\0")
        h.update((src / rel).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _check_hash(check_rel: str, criteria: Path) -> str:
    return _sha((criteria / Path(check_rel).name).read_bytes())


def _key(idx: int, src: Path, criteria: Path) -> str:
    _name, _adds, check_rel, _verdict = LAYERS[idx]
    return _sha((_check_hash(check_rel, criteria) + _impl_hash(idx, src)).encode())


def _stage(idx: int, src: Path, criteria: Path, room: Path) -> str:
    """Lay the layer out the way selfclaim seals it: the modules it judges
    under reticuli/, its check under checks/. Returns the gate command."""
    _name, _adds, check_rel, _verdict = LAYERS[idx]
    if room.exists():
        shutil.rmtree(room)
    (room / "checks").mkdir(parents=True)
    for rel in _modules_below(idx):
        dst = room / "reticuli" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, dst)
    check_name = Path(check_rel).name
    shutil.copyfile(criteria / check_name, room / "checks" / check_name)
    return f"{VENV_PY} checks/{check_name}"


def _earn(idx: int, src: Path, criteria: Path) -> tuple:
    """Run the layer's check cold in its staged room. Returns (ok, seconds,
    tail) — exactly the work a from-scratch audit pays for this layer."""
    name = LAYERS[idx][0]
    room = SCRATCH / f"earn_{idx:02d}_{name}"
    gate = _stage(idx, src, criteria, room)
    env = dict(os.environ, PYTHONPATH=str(room), NO_COLOR="1",
               PYTHONDONTWRITEBYTECODE="1")
    t = time.time()
    try:
        r = subprocess.run(gate, shell=True, cwd=str(room), env=env,
                           capture_output=True, text=True, timeout=1800,
                           check=False)
        ok = r.returncode == 0
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:]
    except subprocess.TimeoutExpired:
        ok, tail = False, ["timeout"]
    return ok, round(time.time() - t, 2), (tail[0][:160] if tail else "")


# -- the cache store ---------------------------------------------------------

def load_cache() -> dict:
    if CACHE_PATH.is_file():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _accept(entries: list, policy: str, me: dict) -> str | None:
    """Does the trust policy accept any cached entry for a key? Returns a
    short description of WHY it was a hit, or None for a miss."""
    good = [e for e in entries if e.get("ok")]
    if not good:
        return None
    if policy == "self":
        mine = [e for e in good if e["machine"] == me["machine"]
                and e["signer"] == me["signer"]]
        return f"self ({me['signer']})" if mine else None
    if policy.startswith("signed:"):
        who = policy.split(":", 1)[1]
        return f"signed by {who}" if any(e["signer"] == who for e in good) else None
    if policy.startswith("quorum:"):
        k = int(policy.split(":", 1)[1])
        earners = {e["machine"] for e in good}
        return f"{len(earners)} independent earners" if len(earners) >= k else None
    raise ValueError(f"unknown trust policy: {policy}")


def caching_audit(src: Path, criteria: Path, policy: str, cache: dict,
                  earn: bool = True) -> dict:
    """Audit every layer, paying only for misses. Hits are skipped on the
    trust policy; misses are earned cold (unless earn=False, a dry run that
    only classifies). Returns rows and totals."""
    SCRATCH.mkdir(exist_ok=True)
    me = _me()
    rows, spent = [], 0.0
    for idx, (name, _adds, _check, _verdict) in enumerate(LAYERS):
        key = _key(idx, src, criteria)
        why = _accept(cache.get(key, []), policy, me)
        if why:
            rows.append({"layer": name, "key": key[:8], "status": "hit",
                         "source": why, "seconds": 0.0})
            continue
        if not earn:
            rows.append({"layer": name, "key": key[:8], "status": "would-earn",
                         "source": "", "seconds": 0.0})
            continue
        ok, seconds, tail = _earn(idx, src, criteria)
        spent += seconds
        entry = {"ok": ok, "when": time.time(), "seconds": seconds, **me}
        cache.setdefault(key, []).append(entry)
        save_cache(cache)
        rows.append({"layer": name, "key": key[:8],
                     "status": "earned" if ok else "FAILED",
                     "source": f"cold on {me['machine']}", "seconds": seconds,
                     "tail": "" if ok else tail})
    hits = sum(1 for r in rows if r["status"] == "hit")
    earned = sum(1 for r in rows if r["status"] == "earned")
    failed = [r for r in rows if r["status"] == "FAILED"]
    return {"rows": rows, "hits": hits, "earned": earned,
            "failed": failed, "spent": round(spent, 1), "policy": policy}


def report(result: dict) -> None:
    print(f"\n  {'layer':12} {'key':9} {'verdict':9} source")
    for r in result["rows"]:
        print(f"  {r['layer']:12} {r['key']:9} {r['status']:9} {r['source']}"
              + (f"  ({r['seconds']}s)" if r['seconds'] else ""))
    n = len(result["rows"])
    print(f"\n  policy {result['policy']}: {result['hits']}/{n} trusted from "
          f"cache, {result['earned']}/{n} earned cold this run"
          + (f", {len(result['failed'])} FAILED" if result['failed'] else "")
          + f" — spent {result['spent']}s"
          + (" (would have been the full cold cost)" if result['earned'] == n
             else " instead of the full cold cost"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="self")
    ap.add_argument("--dry", action="store_true", help="classify, do not earn")
    ap.add_argument("--reset", action="store_true", help="empty the cache first")
    args = ap.parse_args()
    if args.reset and CACHE_PATH.exists():
        CACHE_PATH.unlink()
    cache = load_cache()
    report(caching_audit(SRC, REPO / "criteria", args.policy, cache,
                         earn=not args.dry))
