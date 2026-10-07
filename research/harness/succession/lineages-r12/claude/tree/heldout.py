"""Held-out evaluation: measuring past the pinned gate.

A claim's own gate is inside its root -- a producer sees it, and passing
it is the acceptance condition. A **held-out case** is a check that is
never shown to a producer and never pinned into the claim at all; it
exists only on the measuring host, and is run against an already-built
claim directory afterward. Passing the pinned gate proves the claim
holds; also passing held-out cases is evidence the realization
generalizes, rather than having been shaped to the pinned gate alone.

A held-out case runs under the same execution contract as any other gate
(`kernel.run_gate`: scrubbed environment, sandboxed, bounded) so that
"held out" changes only which checks are run, never how.

Stdlib only.
"""
from . import kernel


def evaluate(d: str, cases: list) -> list:
    """Run every held-out case against the claim directory `d`.

    Each case is `{"name", "run"}`, a shell command executed exactly as
    a gate would be. Returns one row per case, in order:
    `{"name", "status"}`, `status` from the same vocabulary `run_gate`
    reports (`ok` / `failed` / `timeout`).
    """
    rows = []
    for case in cases:
        result = kernel.run_gate(case["run"], d)
        rows.append({"name": case["name"], "status": result["status"]})
    return rows


def score(rows: list) -> dict:
    """Summarize `evaluate`'s rows: how many held-out cases passed."""
    total = len(rows)
    passed = sum(1 for row in rows if row["status"] == "ok")
    return {"passed": passed, "total": total,
            "rate": (passed / total) if total else 0.0}
