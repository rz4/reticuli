"""The promotion ledger: the chain from environmental pressure to identity.

Today that chain is implicit. The criteria have moved roughly a hundred times
and each move's reason lives in a commit message or a comment in the recipe --
readable by a person, not by a program. An append-only record of
(entry, pin, root before, root after, signature) makes the ratchet a first
class artifact: for any criterion you can ask which witness forced it, and for
any witness you can ask whether it was ever declared.

Nothing here performs a promotion. A promotion is an ordinary root move -- a
criterion is written, its path is added to the recipe's inputs, the gate earns
a new output, the root is re-sealed -- and it is signed by the keyholder. This
module records that it happened and refuses records that do not describe one.
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "zeta.promotion.1"
LANES = ("contraction", "eviction", "repair")
REQUIRED = ("schema", "entry", "pressure_id", "lane", "pin", "root_before",
            "root_after", "signature", "when")


def validate(record):
    missing = [key for key in REQUIRED if key not in record]
    if missing:
        raise ValueError(f"promotion record omits {', '.join(missing)}")
    if record["schema"] != SCHEMA:
        raise ValueError("unsupported promotion schema")
    if record["lane"] not in LANES:
        raise ValueError(f"unknown lane: {record['lane']}")
    for field in ("root_before", "root_after"):
        value = record[field]
        if not isinstance(value, str) or len(value) != 64 or value != value.lower():
            raise ValueError(f"{field} is not a 64-character lowercase root")
    if record["root_before"] == record["root_after"]:
        raise ValueError("a promotion moves the root; these are equal")
    if not str(record["signature"]).strip():
        raise ValueError("a promotion carries a signature")
    if record["lane"] == "eviction" and not record.get("evicted"):
        raise ValueError("an eviction names the members it evicts")
    return record


def append(path, record):
    validate(record)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read(path):
    path = Path(path)
    if not path.exists():
        return []
    return [validate(json.loads(line)) for line in path.read_text().splitlines()
            if line.strip()]


def chain(path):
    """Check that the recorded promotions form one unbroken root sequence."""
    records = read(path)
    for earlier, later in zip(records, records[1:]):
        if earlier["root_after"] != later["root_before"]:
            raise ValueError(f"promotion chain breaks at {later['entry']}: "
                             f"{earlier['root_after'][:12]} then "
                             f"{later['root_before'][:12]}")
    return records
