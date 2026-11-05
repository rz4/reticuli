"""Sessions become claims.

A session leaves a trace: prompts, writes, reads, and the commands that were
run. `propose` reads one and says what claim it implies -- which files look
like the implementation, which look like the criteria, and which command is
the gate. `build_claim` then CERTIFIES that proposal COLD: it lays the
declared content into a clean room, re-runs every gate there, and requires
the pinned verdict to reproduce byte for byte. The trace has no authority;
it is a hypothesis the room either confirms or refuses.

Two rules the measured failures taught:

IDENTITY MUST NOT FOLLOW THE FILESYSTEM. A candidate name is kept only when
it matches a real directory entry exactly, case included. Testing with
`os.path.isfile` folds case on macOS and Windows, which once sealed one
session to different roots on different hosts.

THE CLAIM BOUNDARY IS DECLARED, NOT INFERRED. If the only thing deciding a
gate is a file the session also generated, the verdict depends on no claim
at all: such a gate is VACUOUS and is refused. Declaring the check (`claim=`)
is what makes it a criterion -- provenance never decides class.
"""
import json
import os
import shutil

from . import _util
from . import kernel
from . import render

TRACE = ".reticuli/draft.jsonl"


# -- the trace -------------------------------------------------------------
def events(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    found = []
    if not os.path.isfile(path):
        return found
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                found.append(parsed)
    return found


def _confine(ws: str, declared: str) -> str:
    """A trace-derived path is confined BEFORE anything is copied.

    A traced read of `../secret` is an input that escapes the session: it
    must be refused at the boundary, not copied out of the workspace on the
    way to a seal that would have refused it anyway.
    """
    try:
        return _util.safe_path(ws, declared)
    except ValueError as exc:
        raise kernel.ClaimError(
            f"a trace-derived path escapes the session: {declared!r} "
            f"({exc})") from None


def _real_entry(ws: str, declared: str) -> bool:
    """Does this name match a real directory entry, exactly?

    `printf ok > OK` makes `ok` a candidate, and on a case-insensitive
    filesystem it tests true against the file `OK`. Pinning it would seal
    the same session to different roots on different hosts, and name an
    input a case-sensitive host cannot find at all.
    """
    if not declared or os.path.isabs(declared) or ".." in declared.split("/"):
        return False
    here = ws
    pieces = declared.split("/")
    for piece in pieces[:-1]:
        try:
            if piece not in os.listdir(here):
                return False
        except OSError:
            return False
        here = os.path.join(here, piece)
    try:
        return pieces[-1] in os.listdir(here)
    except OSError:
        return False


def _tokens(command: str) -> list:
    import shlex
    try:
        return shlex.split(command or "")
    except ValueError:
        return (command or "").split()


def _redirect_targets(command: str) -> list:
    """What a command writes by redirection -- a gate's verdict, usually."""
    out, words = [], _tokens(command)
    for index, word in enumerate(words):
        if word in (">", ">>") and index + 1 < len(words):
            out.append(words[index + 1])
        elif word.startswith(">") and len(word) > 1 and \
                not word.startswith(">>"):
            out.append(word[1:])
        elif word.startswith(">>") and len(word) > 2:
            out.append(word[2:])
    return out


def _imported_by(ws: str, script: str) -> list:
    """One level of import: the canonical Python shape is `python3 check.py`
    where check.py says `from primes import ...`, and coverage must see
    through exactly that."""
    import ast
    path = os.path.join(ws, script)
    if not script.endswith(".py") or not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    reached = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and \
                node.level == 0:
            names = [node.module]
        for name in names:
            candidate = name.split(".")[0] + ".py"
            if _real_entry(ws, candidate):
                reached.append(candidate)
    return reached


def observations(ws: str) -> dict:
    """What the session was observed to do, per path."""
    seen = {}
    for event in events(ws):
        kind = event.get("event")
        if kind not in ("write", "read"):
            continue
        path = event.get("path")
        if not path:
            continue
        _confine(ws, path)
        seen.setdefault(path, {"observed": kind,
                               "evidence": event.get("via") or "hook"})
        if kind == "write":
            seen[path]["observed"] = "write"
    return seen


def gate_commands(ws: str) -> list:
    return [event.get("cmd") for event in events(ws)
            if event.get("event") == "bash" and event.get("cmd")]


def session_span(ws: str) -> tuple:
    """How many oracle turns the session took, and how long it ran."""
    stamps = [float(e["ts"]) for e in events(ws)
              if isinstance(e.get("ts"), (int, float))]
    prompts = sum(1 for e in events(ws) if e.get("event") == "prompt")
    span = (max(stamps) - min(stamps)) if len(stamps) > 1 else 0.0
    return prompts, span


def discovery_bill(ws: str) -> dict:
    """What FINDING the answer cost, priced from the harness's own usage
    records over this session's window.

    Testimony, stamped as such: tokens always, money only where the harness
    reported one, because a price table would drift. It is reported beside
    the band and never inside it -- a 154k-token discovery session must not
    reject a one-call redo.
    """
    transcripts = [e.get("transcript") for e in events(ws)
                   if e.get("event") == "session" and e.get("transcript")]
    tokens, usd, calls = 0, 0.0, 0
    for path in transcripts:
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = ((entry.get("message") or {}).get("usage")
                         if isinstance(entry.get("message"), dict) else None)
                if not isinstance(usage, dict):
                    continue
                calls += 1
                for key in ("input_tokens", "output_tokens",
                            "cache_read_input_tokens"):
                    value = usage.get(key)
                    if isinstance(value, (int, float)) and \
                            not isinstance(value, bool):
                        tokens += value
                for key in ("usd", "cost_usd", "total_cost_usd"):
                    value = entry.get(key) or usage.get(key)
                    if isinstance(value, (int, float)) and \
                            not isinstance(value, bool):
                        usd += value
    bill = {}
    if tokens:
        bill["tokens"] = tokens
    if calls:
        bill["calls"] = calls
    if usd:
        bill["usd"] = usd
    return bill


# -- the proposal ----------------------------------------------------------
def propose(ws: str, accept, name: str | None = None, claim=None,
            generated=None, claim_format: int = 3) -> dict:
    """What claim this session implies. A hypothesis, not a verdict."""
    accepted = list(accept or [])
    claimed = list(claim or [])
    declared_generated = list(generated or [])
    seen = observations(ws)
    commands = gate_commands(ws)
    if not commands:
        raise kernel.ClaimError(
            "this session ran no command, so it declares no acceptance "
            "criteria: there is nothing to seal")
    command = commands[-1]

    produced, inputs = [], []
    for path, fact in sorted(seen.items()):
        if path in accepted or path in claimed:
            continue
        if fact["observed"] == "write":
            # a traced write whose file was later DELETED is not an output
            # this claim has: declaring it would ask every rebuilder to
            # produce a file the original does not carry either.
            if _real_entry(ws, path):
                produced.append(path)
        elif _real_entry(ws, path):
            inputs.append(path)
    for path in declared_generated:
        if path not in produced:
            produced.append(path)
    for path in claimed:
        _confine(ws, path)
        if path not in inputs:
            inputs.append(path)
    verdicts = set(_redirect_targets(command)) | set(accepted)
    for token in _tokens(command):
        if token in accepted or token in verdicts or token in produced \
                or token in inputs:
            continue
        if _real_entry(ws, token):
            inputs.append(token)

    recipe = {"claim": {"name": name or os.path.basename(
        os.path.abspath(ws)), "inputs": sorted(set(inputs))}}
    if claim_format and claim_format > 1:
        recipe["claim"]["format"] = claim_format
    steps = []
    hint = "guidance" if (claim_format or 1) >= 3 else "request"
    for path in sorted(set(produced)):
        steps.append({"kind": "produce", "output": path,
                      "class": "generated",
                      hint: f"regenerate {path} to pass the gate"})
    for output in accepted:
        steps.append({"kind": "gate", "output": output,
                      "class": "validated", "run": command})
    recipe["step"] = steps
    return recipe


# -- certification ---------------------------------------------------------
def build_claim(ws: str, accept, into: str, name: str | None = None,
                claim=None, generated=None, claim_format: int = 3) -> dict:
    """Certify a session's proposal COLD, then seal it.

    Nothing is taken on the trace's word: the declared content is laid into
    a clean room, every gate is re-run there, and each accepted output must
    reproduce the bytes the session earned. A verdict the room cannot
    re-earn forms no claim.
    """
    recipe = propose(ws, accept, name=name, claim=claim,
                     generated=generated, claim_format=claim_format)
    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"the gate {vacuous[0]!r} is vacuous: every file deciding it is "
            f"one this session generated, so the verdict depends on no "
            f"claim at all. Declare the check as a criterion (claim=) to "
            f"make it one")

    if os.path.exists(into) and os.listdir(into):
        shutil.rmtree(into)
    os.makedirs(into, exist_ok=True)
    with open(os.path.join(into, kernel.RECIPE), "w",
              encoding="utf-8") as handle:
        handle.write(render.dump_recipe(recipe))
    for declared in recipe["claim"]["inputs"]:
        _util.copy_into(_confine(ws, declared),
                        _util.safe_path(into, declared))
    for step in recipe["step"]:
        if step["kind"] != "produce":
            continue
        source = _confine(ws, step["output"])
        if os.path.isfile(source):
            _util.copy_into(source, _util.safe_path(into, step["output"]))

    parsed = kernel.load_recipe(into)
    for gate in kernel.gates(parsed):
        outcome = kernel.run_gate(gate["run"], into, parsed)
        if outcome["status"] != "ok":
            raise kernel.ClaimError(
                f"the gate {gate['output']!r} does not re-earn its verdict "
                f"cold ({outcome['status']}): "
                f"{(outcome['stderr'] or outcome['stdout'])[-300:]}")
        warm = os.path.join(ws, gate["output"])
        cold = os.path.join(into, gate["output"])
        if not os.path.isfile(cold):
            raise kernel.ClaimError(
                f"the gate {gate['output']!r} wrote no verdict in a clean "
                f"room")
        if os.path.isfile(warm) and \
                _util.hash_file(warm) != _util.hash_file(cold):
            raise kernel.ClaimError(
                f"the verdict {gate['output']!r} does not reproduce: the "
                f"session earned different bytes than a clean room does, so "
                f"no claim forms from it")

    manifest = kernel.seal(into)
    calls, span = session_span(ws)
    kernel.ledger(into, {"event": "oracle", "calls": max(calls, 1),
                         "seconds": span, "scope": "session"})
    bill = discovery_bill(ws)
    if bill:
        kernel.ledger(into, dict({"event": "discovery",
                                  "scope": "discovery"}, **bill))
    return {"ok": True, "root": manifest["root"], "name": manifest["name"],
            "path": into, "inputs": recipe["claim"]["inputs"],
            "generated": [s["output"] for s in recipe["step"]
                          if s["kind"] == "produce"]}
