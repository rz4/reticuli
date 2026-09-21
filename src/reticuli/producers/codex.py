"""A local Codex-CLI producer for v2 claims — the un-metered rebuilder.

The openai/anthropic producers drive their own bounded tool loop against a
vendor API, and every turn is billed to that API's budget. This one drives no
loop of its own: it hands the room to the locally installed `codex` CLI
(`codex exec`), which reads the check files, writes the generated source, and
runs the gate until it passes. Codex authenticates from ~/.codex — a signed-in
ChatGPT plan, not a metered API key — so a rebuild here does NOT draw on the
OpenAI API budget the other producer hits.

Same room contract as the shipped producers: runs INSIDE the claim directory
(cwd = the room), reconstructs the files named by the recipe so the gate
passes, and returns 0 only when it does.

The producer step is not wrapped in reticuli's sandbox (that jail is for
gates), so the inherited PATH and HOME survive the scrub — codex finds its own
binary and ~/.codex auth. Codex is launched with its sandbox disabled
(`--dangerously-bypass-approvals-and-sandbox`) for two reasons: reticuli is
already the outer harness, and these self-claim gates themselves spawn
sandboxed subprocesses (surface_check runs ~50), which would die if codex
re-applied a macOS seatbelt around them — the same "sandboxes do not nest"
rule the kernel observes. This mirrors the openai producer, which runs the
gate through a plain unsandboxed subprocess.

Env: RETICULI_MODEL (passed to `codex -m` if set; else codex's own default,
e.g. gpt-5-codex), RETICULI_OUTPUT (the output this call must produce),
RETICULI_USAGE (ledger drop file), RETICULI_CODEX_TIMEOUT (wall-clock cap in
seconds, default 3600). Requires the `codex` binary on PATH.
"""
import json
import os
import shutil
import subprocess
import sys
import tomllib

CHUNK = 20000


def _fail(msg: str) -> None:
    print(f"producer_codex: {msg}", file=sys.stderr)
    sys.exit(1)


def _find_tokens(obj, best=0):
    """Best-effort scan of a codex JSON event for a running token total.

    The --json event schema drifts between codex versions, so rather than pin a
    key we walk the object and keep the largest plausible total-token number we
    see. It feeds the usage ledger only; a miss costs nothing but a blank cost.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if isinstance(v, (int, float)) and "token" in kl and (
                    "total" in kl or kl in ("tokens", "total_tokens")):
                best = max(best, int(v))
            else:
                best = _find_tokens(v, best)
    elif isinstance(obj, list):
        for v in obj:
            best = _find_tokens(v, best)
    return best


def _digest_event(line: str, state: dict) -> None:
    """Turn one --json line into a short human trace on stderr, and keep the
    token tally. Unparseable lines are printed raw — the operator still sees
    the run either way."""
    line = line.rstrip("\n")
    if not line:
        return
    try:
        ev = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        print(f"  {line[:2000]}", file=sys.stderr)
        return
    state["tokens"] = _find_tokens(ev, state.get("tokens", 0))
    kind = str(ev.get("type") or ev.get("event") or "").lower()
    # A few well-known shapes, best-effort. Anything else stays quiet but still
    # counted toward tokens above.
    text = ev.get("message") or ev.get("text") or ev.get("content")
    if "message" in kind and text:
        print(f"  · {str(text)[:500]}", file=sys.stderr)
    elif "command" in kind or "exec" in kind:
        cmd = ev.get("command") or ev.get("cmd") or ""
        if cmd:
            print(f"  $ {str(cmd)[:300]}", file=sys.stderr)
    elif "error" in kind:
        print(f"  ! {str(ev)[:500]}", file=sys.stderr)


def main() -> int:
    codex = shutil.which("codex")
    if not codex:
        _fail("the codex CLI is not on PATH (install it, or sign in with `codex login`)")

    model = os.environ.get("RETICULI_MODEL")
    out = os.environ["RETICULI_OUTPUT"]
    try:
        timeout = float(os.environ.get("RETICULI_CODEX_TIMEOUT", "3600"))
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

    argv = [codex, "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--color", "never",
            "--json",
            "-C", os.getcwd()]
    if model:
        argv += ["-m", model]
    argv.append("-")  # read the prompt from stdin

    print(f"producer_codex: launching codex exec"
          f"{' (model ' + model + ')' if model else ''} in {os.getcwd()}",
          file=sys.stderr)

    state = {"tokens": 0}
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
    except OSError as exc:
        _fail(f"cannot launch codex: {exc}")

    try:
        proc.stdin.write(task)
        proc.stdin.close()
        for line in proc.stdout:
            _digest_event(line, state)
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        _report(state["tokens"])
        _fail(f"codex exceeded the {timeout:.0f}s wall-clock cap")
    except KeyboardInterrupt:
        proc.kill()
        raise

    _report(state["tokens"])

    if rc != 0 and not claim_done():
        _fail(f"codex exited {rc} and the gate has not passed")
    if not claim_done():
        why = f"the gate never produced {gate_out}" if gate_out else "the claim is incomplete"
        _fail(f"codex finished but {why}")
    if not present(out):
        _fail(f"codex finished but did not write {out}")
    return 0


def _report(tokens: int) -> None:
    """Report cost like the API producers do. Codex bills a ChatGPT plan, not a
    per-token API line, so there is no usd figure to give — the tokens are
    recorded for comparison; the ledger notes the un-metered source."""
    upath = os.environ.get("RETICULI_USAGE")
    if not upath:
        return
    rec = {"vendor": "codex", "metered": False}
    if tokens:
        rec["tokens"] = tokens
    with open(upath, "w", encoding="utf-8") as f:
        json.dump(rec, f)


if __name__ == "__main__":
    sys.exit(main())
