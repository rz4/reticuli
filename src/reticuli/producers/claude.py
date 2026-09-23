"""A local Claude-Code producer for v2 claims — a second, un-metered family.

The sibling of producers/codex.py, for the other family. Where codex hands the
room to `codex exec`, this hands it to a fresh headless Claude Code session
(`claude -p`), which reads the check files, writes the generated source, and
runs the gate until it passes. Claude Code authenticates from the signed-in CLI
(a Claude subscription, not a metered API key), so a rebuild here does NOT draw
on the Anthropic API budget the anthropic producer hits.

Its point in the experiment is independence: codex is the OpenAI family, this is
the Anthropic family. A cross-family rebuild is the control for producer
dependence — whether an agreement between reconstructions comes from the
boundary or from a prior the producers happen to share.

Same room contract as the shipped producers: runs INSIDE the claim directory
(cwd = the room), reconstructs the files named by the recipe so the gate passes,
returns 0 only when it does. The session is BLIND — its working directory is the
room, which holds only the check and inputs, never the reference implementation.
It is a *fresh* session with no access to any conversation that has seen the
answer.

The producer step is not wrapped in reticuli's sandbox (that jail is for gates),
so inherited PATH and HOME survive the scrub — claude finds its own binary and
auth. It is launched with --dangerously-skip-permissions so it can write and run
the gate without interactive prompts, for the same reason codex disables its
sandbox: reticuli is already the outer harness, and the self-claim gates spawn
their own sandboxed subprocesses.

Env: RETICULI_MODEL (passed to `claude --model` if set; else the CLI default),
RETICULI_OUTPUT (the output this call must produce), RETICULI_USAGE (ledger drop
file), RETICULI_CLAUDE_TIMEOUT (wall-clock cap in seconds, default 3600).
Requires the `claude` binary on PATH.
"""
import getpass
import json
import os
import shutil
import subprocess
import sys
import tomllib


def _fail(msg: str) -> None:
    print(f"producer_claude: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    claude = shutil.which("claude")
    if not claude:
        _fail("the claude CLI is not on PATH (install Claude Code, or sign in)")

    model = os.environ.get("RETICULI_MODEL")
    out = os.environ["RETICULI_OUTPUT"]
    try:
        timeout = float(os.environ.get("RETICULI_CLAUDE_TIMEOUT", "3600"))
    except ValueError:
        timeout = 3600.0

    recipe_name = "reticuli.toml" if os.path.isfile("reticuli.toml") else "claim.toml"
    with open(recipe_name, "rb") as f:
        recipe = tomllib.load(f)
    gate = next((s for s in recipe["step"] if s["kind"] == "gate"), None)
    inputs = recipe["claim"].get("inputs", [])
    supplied = [s["output"] for s in recipe["step"]
                if s["kind"] == "produce" and "from" in s]
    own = [s["output"] for s in recipe["step"]
           if s["kind"] == "produce" and "from" not in s]
    gate_cmd = gate["run"] if gate else ""
    gate_out = gate["output"] if gate else ""

    def present(p):
        return bool(p) and os.path.isfile(p)

    def claim_done():
        return present(gate_out) if gate_out else bool(own) and all(present(p) for p in own)

    if present(out) and claim_done():
        return 0

    task = f"""You are reconstructing the source files of a content-addressed claim so its \
check passes. There is NO reference implementation — infer the required API and semantics \
from the check files ALONE.

Work in the current directory. Use your file tools to read and write, and your shell to run \
the gate. Do these steps:

1. Read the check/input files IN FULL first (they are already present, do NOT modify them): \
{inputs}
   A check may be longer than it first appears — read the ENTIRE file. Its header docstrings \
specify exact byte-level serializations you must reproduce.
2. Read (do NOT modify) the files supplied by lower layers; import from them: {supplied}
3. Create these files, standard library only, correct over clever: {own}
4. Run the gate command:  {gate_cmd}
   It must exit 0 and create:  {gate_out}
5. Iterate — read the gate's output, fix your files, re-run — until the gate exits 0. Then stop.

Never modify the check/input files. When the gate passes, you are done."""

    argv = [claude, "--print", "--dangerously-skip-permissions"]
    if model:
        argv += ["--model", model]
    argv.append(task)

    # reticuli's producer env-scrub keeps only PATH/HOME/TMPDIR/LANG/LC_ALL/TZ,
    # but headless Claude needs USER/LOGNAME to read its Keychain login (without
    # them it reports "Not logged in"). Reconstruct them from the OS password
    # database, which getpass falls back to when the env vars are absent. The
    # scrub already dropped ANTHROPIC_API_KEY, so Claude uses the subscription,
    # not a metered key.
    env = dict(os.environ)
    who = getpass.getuser()
    env.setdefault("USER", who)
    env.setdefault("LOGNAME", who)

    print(f"producer_claude: launching claude -p"
          f"{' (model ' + model + ')' if model else ''} in {os.getcwd()}",
          file=sys.stderr)

    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, check=False, env=env)
    except subprocess.TimeoutExpired:
        _report()
        _fail(f"claude exceeded the {timeout:.0f}s wall-clock cap")
    except OSError as exc:
        _fail(f"cannot launch claude: {exc}")

    tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-1000:]
    if tail.strip():
        print(f"  {tail.strip()}", file=sys.stderr)
    _report()

    if proc.returncode != 0 and not claim_done():
        _fail(f"claude exited {proc.returncode} and the gate has not passed")
    if not claim_done():
        why = f"the gate never produced {gate_out}" if gate_out else "the claim is incomplete"
        _fail(f"claude finished but {why}")
    if not present(out):
        _fail(f"claude finished but did not write {out}")
    return 0


def _report() -> None:
    """Record the source for comparison. Claude Code bills a subscription, not a
    per-token API line, so there is no usd figure — the ledger notes the
    un-metered family."""
    upath = os.environ.get("RETICULI_USAGE")
    if not upath:
        return
    with open(upath, "w", encoding="utf-8") as f:
        json.dump({"vendor": "claude-code", "metered": False}, f)


if __name__ == "__main__":
    sys.exit(main())
