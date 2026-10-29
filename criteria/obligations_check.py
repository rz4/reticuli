"""Five declared obligations that had no criterion. Writes OBLIGATIONS_OK.

    python3 criteria/obligations_check.py       (from the repository root)

Each was declared somewhere -- in the record spec, in the verification spec, in
the kernel's own docstring, or by the shape of the determination result -- and
none was tested, so the root admitted an implementation that did otherwise.
All five hold on the authored tree, which is why closing them evicts nobody.

Signed by the keyholder 2026-10-14. The witnesses are recorded in the signed
proposal for this batch, kept with the project's research record; most of them
are surviving mutants, a staged intrusion, or a measurement, not arguments.

This docstring deliberately names no path outside the claim. A pinned file is
materialised into a rebuilding producer's room, which holds only the declared
inputs, so a reference to anything else dangles there. The first version of
this file cited the proposal by path and the held-out battery caught it -- a
test outside the root, catching what the gate by design cannot see.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import attest, core, recipe, run

HEX = "a" * 64
RECORD = {
    "record": 2, "claim": {}, "name": "example", "root": HEX,
    "build_digest": HEX,
    "gates": [{"output": "EXAMPLE_OK", "status": "ok", "sandbox": "seatbelt"}],
    "environment": {"platform": "p", "machine": "m", "runtime": "r"},
    "when": "2026-10-14T00:00:00Z",
}

#: The environment the sandbox grants a gate, set adversarially. A verdict must
#: not depend on any of it. Sampled, not closed: these axes are what was
#: measured, and the criterion re-measures exactly them.
HOSTILE = [
    ("turkish-locale", {"LANG": "tr_TR.UTF-8", "LC_ALL": "tr_TR.UTF-8"}),
    ("c-locale", {"LANG": "C", "LC_ALL": "C"}),
    ("far-timezone", {"TZ": "Pacific/Kiritimati"}),
    ("hash-seed-1", {"PYTHONHASHSEED": "1"}),
    ("hash-seed-9999", {"PYTHONHASHSEED": "9999"}),
]

#: Run in a subprocess so the environment is really different, rather than
#: mutated inside a process that has already imported and cached everything.
PROBE = (
    "import json, sys; sys.path.insert(0, %r);"
    "from reticuli._kernel import attest, core;"
    "doc = json.loads(sys.argv[1]);"
    "print(json.dumps({"
    "'digest': attest.record_digest(doc),"
    "'canonical': attest.record_canonical(doc).decode(),"
    "'now_is_utc': core._now().endswith('Z'),"
    "'keep_env': list(core._KEEP_ENV)[:6],"
    "}, sort_keys=True))"
)


def _ledger(directory, event):
    os.makedirs(os.path.join(directory, ".reticuli"), exist_ok=True)
    with open(os.path.join(directory, ".reticuli", "ledger.jsonl"), "w",
              encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def cost_never_counts_a_boolean():
    """spec/record.md: a cost value is a number and never a boolean.

    A boolean smuggled into a total is a measurement that looks like money,
    and the total is what a declared envelope is compared against.
    """
    with tempfile.TemporaryDirectory() as directory:
        _ledger(directory, {"event": "producer", "usd": True, "tokens": 5})
        totals = run.cost(directory) or {}
        assert "usd" not in totals, \
            f"a boolean cost value must not enter the totals: {totals}"
        assert totals.get("tokens") == 5, \
            f"a real measurement beside it must survive: {totals}"
    with tempfile.TemporaryDirectory() as directory:
        _ledger(directory, {"event": "producer", "usd": False})
        assert "usd" not in (run.cost(directory) or {}), \
            "False is a boolean too, and zero is not what it means"


def a_cost_value_is_finite():
    """spec/record.md: NaN and the infinities are refused along with negatives.

    Not a stylistic tightening. A cost is a measurement of work, and neither
    NaN nor an infinity reports any; worse, both poison the comparison a cost
    exists for, since a declared ceiling is false against NaN whatever the
    ceiling and false against Infinity for every ceiling. A reader that
    accepts one turns an unmeasurable report into a verdict.

    Reachable from a file: Python's JSON reader takes the bare NaN literal and
    the canonicaliser re-emits it, so the raw-equals-canonical bond holds.
    Found by the r25 trial, where the regrown implementation refused these and
    the shipped one accepted them.
    """
    for unit in ("usd", "tokens", "calls", "seconds"):
        for label, value in (("nan", float("nan")), ("+inf", float("inf")),
                             ("-inf", float("-inf"))):
            doc = dict(RECORD, cost={unit: value})
            try:
                attest.record_validate(doc)
            except core.ClaimError:
                continue
            raise AssertionError(
                f"a reader must refuse a {label} cost value ({unit})")
    # A finite value at the same magnitude still reads, so the rule refuses
    # non-finiteness rather than largeness.
    attest.record_validate(dict(RECORD, cost={"usd": 1e308}))
    attest.record_validate(dict(RECORD, cost={"usd": 0}))
    # And the ledger totaller agrees with the reader: a non-finite number in a
    # ledger is not a measurement, so it must not reach a total either.
    with tempfile.TemporaryDirectory() as directory:
        _ledger(directory, {"event": "producer", "usd": float("inf"),
                            "tokens": 5})
        totals = run.cost(directory) or {}
        assert "usd" not in totals, \
            f"a non-finite ledger value must not enter the totals: {totals}"
        assert totals.get("tokens") == 5, "a real measurement still survives"


def the_band_is_closed():
    """spec/verification.md and run.py: comparability is [1/tol, tol].

    An implementation using an open interval would refuse a redo whose ratio
    sits exactly on the declared tolerance, so two conforming members would
    disagree about a verdict at the boundary.
    """
    assert run._in_band(2.0, 1.0, 2.0), "the band includes its upper boundary"
    assert run._in_band(1.0, 2.0, 2.0), "the band includes its lower boundary"
    assert run._in_band(1.0, 1.0, 2.0), "and the middle, obviously"
    assert not run._in_band(2.01, 1.0, 2.0), "and excludes what lies beyond"
    assert not run._in_band(1.0, 2.01, 2.0), "on both sides"


def the_gate_runs_only_pinned_criteria():
    """The read set must be inside the pinned set.

    gate.py enumerates its suites with a glob, so its read set includes a
    directory listing, and no pinned path determines what a listing returns.
    A cold audit materialises only declared inputs, so the canonical path is
    sound; this closes the warm development run, where dropping a failing file
    into criteria/ turns a conforming tree non-conforming.
    """
    parsed = recipe.load_recipe(".")
    pinned = {p for p in parsed["claim"].get("inputs", []) or []
              if p.startswith("criteria/") and p.endswith(".py")}
    present = set(glob.glob("criteria/*.py"))
    assert present == pinned, (
        f"the gate runs what the root does not pin, or the reverse: "
        f"unpinned {sorted(present - pinned)}, "
        f"missing {sorted(pinned - present)}")


def canonical_bytes_are_verbatim():
    """spec/record.md: a reader does not normalise numeric form.

    A reader that normalised would canonicalise 1.0 to 1, find a file holding
    1.0 no longer matching its own canonical bytes, and refuse a valid record.
    """
    integral = dict(RECORD, cost={"usd": 1})
    decimal = dict(RECORD, cost={"usd": 1.0})
    assert attest.record_canonical(integral) != attest.record_canonical(decimal), \
        "numeric form must survive canonicalisation untouched"
    assert attest.record_digest(integral) != attest.record_digest(decimal), \
        "a digest names bytes, so a different representation is a different digest"
    assert b'"usd": 1.0' in attest.record_canonical(decimal), \
        "a decimal stays a decimal"
    assert b'"usd": 1,' in attest.record_canonical(integral) or \
           b'"usd": 1}' in attest.record_canonical(integral), \
        "an integer stays an integer"
    # And the bond the clause protects: a file holds its own canonical bytes.
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "record.json")
        with open(path, "wb") as handle:
            handle.write(attest.record_canonical(decimal))
        assert attest.record_read(path)["cost"]["usd"] == 1.0, \
            "a record written with a decimal must read back"


def a_verdict_ignores_the_granted_environment():
    """Anything a gate can read is something a verdict could depend on.

    The sandbox grants HOME, LANG, LC_ALL and TZ, which the host contract does
    not declare. Declaring them would constrain nothing -- `requires` asserts
    presence, not value -- so the obligation is that the grant goes unused.

    Sampled, not closed. These are the axes that were measured; a criterion
    cannot quantify over every environment, and claiming otherwise would be a
    universal statement resting on five points.
    """
    granted = set(core._KEEP_ENV)
    for name in ("LANG", "LC_ALL", "TZ", "HOME"):
        assert name in granted, (
            f"{name} left the sandbox allow-list; this criterion samples the "
            f"grant and must be updated when the grant changes")
    document = json.dumps(dict(RECORD, cost={"usd": 1.5}))
    command = [sys.executable, "-c", PROBE % os.path.abspath(SRC), document]
    base = subprocess.run(command, capture_output=True, text=True, check=True,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    expected = json.loads(base.stdout)
    assert expected["now_is_utc"], "a recorded time is UTC, whatever TZ says"
    for label, overrides in HOSTILE:
        done = subprocess.run(command, capture_output=True, text=True,
                              check=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                                       **overrides))
        assert json.loads(done.stdout) == expected, (
            f"the kernel answered differently under {label}: a verdict must "
            f"not depend on what the sandbox merely grants")


def battery():
    cost_never_counts_a_boolean()
    a_cost_value_is_finite()
    the_band_is_closed()
    the_gate_runs_only_pinned_criteria()
    canonical_bytes_are_verbatim()
    a_verdict_ignores_the_granted_environment()


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("OBLIGATIONS_OK", "w", encoding="utf-8") as handle:
            handle.write("obligations-ok\n")
    print("obligations-ok")
