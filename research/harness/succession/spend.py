"""What the lineage ledgers say a wave cost, for reconciling with the bill.

    python3 spend.py                 # every run
    python3 spend.py r29 r31         # named runs

Reads the `cost` events the runner now writes into each lineage's ledger,
which is append-only and committed. It deliberately does NOT read the
scratch rooms: those are where the cost used to live, and the harness
deletes them -- every attempt rmtrees its rebuild directory, so a retried
layer kept only its last attempt's record and a later resume destroyed even
that.

Reconciled against the gateway's own dashboard on 2026-10-15: the surviving
room records summed to $4.19 against $32.84 actually billed, a 7.3x
undercount, and by the time the check ran a fresh wave had wiped the rooms
and the figure read $0.00. The gateway's dashboard is the authority; this is
the instrument's own account of itself, and the gap between them is worth
printing on purpose.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(runs=()):
    for base in sorted(HERE.glob("lineages-*")):
        run = base.name.removeprefix("lineages-")
        if runs and run not in runs:
            continue
        for lineage in sorted(p for p in base.iterdir() if p.is_dir()):
            ledger = lineage / "ledger.jsonl"
            if not ledger.is_file():
                continue
            spend = {"usd": 0.0, "calls": 0, "tokens": 0,
                     "input": 0, "output": 0, "cached": 0, "attempts": 0}
            priced = True
            for line in ledger.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("event") != "cost":
                    continue
                spend["attempts"] += 1
                spend["calls"] += event.get("calls", 0) or 0
                spend["tokens"] += event.get("tokens", 0) or 0
                spend["input"] += event.get("input_tokens", 0) or 0
                spend["output"] += event.get("output_tokens", 0) or 0
                spend["cached"] += event.get("cached_input_tokens", 0) or 0
                if "usd" in event:
                    spend["usd"] += event["usd"] or 0.0
                else:
                    priced = False
            if spend["attempts"]:
                yield run, lineage.name, spend, priced


def main(runs) -> int:
    print(f"{'run':5s} {'lineage':12s} {'usd':>9s} {'calls':>6s} "
          f"{'tokens':>12s} {'cached':>12s} {'att':>4s}")
    total = 0.0
    unpriced = []
    for run, lineage, s, priced in rows(tuple(runs)):
        mark = "" if priced else "  (some attempts unpriced)"
        if not priced:
            unpriced.append(f"{run}:{lineage}")
        total += s["usd"]
        print(f"{run:5s} {lineage:12s} {s['usd']:9.4f} {s['calls']:6d} "
              f"{s['tokens']:12,d} {s['cached']:12,d} {s['attempts']:4d}{mark}")
    print(f"\n{'':5s} {'LEDGER TOTAL':12s} {total:9.4f}")
    if unpriced:
        print(f"  unpriced attempts in: {', '.join(unpriced)} — these are a "
              f"floor, not a measurement")
    print("  The gateway dashboard is the authority. Compare it against this "
          "and record the gap;\n  attempts that predate cost capture "
          "(before 2026-10-15) are missing here entirely.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
