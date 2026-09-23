"""The boundary C, subject-agnostic.

A boundary is a set of happy-path checks (the behavior everyone must get right)
plus pinned rules (input -> required outcome) that the ratchet adds as
counterexamples are accepted. It gates one operation, named by `op`
("decode" for the base64 subject, "evaluate" for quirkcalc). Subjects live in
their own modules (base64_subject.py, quirkcalc_subject.py) and build a
Boundary; everything downstream — the differential, the reducer, the metrics —
is subject-independent and reaches the operation through `call`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The operation under test. The orchestrator sets this from the subject's
# boundary before running the differential, so `call` reaches the right method.
OP = "decode"


def observe(fn, arg):
    """One implementation's behavior on one input, canonicalized so outcomes
    from different implementations compare equal iff the behavior matches.

    ("ok", value) on return; ("err",) on any exception. The exception *type* is
    deliberately not part of the outcome: two implementations that both refuse
    an input behave the same to a caller. Rejection is rejection.
    """
    try:
        v = fn(arg)
    except Exception:  # noqa: BLE001 — any refusal is one behavior: rejected
        return ("err",)
    if isinstance(v, (bytes, bytearray)):
        v = bytes(v)
    return ("ok", v)


def call(impl, arg):
    """Observe the operation under test (OP) on one input."""
    return observe(getattr(impl, OP), arg)


def outcome_matches(observed, required) -> bool:
    """A rule pins either an exact value or 'must reject'."""
    if required[0] == "err":
        return observed[0] == "err"
    return observed == required


@dataclass
class Boundary:
    name: str
    op: str = "decode"
    generation: int = 0
    checks: list = field(default_factory=list)   # each: impl -> list[str] failures
    rules: list = field(default_factory=list)     # (input, required_outcome)

    def gate(self, impl) -> tuple[bool, list[str]]:
        """Does this implementation satisfy C? Returns (ok, reasons-it-failed)."""
        fails: list[str] = []
        for check in self.checks:
            fails.extend(check(impl))
        fn = getattr(impl, self.op, None)
        if fn is None:
            fails.append(f"missing operation {self.op!r}")
            return (False, fails)
        for inp, required in self.rules:
            got = observe(fn, inp)
            if not outcome_matches(got, required):
                fails.append(f"rule {self.op}({inp!r}) -> {got!r}, want {required!r}")
        return (not fails, fails)

    def decides(self, probe) -> bool:
        return any(inp == probe for inp, _ in self.rules)

    def tighten(self, rules) -> Boundary:
        """C_{n+1} = C_n + accepted counterexamples. A keyholder's act; the
        harness only proposes the rules."""
        return Boundary(self.name, self.op, self.generation + 1,
                        list(self.checks), self.rules + list(rules))
