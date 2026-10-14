"""A promotion record must describe a signed root move, or be refused.

The ledger is the only place the chain from pressure to identity is written
down. If it accepts a record that does not move a root, or one with no
signature, or an eviction that does not say who it evicted, then the chain it
records is not the chain that happened -- which is worse than having no
ledger, because it reads as evidence.
"""

import sys
import tempfile
from pathlib import Path

# The claim directory, which is this file's parent. A sandboxed audit
# materialises the claim AS the workspace root, so an import reaching
# one level further up works in the repository and fails cold.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import ledger as ledgerlib

BEFORE = "a" * 64
AFTER = "b" * 64
THIRD = "c" * 64


def record(**overrides):
    base = {"schema": "zeta.promotion.1", "entry": "0123456789abcdef",
            "pressure_id": "record_surface/f", "lane": "contraction",
            "pin": "criteria/record_check.py", "root_before": BEFORE,
            "root_after": AFTER, "signature": "keyholder",
            "when": "2026-10-14T00:00:00Z"}
    return {**base, **overrides}


def check(condition, why):
    if not condition:
        raise SystemExit(f"ledger_check: {why}")


def refuses(data, fragment):
    try:
        ledgerlib.validate(data)
    except ValueError as exc:
        check(fragment in str(exc),
              f"expected a refusal mentioning {fragment!r}, got {exc}")
        return
    raise SystemExit(f"ledger_check: accepted a record it must refuse ({fragment})")


ledgerlib.validate(record())
ledgerlib.validate(record(lane="eviction", evicted=["r24-claude"]))

# A promotion moves the root. A record where it did not is not a promotion.
refuses(record(root_after=BEFORE), "moves the root")

# No agent signs. A record without a signature does not describe what happened.
refuses(record(signature=""), "carries a signature")
refuses(record(signature="   "), "carries a signature")

# An eviction that does not name its casualties hides the cost of the decision.
refuses(record(lane="eviction"), "names the members it evicts")

refuses(record(lane="improvement"), "unknown lane")
refuses(record(root_before="A" * 64), "lowercase")
refuses(record(root_after="b" * 10), "lowercase root")
refuses(record(schema="zeta.promotion.99"), "unsupported promotion schema")
for field in ("entry", "pin", "when", "root_after", "signature"):
    missing = record()
    del missing[field]
    refuses(missing, field)

# The recorded promotions must form one unbroken sequence of roots. A gap means
# a root move happened that the ledger does not account for.
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "ledger.jsonl"
    check(ledgerlib.read(path) == [], "an absent ledger reads as no promotions")
    ledgerlib.append(path, record())
    ledgerlib.append(path, record(root_before=AFTER, root_after=THIRD,
                                  entry="fedcba9876543210"))
    check(len(ledgerlib.chain(path)) == 2, "a continuous chain must read")

    ledgerlib.append(path, record(root_before="d" * 64, root_after="e" * 64,
                                  entry="0f0f0f0f0f0f0f0f"))
    try:
        ledgerlib.chain(path)
    except ValueError as exc:
        check("chain breaks" in str(exc), f"a gap must be named: {exc}")
    else:
        raise SystemExit("ledger_check: accepted a ledger with a broken chain")

print("ledger-ok")
