"""Trust thermodynamics: the measured economics of earning and trusting.

Verification is work; trust is stored work; a signature transfers stored
work at near-zero cost. This extracts the actual numbers from the ledgers
the project has already written:

  generation cost   wall-clock for a producer to regrow one layer blind
                    (lineage ledger timestamp deltas, per layer, per run)
  earn cost         wall-clock to re-earn a layer's check against bytes
                    present (the layered self-audit's per-layer seconds)
  transfer cost     wall-clock to accept a trusted earn instead
                    (a cache lookup + ssh signature verification)

The ratios are the economy: generation/earn is the producer-verifier
asymmetry that makes acceptance criteria meaningful at all; earn/transfer
is the amplification a signature buys; generation/transfer is the full
leverage of the shared cache.

    python3 thermo.py
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SUC = REPO / "research/harness/succession"


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


def earn_costs() -> list:
    """Per-layer earn times: run the layered self-audit cold in an
    isolated cache and keep each layer's seconds."""
    import os
    sys.path.insert(0, str(REPO / "src"))
    sys.path.insert(0, str(REPO / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "selfaudit", REPO / "scripts" / "selfaudit.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    from reticuli import reuse
    os.environ["RETICULI_CACHE"] = str(HERE / "scratch" / "thermo-cache")
    subprocess.run(["rm", "-rf", os.environ["RETICULI_CACHE"]], check=False)
    layers = sa._spec_for_repo()
    result = reuse.layered_audit(layers, reuse=True)
    earned = [(r["name"], r["seconds"]) for r in result["layers"]]
    # and the transfer cost: the same audit warm, per layer
    t0 = time.time()
    warm = reuse.layered_audit(layers, reuse=True)
    transfer_total = time.time() - t0
    assert all(r["status"] == "reused" for r in warm["layers"])
    return earned, transfer_total / max(len(warm["layers"]), 1)


def main() -> None:
    gen = generation_costs()
    earned, transfer_each = earn_costs()
    earn_by = dict(earned)

    print("generation cost (blind regrowth, wall-clock seconds per layer):")
    all_gen = {}
    for lineage, rows in gen.items():
        for layer, dt in rows:
            all_gen.setdefault(layer, []).append(dt)
    total_gen_med = 0.0
    print(f"  {'layer':12} {'median s':>9} {'min':>7} {'max':>8} "
          f"{'earn s':>8} {'gen/earn':>9}")
    for layer, secs in all_gen.items():
        secs.sort()
        med = secs[len(secs)//2]
        total_gen_med += med
        e = earn_by.get(layer, float("nan"))
        ratio = med / e if e and e == e and e > 0 else float("inf")
        print(f"  {layer:12} {med:9.0f} {secs[0]:7.0f} {secs[-1]:8.0f} "
              f"{e:8.2f} {ratio:9.0f}x")
    total_earn = sum(s for _n, s in earned)
    print(f"\n  whole chain, medians: generation {total_gen_med/60:.1f} min, "
          f"earn {total_earn:.1f} s, transfer {transfer_each*20:.2f} s")
    print(f"  asymmetries: generation/earn {total_gen_med/max(total_earn,1e-9):.0f}x, "
          f"earn/transfer {total_earn/max(transfer_each*20,1e-9):.0f}x, "
          f"generation/transfer {total_gen_med/max(transfer_each*20,1e-9):.0f}x")


if __name__ == "__main__":
    main()
