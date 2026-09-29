"""A guided-rewrite producer for the generation ladder.

The shipped producers reconstruct a claim BLIND — criteria alone. This one
exists for the opposite condition: it refuses to run without guidance
(`RETICULI_REQUEST`), because its whole job is to hand a producer the
previous generation's implementation and ask for a rewrite. The guidance
travels on the claim's format-3 channel, which the root deliberately
excludes, so a guided rewrite targets exactly the root a blind rebuild does
— and the kernel's ledger records `guidance: true` rather than pretending
the run was blind.

Dispatches on RETICULI_VENDOR: `codex` (codex exec, the OpenAI family) or
`claude` (claude -p, the Anthropic family). Same room contract as the
shipped producers: runs inside the claim directory, may write only the
generated outputs, returns 0 only when the gate has passed. Same
sandbox-disabling flags, for the same reason: reticuli is the outer
harness, and its gate jail is applied after this step, not during it.

Env: RETICULI_VENDOR, RETICULI_REQUEST (required), RETICULI_MODEL,
RETICULI_OUTPUT, RETICULI_USAGE, RETICULI_REWRITE_TIMEOUT (default 1800 s).
"""
import getpass
import json
import os
import shutil
import subprocess
import sys
import tomllib


def _fail(msg: str) -> None:
    print(f"producer_rewrite: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    vendor = os.environ.get("RETICULI_VENDOR", "")
    request = os.environ.get("RETICULI_REQUEST", "")
    if not request:
        _fail("no RETICULI_REQUEST: this producer serves guided rewrites only")
    model = os.environ.get("RETICULI_MODEL")
    out = os.environ["RETICULI_OUTPUT"]
    try:
        timeout = float(os.environ.get("RETICULI_REWRITE_TIMEOUT", "1800"))
    except ValueError:
        timeout = 1800.0

    recipe_name = "reticuli.toml" if os.path.isfile("reticuli.toml") else "claim.toml"
    with open(recipe_name, "rb") as f:
        recipe = tomllib.load(f)
    gate = next((s for s in recipe["step"] if s["kind"] == "gate"), None)
    inputs = recipe["claim"].get("inputs", [])
    own = [s["output"] for s in recipe["step"]
           if s["kind"] == "produce" and "from" not in s]
    gate_cmd = gate["run"] if gate else ""
    gate_out = gate["output"] if gate else ""

    def present(p):
        return bool(p) and os.path.isfile(p)

    def claim_done():
        return present(gate_out) if gate_out else all(present(p) for p in own)

    if present(out) and claim_done():
        return 0

    task = f"""{request}

Ground rules for this workspace: work in the current directory, standard
library only. Do NOT modify the check/input files: {inputs}. Write the
file(s): {own}. Then run the gate command:

    {gate_cmd}

It must exit 0 and create {gate_out}. Iterate — read the gate's output, fix
your files, re-run — until it passes. Then stop."""

    env = dict(os.environ)
    if vendor == "codex":
        binary = shutil.which("codex")
        if not binary:
            _fail("the codex CLI is not on PATH")
        argv = [binary, "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--color", "never",
                "-C", os.getcwd()]
        if model:
            argv += ["-m", model]
        argv.append("-")
        stdin = task
    elif vendor == "claude":
        binary = shutil.which("claude")
        if not binary:
            _fail("the claude CLI is not on PATH")
        argv = [binary, "--print", "--dangerously-skip-permissions"]
        if model:
            argv += ["--model", model]
        argv.append(task)
        stdin = None
        # headless claude needs USER/LOGNAME for its keychain login; the
        # producer env-scrub dropped them (same fix as producers/claude.py)
        who = getpass.getuser()
        env.setdefault("USER", who)
        env.setdefault("LOGNAME", who)
    else:
        _fail(f"unknown RETICULI_VENDOR {vendor!r} (want codex or claude)")

    print(f"producer_rewrite: launching {vendor}"
          f"{' (model ' + model + ')' if model else ''} in {os.getcwd()}",
          file=sys.stderr)
    try:
        proc = subprocess.run(argv, input=stdin, capture_output=True,
                              text=True, timeout=timeout, check=False, env=env)
    except subprocess.TimeoutExpired:
        _report(vendor)
        _fail(f"{vendor} exceeded the {timeout:.0f}s wall-clock cap")
    except OSError as exc:
        _fail(f"cannot launch {vendor}: {exc}")

    tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-1000:]
    if tail.strip():
        print(f"  {tail.strip()}", file=sys.stderr)
    _report(vendor)

    if proc.returncode != 0 and not claim_done():
        _fail(f"{vendor} exited {proc.returncode} and the gate has not passed")
    if not claim_done():
        _fail(f"{vendor} finished but the gate never produced {gate_out}")
    if not present(out):
        _fail(f"{vendor} finished but did not write {out}")
    return 0


def _report(vendor: str) -> None:
    upath = os.environ.get("RETICULI_USAGE")
    if not upath:
        return
    with open(upath, "w", encoding="utf-8") as f:
        json.dump({"vendor": f"{vendor}-rewrite", "metered": False}, f)


if __name__ == "__main__":
    sys.exit(main())
