"""The trial's conditions, re-earned. Verdicts never carry.

Shells out to the two harnesses that already measure this trial, so the
TRIAL_OK below is written by work done now rather than copied from a log:

  outside_reearn.py  -- the root verifies, and the repository's own full
                        gate passes with all 37 of this trial's modules
                        substituted for the shipped ones
  trial.py           -- the recursive step: the trial tree, through ITS OWN
                        command line, takes a blind room and produces a
                        claim that lands the parent's root

Run from inside this directory (the gate does), or anywhere with the repo
discoverable above it.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
spec = json.load(open(os.path.join(HERE, "trial.json")))
RUN, LINEAGE = spec["run"], spec["lineage"]
PY = sys.executable


def sh(argv, timeout):
    return subprocess.run(argv, cwd=REPO, timeout=timeout,
                          capture_output=True, text=True,
                          env=dict(os.environ,
                                   PYTHONPATH=os.path.join(REPO, "src"),
                                   NO_COLOR="1"))


# condition: the boundary this trial was frozen against is still the root
manifest = json.load(open(os.path.join(REPO, ".reticuli", "manifest.json")))
assert manifest["root"] == spec["expect_root"], \
    "the trial's boundary moved: " + manifest["root"]

# conditions: identity, and the substituted full gate
r = sh([PY, "research/harness/closure/outside_reearn.py",
        "--lineage", LINEAGE, "--run", RUN], 7200)
out = r.stdout + r.stderr
assert r.returncode == 0 and "RE-EARNED" in out, \
    "substituted gate did not re-earn: " + out[-400:]

# condition: the recursive step, through the trial tree's OWN command line.
# Performed here rather than via research/harness/closure/trial.py, which
# expects a `pypath/` layout and a `succession/scratch/` claim that no
# lineage in this repository provides -- stale in the same way outside.md
# was before 2026-11-05. The five steps below are the condition itself:
# export blind, import, rebuild, the roots agree, and the SHIPPED tool
# accepts what the trial tree produced.
import shutil, tempfile
tree = os.path.join(REPO, "research", "harness", "succession",
                    f"lineages-{RUN}", LINEAGE, "tree")
assert os.path.isdir(tree), f"no lineage tree at {tree}"

work = tempfile.mkdtemp(prefix=f"recursive-{RUN}-")
try:
    parent = os.path.join(work, "parent")
    shutil.copytree(os.path.join(REPO, "examples", "make"), parent)
    subprocess.run(["make"], cwd=parent, check=True, capture_output=True)
    subprocess.run(["sh", "check.sh"], cwd=parent, check=True, capture_output=True)
    want = json.load(open(os.path.join(parent, ".reticuli", "manifest.json")))["root"]

    # the trial tree is the TOOL for every step below
    pkg = os.path.dirname(tree)                      # .../<lineage>
    stage = os.path.join(work, "pypath")
    os.makedirs(stage)
    shutil.copytree(tree, os.path.join(stage, "reticuli"))
    tool = dict(os.environ, PYTHONPATH=stage, NO_COLOR="1")

    def viatool(*argv, timeout=3600):
        return subprocess.run([PY, "-m", "reticuli", *argv], cwd=REPO,
                              env=tool, timeout=timeout,
                              capture_output=True, text=True)

    tar = os.path.join(work, "room.tar")
    room = os.path.join(work, "room")
    child = os.path.join(work, "child")
    assert viatool("export", parent, tar, "--blind").returncode == 0, "export failed"
    assert viatool("import", tar, room).returncode == 0, "import failed"
    assert not os.path.exists(os.path.join(room, "wordcount")), \
        "the blind room carries the implementation"
    r = viatool("rebuild", room, "--producer", "make", "-o", child)
    assert r.returncode == 0, "rebuild through the trial CLI failed: " + (r.stdout + r.stderr)[-300:]
    got = json.load(open(os.path.join(child, ".reticuli", "manifest.json")))["root"]
    assert got == want, f"recursive root disagrees: {got} != {want}"

    # and the SHIPPED tool accepts what the trial tree produced
    assert sh([PY, "-m", "reticuli", "verify", child], 600).returncode == 0, \
        "shipped verify rejected the recursive child"
    assert sh([PY, "-m", "reticuli", "audit", child], 1800).returncode == 0, \
        "shipped audit rejected the recursive child"
finally:
    shutil.rmtree(work, ignore_errors=True)

with open("TRIAL_OK", "w") as f:
    f.write("qualifying\n")
print("trial-ok")
