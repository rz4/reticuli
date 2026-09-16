"""stdout carries the report; a gate's own output must never land in it.

`ret pack --json` prints a JSON report. It also runs the gate, and a gate
prints: every claim in this repository has one that says something on success,
because a check that passes silently is a check nobody trusts. Those two
streams were the same stream, so `ret pack --json | jq` failed on every real
claim and worked only on the silent toy ones used to test it.

The general rule this pins is the ordinary Unix one, which is worth having a
test for because the failure is invisible until a script depends on it: a
verb's machine-readable output goes to stdout, everything a person reads --
progress, a gate's voice, a warning -- goes to stderr.

    python3 tests/stream_check.py        (from the repository root)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A gate that is loud on both streams, which is the normal case, not an edge.
CHECK = '''import sys

print("GATE-SAYS-HELLO")
sys.stderr.write("GATE-WARNS\\n")
with open("OK", "w") as f:
    f.write("ok\\n")
'''


def _ret(*argv: str, cwd: str | None = None):
    """`ret …` as a script would call it: the two streams kept apart."""
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    return subprocess.run([sys.executable, "-m", "reticuli", *argv], check=False,
                          cwd=cwd or ROOT, env=env, capture_output=True, text=True)


def battery() -> None:
    work = tempfile.mkdtemp(prefix="stream-check-")
    try:
        claim = os.path.join(work, "loud")
        os.makedirs(claim)
        with open(os.path.join(claim, "impl.py"), "w") as f:
            f.write("def f(x):\n    return x + 1\n")
        with open(os.path.join(claim, "check.py"), "w") as f:
            f.write(CHECK)

        packed = _ret("pack", "loud", "-C", claim, "--generated", "impl.py",
                      "--input", "check.py", "--gate", f"{sys.executable} check.py",
                      "--output", "OK", "--json")
        assert packed.returncode == 0, f"the claim seals: {packed.stderr}"

        report = json.loads(packed.stdout)       # the assertion IS the parse
        assert report.get("root"), f"and the report is the whole of stdout: {report}"
        assert "GATE-SAYS-HELLO" not in packed.stdout, \
            "a gate's stdout must not be mixed into the JSON report"
        assert "GATE-SAYS-HELLO" in packed.stderr, \
            "but it must not be swallowed either -- a person still needs to read it"
        assert "GATE-WARNS" in packed.stderr, "and a gate's stderr stays stderr"

        # Every verb that offers --json must mean it, including the two that
        # were left off the list: `assess`, which is the measurement a study or
        # a CI job consumes, and `inspect`, which is the recipient's report.
        for verb, extra in (("verify", []), ("audit", []), ("inspect", []),
                            ("assess", ["--mutants", "0"])):
            result = _ret(verb, claim, *extra, "--json")
            assert result.returncode == 0, f"ret {verb}: {result.stderr}"
            try:
                parsed = json.loads(result.stdout)
            except ValueError as exc:
                raise AssertionError(
                    f"ret {verb} --json must print JSON and nothing else: "
                    f"{exc}; stdout began {result.stdout[:120]!r}") from None
            assert isinstance(parsed, dict) and parsed, f"ret {verb} --json is empty"

        # Without --json the same verbs print for a person, and must not be
        # silent: a verb that says nothing at all is its own kind of bug.
        human = _ret("audit", claim)
        assert human.returncode == 0 and human.stdout.strip(), \
            "the default rendering still speaks"

        print("stream-ok")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    battery()
