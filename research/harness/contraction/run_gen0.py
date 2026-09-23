"""Generation 0: blind rebuilds via the codex producer, for any subject.

Paced and resumable — each rebuild writes to its own directory, and a rebuild
whose generated file already exists is skipped, so re-running continues where a
codex usage-window stop left off (and re-ingests without re-spending). On a
quota signal the run stops cleanly rather than hammering the window.

The generated filename is read from the claim's recipe (the produce step's
output), so the same runner works for codec.py, calc.py, or anything else.

Family is one (OpenAI/codex) on purpose for the pilot; sizes are mixed to spread
the reconstructions. Cross-family independence is a later, separate step.
"""

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

SP = Path("/private/tmp/claude-501/-Users-rzamora-Desktop-LBNL-AMSC-experiment-reticuli"
          "/118c5de8-4cd2-4b36-95d8-cd6ebf00be66/scratchpad")
VENV_PY = "/Users/rzamora/Desktop/LBNL/AMSC/experiment/reticuli/.venv/bin/python"
DEFAULT_PLAN = (["gpt-6-luna"] * 3) + (["gpt-6-sol"] * 3) + (["gpt-6-astra"] * 2)

# Positional args: <claim> <out-dir> [producer-module] [comma-separated model plan]
CLAIM = Path(sys.argv[1]) if len(sys.argv) > 1 else SP / "base64-claim"
GEN0 = Path(sys.argv[2]) if len(sys.argv) > 2 else SP / "gen0"
IMPLS = GEN0 / "impls"
PRODUCER_MODULE = sys.argv[3] if len(sys.argv) > 3 else "reticuli.producers.codex"
PRODUCER = f"{VENV_PY} -P -m {PRODUCER_MODULE}"
PLAN = sys.argv[4].split(",") if len(sys.argv) > 4 else DEFAULT_PLAN

# The generated file the producer regrows, from the claim's recipe.
with open(CLAIM / "reticuli.toml", "rb") as _f:
    GENERATED = next(s["output"] for s in tomllib.load(_f)["step"]
                     if s["kind"] == "produce")

QUOTA = re.compile(r"usage limit|rate limit|try again|quota|429", re.IGNORECASE)


def main() -> int:
    IMPLS.mkdir(parents=True, exist_ok=True)
    for idx, model in enumerate(PLAN):
        out = GEN0 / f"rebuild_{idx:02d}_{model}"
        codec = out / GENERATED
        dest = IMPLS / f"impl_{idx:02d}_{model.replace('-', '_')}.py"

        if codec.exists():
            shutil.copy(codec, dest)
            print(f"[{idx:02d}] {model}: already rebuilt, ingested", flush=True)
            continue

        print(f"[{idx:02d}] {model}: rebuilding blind...", flush=True)
        env = dict(os.environ, RETICULI_MODEL=model,
                   RETICULI_USAGE=str(GEN0 / f"rebuild_{idx:02d}.usage.json"))
        try:
            r = subprocess.run(
                ["ret", "rebuild", str(CLAIM), "--producer", PRODUCER, "-o", str(out)],
                env=env, capture_output=True, text=True, timeout=1800, check=False,
            )
        except subprocess.TimeoutExpired:
            print(f"[{idx:02d}] {model}: TIMED OUT (counts as a failed attempt)", flush=True)
            continue

        combined = (r.stdout or "") + (r.stderr or "")
        if codec.exists():
            shutil.copy(codec, dest)
            print(f"[{idx:02d}] {model}: converged -> {dest.name}", flush=True)
        elif QUOTA.search(combined):
            print(f"[{idx:02d}] {model}: QUOTA — stopping; re-run to resume.", flush=True)
            print(combined[-600:], flush=True)
            break
        else:
            print(f"[{idx:02d}] {model}: did not converge (no quota); a failed "
                  f"attempt, lowers R.", flush=True)
            print(combined[-400:], flush=True)

    done = sorted(p.name for p in IMPLS.glob("*.py"))
    print(f"\ngeneration 0: {len(done)}/{len(PLAN)} rebuilds ingested: {done}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
