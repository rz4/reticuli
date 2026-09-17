"""The conformance runner: point any implementation at the vectors.

    python3 spec/vectors/run.py --root "<command>"
    python3 spec/vectors/run.py --root "<command>" --digest "<command>"

Each command is a shell string; the runner appends one argument, the vector
directory, and reads the LAST 64-character lowercase-hex token on stdout as
the answer. A vector passes when the answer equals the directory's
`expected-root` (and, with --digest given, `expected-build-digest`). Exit 0
means every vector passed; the failures are listed either way.

Examples, using the two implementations this repository ships:

    python3 spec/vectors/run.py \\
        --root "PYTHONPATH=src python3 -m reticuli.reference root"

An implementation in any language conforms to spec/identity.md exactly when
it reproduces every expected value here. Stdlib only.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HEX = re.compile(r"\b[0-9a-f]{64}\b")


def answer(command: str, vector: str):
    """The implementation's hex answer for one vector, or an error string."""
    done = subprocess.run(f"{command} {vector}", shell=True,
                          capture_output=True, text=True, timeout=120,
                          check=False)
    if done.returncode != 0:
        return None, (done.stderr or done.stdout).strip()[-200:] or "nonzero exit"
    found = HEX.findall(done.stdout)
    if not found:
        return None, "no 64-hex token on stdout"
    return found[-1], None


def expected(vector: str, name: str):
    path = os.path.join(vector, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="reticuli identity conformance")
    ap.add_argument("--root", required=True, metavar="COMMAND",
                    help="command computing a claim directory's root")
    ap.add_argument("--digest", default=None, metavar="COMMAND",
                    help="command computing a claim directory's build digest")
    args = ap.parse_args()

    vectors = sorted(d for d in os.listdir(HERE)
                     if os.path.isfile(os.path.join(HERE, d, "expected-root")))
    checks, failures = 0, []
    for name in vectors:
        vector = os.path.join(HERE, name)
        jobs = [("root", args.root, expected(vector, "expected-root"))]
        if args.digest:
            want = expected(vector, "expected-build-digest")
            if want:
                jobs.append(("digest", args.digest, want))
        for kind, command, want in jobs:
            checks += 1
            got, why = answer(command, vector)
            if got == want:
                print(f"ok    {name} {kind}")
            else:
                failures.append(name)
                print(f"FAIL  {name} {kind}: want {want[:16]}…, "
                      f"got {(got or why)[:60]}")
    print(f"\n{checks - len(failures)}/{checks} conformant"
          + ("" if not failures else f" — nonconformant: {sorted(set(failures))}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
