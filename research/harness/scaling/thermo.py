"""Trust thermodynamics: the measured economics of earning and trusting.

Verification is work; trust is stored work; a signature transfers stored
work at low cost. This extracts the actual numbers from evidence the
project has already written, measures the rest, and writes every number
it reports to `thermo_report.json` beside this file — a report whose
numbers cannot be traced to that file is a claim, not a measurement.

  generation cost   wall-clock for a producer to regrow one layer blind
                    (lineage ledger timestamp deltas, per layer, per run)
  earn cost         wall-clock to re-earn a layer's check against bytes
                    present (the layered self-audit, cold, per layer)
  transfer cost     wall-clock to accept a stored earn instead. Two
                    honest variants, kept apart: `self` (this host's own
                    cache: a fingerprint lookup, no cryptography) and
                    `signed` (a shared earn verified with ssh-keygen
                    against an allowed-signers file — the thing a
                    NETWORK actually pays, measured with an ephemeral
                    key, local cache cleared so nothing shortcuts it).

Unit discipline, learned the hard way: the first write-up of this
instrument divided a per-chain earn by a per-layer transfer and
published 1,469x and 553,704x. Every ratio below is per-chain over
per-chain; per-layer rows are printed as rows, never mixed into a
headline. And the transfer it timed was the `self` lookup while the
prose said "signature verification" — the signed path is now measured
as itself.

    python3 thermo.py
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SUC = REPO / "research/harness/succession"
SCRATCH = HERE / "scratch" / "thermo"


def generation_costs() -> dict:
    """Per-layer regrowth wall-times from every lineage ledger: the delta
    between consecutive 'grown' timestamps approximates the layer's
    producer session (staging and gates included — the price of a blind
    regrowth as actually paid)."""
    runs = {}
    for ledger in sorted(SUC.glob("lineages*/*/ledger.jsonl")):
        lineage = f"{ledger.parent.parent.name.replace('lineages', 'r1')}/{ledger.parent.name}"
        events = [json.loads(line) for line in open(ledger)]
        grown = [e for e in events if e.get("event") == "grown"]
        prev = None
        rows = []
        for e in grown:
            t = datetime.strptime(e["when"], "%Y-%m-%dT%H:%M:%S")
            if prev is not None:
                dt = (t - prev[1]).total_seconds()
                if 0 < dt < 7200:                 # resumes split sessions
                    rows.append((e["layer"], dt))
            prev = (e["layer"], t)
        if rows:
            runs[lineage] = rows
    return runs


def _layers():
    sys.path.insert(0, str(REPO / "src"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "selfaudit", REPO / "scripts" / "selfaudit.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    return sa._spec_for_repo()


def measure() -> dict:
    """Cold earn, then both transfer variants, in isolated caches with an
    ephemeral signing key. Returns every timing, per layer and per chain."""
    from reticuli import reuse

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    local = SCRATCH / "local-cache"
    shared = SCRATCH / "shared-cache"
    key = SCRATCH / "thermo_key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C",
                    "thermo", "-f", str(key)], check=True)
    allowed = SCRATCH / "allowed_signers"
    allowed.write_text(f"thermo {key.with_suffix('.pub').read_text()}")

    os.environ[reuse.CACHE_ENV] = str(local)
    os.environ[reuse.SHARED_ENV] = str(shared)
    os.environ[reuse.SIGN_KEY_ENV] = str(key)
    os.environ["RETICULI_REUSE_SIGNER"] = "thermo"

    layers = _layers()
    n = len(layers)

    # cold: every layer earned, each signed into the shared cache
    t0 = time.time()
    cold = reuse.layered_audit(layers, reuse=True)
    cold_wall = time.time() - t0
    assert cold["ok"], "the cold self-audit must pass"
    earn_rows = [(r["name"], r["seconds"]) for r in cold["layers"]]

    # transfer, self policy: local fingerprint lookup, no cryptography
    t0 = time.time()
    warm = reuse.layered_audit(layers, reuse=True)
    transfer_self_chain = time.time() - t0
    assert all(r["status"] == "reused" for r in warm["layers"])

    # transfer, signed policy: the local cache is cleared, so every layer
    # must be accepted from the shared cache via ssh-keygen verification —
    # the cost a network participant pays to accept another's earn
    shutil.rmtree(local)
    t0 = time.time()
    signed = reuse.layered_audit(layers, reuse=True, policy="signed:thermo",
                                 allowed=str(allowed))
    transfer_signed_chain = time.time() - t0
    reused = sum(1 for r in signed["layers"] if r["status"] == "reused")
    assert reused == n, f"signed transfer must cover all layers, got {reused}/{n}"

    return {"layer_count": n, "earn_rows": earn_rows, "cold_wall_s": cold_wall,
            "transfer_self_chain_s": transfer_self_chain,
            "transfer_signed_chain_s": transfer_signed_chain}


def main() -> None:
    gen = generation_costs()
    m = measure()
    earn_by = dict(m["earn_rows"])
    n = m["layer_count"]

    all_gen = {}
    for lineage, rows in gen.items():
        for layer, dt in rows:
            all_gen.setdefault(layer, []).append(dt)

    print("generation cost (blind regrowth, wall-clock seconds per layer):")
    print(f"  {'layer':12} {'median s':>9} {'min':>7} {'max':>8} "
          f"{'earn s':>8} {'gen/earn':>9}")
    gen_rows = {}
    total_gen_med = 0.0
    for layer, secs in all_gen.items():
        secs.sort()
        med = secs[len(secs) // 2]
        total_gen_med += med
        e = earn_by.get(layer, float("nan"))
        ratio = med / e if e and e == e and e > 0 else float("inf")
        gen_rows[layer] = {"median_s": med, "min_s": secs[0], "max_s": secs[-1],
                           "samples": len(secs), "earn_s": e}
        print(f"  {layer:12} {med:9.0f} {secs[0]:7.0f} {secs[-1]:8.0f} "
              f"{e:8.2f} {ratio:9.0f}x")

    total_earn = sum(s for _n2, s in m["earn_rows"])
    t_self = m["transfer_self_chain_s"]
    t_signed = m["transfer_signed_chain_s"]
    chain = {
        "generation_median_s": total_gen_med,
        "earn_s": total_earn,
        "transfer_self_s": t_self,
        "transfer_signed_s": t_signed,
        # per-chain over per-chain, nothing else
        "generation_over_earn": total_gen_med / max(total_earn, 1e-9),
        "earn_over_transfer_self": total_earn / max(t_self, 1e-9),
        "earn_over_transfer_signed": total_earn / max(t_signed, 1e-9),
        "generation_over_transfer_self": total_gen_med / max(t_self, 1e-9),
        "generation_over_transfer_signed": total_gen_med / max(t_signed, 1e-9),
    }

    print(f"\n  whole chain ({n} layers), per-chain units throughout:")
    print(f"    generation (median) {total_gen_med/60:8.1f} min")
    print(f"    earn (cold)         {total_earn:8.1f} s")
    print(f"    transfer, self      {t_self:8.2f} s   (local lookup, no crypto)")
    print(f"    transfer, signed    {t_signed:8.2f} s   (ssh-verified shared earns)")
    print("  asymmetries (per-chain / per-chain):")
    print(f"    generation/earn            {chain['generation_over_earn']:10.0f}x")
    print(f"    earn/transfer(self)        {chain['earn_over_transfer_self']:10.0f}x")
    print(f"    earn/transfer(signed)      {chain['earn_over_transfer_signed']:10.0f}x")
    print(f"    generation/transfer(self)  {chain['generation_over_transfer_self']:10.0f}x")
    print(f"    generation/transfer(signed){chain['generation_over_transfer_signed']:10.0f}x")

    report = {"when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "note": ("wall-clock, one machine; generation rows are ledger "
                       "deltas across all lineage runs (eras mixed, stated); "
                       "earn/transfer measured now, load not isolated"),
              "loadavg": os.getloadavg(),
              "generation_sources": sorted(gen),
              "per_layer": gen_rows, "chain": chain,
              "earn_rows": m["earn_rows"],
              "cold_wall_s": m["cold_wall_s"]}
    out = HERE / "thermo_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n  every number above -> {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
