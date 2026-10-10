"""A trial is a claim: seal a qualifying trial as a verifiable object.

The closure count's verdicts have lived in session transcripts and a
hand-kept ledger — judges that nothing audits. This builder closes that
loop (the instrument-recursion thesis, phase one): given a finished
lineage, it packs a TRIAL CLAIM whose

  inputs   pin the judge sources (judge_gen1.py, trial.py, this gate),
           the frozen repository root the trial ran against, and the
           lineage/run identifiers;
  gate     RE-EARNS the trial's conditions — verdicts never carry, so
           the gate runs the judges again rather than reading stored
           results: the identity full gate (substituted REPO_OK), the
           held-out battery, the bootstrap (SUCCESSION HOLDS including
           audit_repo), and the recursive step's receipt check;
  verdict  TRIAL_OK, written only if every condition re-earns.

Packing therefore succeeds only for a qualifying trial (pack refuses an
unearned gate), and the sealed claim's ROOT names the experiment: anyone
holding the repository and the lineage tree can re-earn the QUALIFYING
verdict with `ret audit` on this claim. The ledger row becomes a
pointer to a root instead of prose.

    python3 trial_claim.py --lineage codex --run r19 --expect-root <root>

The claim seals into research/harness/closure/trialclaims/<run>-<lineage>/.
Scaffolding, honestly labeled: the gate shells back into the repository
checkout it was built from (the trial is ABOUT that checkout); the claim
is reproducible on any machine holding the same checkout and lineage,
which is exactly condition 5's shape.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
from reticuli import kernel, pack  # noqa: E402

GATE = '''\
"""The trial's conditions, re-earned. Verdicts never carry."""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = json.load(open(os.path.join(HERE, "trial.json")))
REPO = spec["repo"]
VENV = os.path.join(REPO, ".venv", "bin", "python")
ENV = dict(os.environ, SUCCESSION_RUN=spec["run"], NO_COLOR="1")

def sh(argv, timeout):
    return subprocess.run(argv, cwd=REPO, env=ENV, timeout=timeout,
                          capture_output=True, text=True)

# condition: the boundary is the one the trial froze
manifest = json.load(open(os.path.join(REPO, ".reticuli", "manifest.json")))
assert manifest["root"] == spec["expect_root"], (
    "the trial's boundary moved: " + manifest["root"])

judge = os.path.join(REPO, "research", "harness", "succession", "judge_gen1.py")

# condition: held-out tests (confidence battery)
r = sh([VENV, judge, "--lineage", spec["lineage"], "--tests"], 1800)
assert r.returncode == 0 and "exit 0" in (r.stdout + r.stderr), (
    "held-out battery failed: " + (r.stdout + r.stderr)[-300:])

# condition: the bootstrap, SUCCESSION HOLDS (incl. gen-2 and audit_repo)
r = sh([VENV, judge, "--lineage", spec["lineage"], "--bootstrap"], 7200)
assert r.returncode == 0 and "SUCCESSION HOLDS" in (r.stdout + r.stderr), (
    "bootstrap did not hold: " + (r.stdout + r.stderr)[-300:])

# condition: identity — the substituted full gate re-earns REPO_OK
r = sh([VENV, judge, "--lineage", spec["lineage"], "--full-gate"], 7200)
assert r.returncode == 0 and "ok=True" in (r.stdout + r.stderr), (
    "identity full gate failed: " + (r.stdout + r.stderr)[-300:])

with open("TRIAL_OK", "w") as f:
    f.write("qualifying\\n")
print("trial-ok")
'''


def build(lineage: str, run: str, expect_root: str) -> dict:
    import json
    name = f"{run}-{lineage}"
    claim = os.path.join(HERE, "trialclaims", name)
    if os.path.exists(claim):
        shutil.rmtree(claim)
    os.makedirs(claim)
    for src in ("judge_gen1.py",):
        shutil.copyfile(os.path.join(HERE, "..", "succession", src),
                        os.path.join(claim, src))
    shutil.copyfile(os.path.join(HERE, "trial.py"),
                    os.path.join(claim, "trial_runner.py"))
    with open(os.path.join(claim, "conditions.py"), "w") as f:
        f.write(GATE)
    with open(os.path.join(claim, "trial.json"), "w") as f:
        json.dump({"run": run, "lineage": lineage,
                   "expect_root": expect_root, "repo": REPO}, f, indent=1)
    result = pack.pack(
        claim, f"trial-{name}",
        generated=[],
        inputs=["judge_gen1.py", "trial_runner.py", "conditions.py",
                "trial.json"],
        gate="python3 conditions.py", gate_output="TRIAL_OK",
        environment=None, claim_format=4)
    return {"claim": claim, "root": result["root"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lineage", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--expect-root", required=True)
    a = ap.parse_args()
    out = build(a.lineage, a.run, a.expect_root)
    print(f"trial claim sealed: {out['claim']}")
    print(f"trial root: {out['root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
