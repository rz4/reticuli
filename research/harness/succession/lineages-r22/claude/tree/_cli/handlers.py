"""CLI handlers: session setup, a traced run, and producer preflight.

`init` marks a directory as a reticuli session -- it creates the
`.reticuli/` store and, unless `no_agent`, wires the coding-agent hook
into `.claude/settings.json` so a session's prompts and tool use get
traced automatically. `run` executes one shell command inside a
session, tracing it to the session's draft trace, and returns the
child's exit code unchanged -- so a session can chain it as a
predicate (`run "pytest" && seal`). A command that names a known
producer (`_PRODUCERS`) is expanded to that producer's own command
line by `_expand_producer`, which preflights the producer's credential
through `_ensure` first -- refusing before a caller spends anything
running a producer that cannot possibly authenticate.
"""
import json
import os
import subprocess
import time

STORE = ".reticuli"
TRACE = ".reticuli/draft.jsonl"
SESSION_FILE = ".reticuli/session.json"

HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")
HOOK_COMMAND = "python3 -m reticuli.hooks"

VERSION = "2.0"

_ENV_ALLOW = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ")

# Named producers: a short name expands to its own command line, gated
# on the credential it needs to spend anything.
_PRODUCERS = {
    "claude": {"command": "claude -p --output-format json", "credential": "ANTHROPIC_API_KEY"},
    "codex": {"command": "codex exec --json", "credential": "OPENAI_API_KEY"},
}

# Forwarded into a producer's own environment past the credential it
# already needs: where to reach it, what it may spend, how long it may run.
_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')


def _version_line() -> str:
    """The one-line version stamp recorded into a fresh session."""
    return f"reticuli {VERSION}"


def _ensure(name: str) -> None:
    """Preflight a named producer's credential: refuse up front rather
    than let a caller spend anything running a producer that cannot
    possibly authenticate. A name that is not a known producer is not
    this function's business -- it is a no-op."""
    spec = _PRODUCERS.get(name)
    if spec is None:
        return
    credential = spec.get("credential")
    if credential and not os.environ.get(credential):
        raise RuntimeError(f"producer {name!r} needs {credential} set")


def _expand_producer(name_or_cmd: str) -> str:
    """A named producer's own command line, after `_ensure` has
    preflighted its credential; any other string passes through
    unchanged as a literal shell command."""
    spec = _PRODUCERS.get(name_or_cmd)
    if spec is None:
        return name_or_cmd
    _ensure(name_or_cmd)
    return spec["command"]


def _scan_workspace(ws: str) -> dict:
    """What already exists under `ws`: whether it is already a
    session, and the names of any claims already sealed into it --
    read, never acted on, so `init` stays idempotent and a caller can
    tell a fresh workspace from one it is walking back into."""
    store = os.path.join(ws, STORE)
    sealed = os.path.join(store, "sealed")
    return {
        "initialized": os.path.isdir(store),
        "claims": sorted(os.listdir(sealed)) if os.path.isdir(sealed) else [],
    }


def _write_json(path: str, doc: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, sort_keys=True)
    os.replace(tmp, path)


def _wire_agent(ws: str) -> list:
    """Add the coding-agent hook to `ws`'s `.claude/settings.json`, one
    entry per event in `HOOK_EVENTS` not already wired -- idempotent,
    and every other key already in the file survives untouched."""
    settings_path = os.path.join(ws, ".claude", "settings.json")
    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_block = settings.setdefault("hooks", {})
    wired = []
    for name in HOOK_EVENTS:
        entries = hooks_block.setdefault(name, [])
        already = any(h.get("type") == "command" and h.get("command") == HOOK_COMMAND
                      for group in entries for h in group.get("hooks", []))
        if not already:
            entries.append({"matcher": "", "hooks": [{"type": "command", "command": HOOK_COMMAND}]})
            wired.append(name)

    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    return wired


def init(ws: str, *, no_agent: bool = False) -> dict:
    """Mark `ws` as a reticuli session: create its `.reticuli/` store
    and, unless `no_agent`, wire the coding-agent hook so the session's
    prompts and tool use get traced automatically. Idempotent -- a
    second call touches nothing that already exists."""
    scan = _scan_workspace(ws)
    os.makedirs(os.path.join(ws, STORE), exist_ok=True)
    wired = _wire_agent(ws) if not no_agent else []
    _write_json(os.path.join(ws, SESSION_FILE),
                {"version": _version_line(), "agent": not no_agent})
    return {"path": ws, "agent": not no_agent, "wired": wired, **scan}


def _producer_env(cmd: str) -> dict:
    """The environment a traced run executes with: the host's own
    environment, confirmed to carry forward the small allowlist a
    sandboxed host might otherwise have dropped, plus -- for a named
    producer -- the credential and passthrough it needs to spend
    anything at all."""
    env = dict(os.environ)
    for k in _ENV_ALLOW:
        if k in os.environ:
            env[k] = os.environ[k]
    spec = _PRODUCERS.get(cmd)
    if spec is not None:
        credential = spec.get("credential")
        for k in (credential,) + _PRODUCER_PASSTHROUGH if credential else _PRODUCER_PASSTHROUGH:
            if k in os.environ:
                env[k] = os.environ[k]
    return env


def _trace(ws: str, record: dict) -> None:
    if not os.path.isdir(os.path.join(ws, STORE)):
        return
    path = os.path.join(ws, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def run(cmd: str, ws: str) -> int:
    """Run `cmd` inside session `ws`: expand a named producer first
    (`_expand_producer`), execute the result as one shell command with
    `ws` as its cwd, trace the attempt, and return the child's exit
    code unchanged -- so a session can use `run` as a predicate."""
    expanded = _expand_producer(cmd)
    when = time.time()
    result = subprocess.run(expanded, shell=True, cwd=ws, env=_producer_env(cmd))
    _trace(ws, {"event": "run", "cmd": cmd, "exit": result.returncode, "when": when})
    return result.returncode
