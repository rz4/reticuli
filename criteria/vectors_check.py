"""The conformance vectors hold — against both implementations, and the
runner has teeth.

spec/vectors/ is the identity computation's interchange test: any
implementation, in any language, conforms exactly when it reproduces every
expected value there. This criterion keeps the vectors true from the inside:
every vector's expected root is what BOTH shipped implementations compute
(two implementations, one answer — the cross-check the identity has), every
expected build digest is what the kernel computes, the runner passes a
conformant implementation, and a tampered vector fails it. A vector that
drifted from the implementations, or a runner that blesses anything, would
make the published conformance test worse than none.

    python3 criteria/vectors_check.py        (from the repository root)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from reticuli import kernel, reference

VECTORS = os.path.join(ROOT, "spec", "vectors")


def _expected(vector: str, name: str):
    path = os.path.join(vector, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def battery() -> None:
    names = sorted(d for d in os.listdir(VECTORS)
                   if os.path.isfile(os.path.join(VECTORS, d, "expected-root")))
    assert len(names) >= 15, f"the vector set shrank: {names}"

    for name in names:
        vector = os.path.join(VECTORS, name)
        want_root = _expected(vector, "expected-root")
        k = kernel.root(kernel.load_recipe(vector), vector)
        r = reference.root(vector)
        assert k == r == want_root, (
            f"{name}: the vector, the kernel, and the reference must agree "
            f"on one root — kernel {k[:16]}…, reference {r[:16]}…, "
            f"expected {want_root[:16]}…")
        want_bd = _expected(vector, "expected-build-digest")
        if want_bd:
            got = kernel.build_digest(vector)
            assert got == want_bd, f"{name}: build digest {got[:16]}… drifted"

    # the canonical-name vector is the two-name rule's tooth: same content,
    # same root as v1-minimal, under the name a legacy-only reader refuses
    assert _expected(os.path.join(VECTORS, "v7-canonical-name"), "expected-root") \
        == _expected(os.path.join(VECTORS, "v1-minimal"), "expected-root"), \
        "the recipe's filename must be outside the preimage"

    # the runner passes a conformant implementation end to end
    root_cmd = f"PYTHONPATH={SRC} {sys.executable} -m reticuli.reference root"
    done = subprocess.run(
        [sys.executable, os.path.join(VECTORS, "run.py"), "--root", root_cmd],
        capture_output=True, text=True, check=False)
    assert done.returncode == 0, f"the runner must pass the reference:\n" \
        f"{(done.stdout + done.stderr)[-600:]}"

    # and it has TEETH: a tampered vector must fail, or the published
    # conformance test blesses anything that prints hex
    scratch = tempfile.mkdtemp(prefix="vectors-")
    try:
        copy = os.path.join(scratch, "vectors")
        shutil.copytree(VECTORS, copy)
        with open(os.path.join(copy, "v2-one-input", "spec.txt"), "a") as f:
            f.write("tampered\n")
        done = subprocess.run(
            [sys.executable, os.path.join(copy, "run.py"), "--root", root_cmd],
            capture_output=True, text=True, check=False)
        assert done.returncode != 0 and "v2-one-input" in done.stdout, \
            "the runner must fail a tampered vector, and name it"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print(f"vectors-ok ({len(names)} vectors, two implementations, one answer)")


if __name__ == "__main__":
    battery()
