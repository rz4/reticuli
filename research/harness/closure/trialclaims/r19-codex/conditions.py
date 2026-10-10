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
    f.write("qualifying\n")
print("trial-ok")
