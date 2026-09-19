"""PROPOSED criterion additions — the residual machine surface a rebuild can drift.

*Not yet a criterion.* Folding these assertions into `criteria/surface_check.py`
would MOVE THE REPOSITORY ROOT (that file is a pinned input), so this ships
under research/ as a validated proposal, not applied. It is runnable, and it
PASSES against the current, correct src/ — which is the point: it pins behavior
the shipped tool already has but `surface_check.py` never checks, so a
from-criteria rebuild could drop it and still certify.

Each block closes one gap found by the 2026-09-18 self-rebuild completeness
audit (research/audits/self-rebuild-completeness-2026-09-18.md). Two of them
(G1, G6) were mutation-proven: reverting the behavior on a copy of src still
passed surface_check.py.

    PYTHONPATH=src python3 research/proposals/surface_json_contract_check.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli import cli

ENVELOPE = {"command", "ok", "status", "root", "data"}


def _run2(argv: list[str]) -> tuple[int, str, str]:
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exit_:               # argparse exit-2 path
            code = exit_.code
    return code, buf.getvalue(), err.getvalue()


def _claim(d: str) -> str:
    """A minimal real claim, sealed in place through the flag-declared path."""
    proj = os.path.join(d, "proj")
    os.makedirs(proj)
    with open(os.path.join(proj, "primes.py"), "w") as f:
        f.write("def is_prime(n):\n    return n > 1 and all(n % k for k in range(2, n))\n")
    with open(os.path.join(proj, "check.py"), "w") as f:
        f.write("from primes import is_prime\n"
                "assert [n for n in range(10) if is_prime(n)] == [2, 3, 5, 7]\n")
    code, _, err = _run2(["pack", proj, "--generated", "primes.py", "--input",
                          "check.py", "--gate",
                          "python3 check.py && printf ok > OK",
                          "--output", "OK"])
    assert code == 0, f"fixture claim failed to seal: {err[-200:]}"
    return proj


def battery() -> None:
    d = tempfile.mkdtemp()
    try:
        claim = _claim(d)
        missing = os.path.join(d, "no-such-claim")

        # -- G1 (mutation-proven): a REFUSAL still speaks the envelope on stdout.
        # surface_check only ever builds the envelope on success paths, so a
        # rebuild that prints refusals as a bare stderr line -- empty stdout --
        # certifies clean yet breaks `ret <verb> --json | jq`, the first thing
        # automation does to ask "is this even a claim?".
        for verb in ("verify", "audit", "status", "assess"):
            code, out, err = _run2([verb, missing, "--json"])
            assert code == 1, f"{verb}: a refusal exits 1, got {code}"
            assert err == "", f"{verb}: --json keeps stderr empty; report is stdout"
            e = json.loads(out)                    # the parse IS the assertion
            assert set(e) == ENVELOPE, f"{verb}: refusal envelope drifted: {set(e)}"
            assert e["ok"] is False and e["status"] == "error"
            assert e["root"] is None and e["data"].get("error"), \
                f"{verb}: the fact must ride under data.error"

        # -- G2: an INVALID INVOCATION (exit 2) is a plain stderr line with NO
        # envelope, even under --json -- the seam is deliberate (the verb never
        # ran) but currently unpinned, so a rebuild could emit an envelope here
        # and diverge. Pin the seam as it stands: words on stderr, exit 2.
        code, out, err = _run2(["pack", claim, "--accept", "OK", "--json"])  # no -o
        assert code == 2 and out == "" and err.startswith("ret: pack:"), \
            "an invalid invocation stays a stderr line, no envelope, exit 2"

        # -- G4: the envelope's `status` VOCABULARY per verb. surface_check pins
        # only verify->fresh and crosscheck->accept; the rest of the words
        # automation switches on are free. Pin the success spellings.
        def _status(argv: list[str]) -> str:
            code, out, _ = _run2(argv)
            assert code in (0, 1), f"{argv[0]}: envelope verb exits by predicate"
            return json.loads(out)["status"]

        assert _status(["verify", claim, "--json"]) == "fresh"
        assert _status(["audit", claim, "--json"]) == "earned"
        assert _status(["assess", claim, "--mutants", "2", "--json"]) == "measured"
        assert _status(["status", claim, "--json"]) in {"fresh", "claim"}

        # -- G3: the per-verb `data` KEY SETS the machine reads. Documented in
        # docs/cli-style.md, but docs are outside the root, so the schema is
        # unpinned below the top level. Pin the load-bearing documented keys so
        # a rebuild cannot rename `deciding` or drop `discovery`.
        def _data(argv: list[str]) -> dict:
            code, out, _ = _run2(argv)
            assert code in (0, 1)
            return json.loads(out)["data"]

        assert {"name", "root", "recomputed", "phase", "ok"} <= set(
            _data(["verify", claim, "--json"])), "verify data schema"
        assert {"name", "root", "recomputed", "elapsed", "environment",
                "layers", "gates"} <= set(_data(["audit", claim, "--json"])), \
            "audit data schema"
        assert {"measured", "not_measured", "not_applicable", "declared",
                "gate"} <= set(_data(["assess", claim, "--mutants", "2",
                                      "--json"])), "assess data schema"
        assert {"name", "root", "phase", "audited", "deciding", "proof",
                "signatures", "next"} <= set(
            _data(["status", claim, "--json"])), "status data schema"
        # G5 (naming seam) belongs here too: audit's per-gate key is `quarantine`
        # in --json but `sandbox` in the record. record's spelling is pinned by
        # spec/record.md; audit's is not. Pin it so the two names stay a
        # deliberate seam, not accidental drift.
        gates = _data(["audit", claim, "--json"]).get("gates") or []
        assert gates and "quarantine" in gates[0], \
            "audit --json names the per-gate sandbox `quarantine`"

        # -- G6 (mutation-proven): `ret run` returns the child's exit code
        # UNCHANGED. This is run's whole reason to exist -- an execution
        # boundary you can use as a CI predicate -- yet surface_check only ever
        # runs it with a passing command, so a rebuild whose run() always
        # returns 0 certifies clean and silently turns every red build green.
        ws = os.path.join(d, "ws")
        assert _run2(["init", ws, "--no-agent"])[0] == 0
        code, _, _ = _run2(["run", "exit 7", "-C", ws])
        assert code == 7, f"run must pass the child's code through, got {code}"
        code, _, _ = _run2(["run", "exit 0", "-C", ws])
        assert code == 0, "and a passing child stays 0"
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    print("proposed-surface-json-ok")
