"""Authoring: a session becomes a claim.

`propose` reads a session's trace and offers a recipe; `build_claim` certifies
it COLD -- the trace has no authority, so every verdict is re-earned in a
clean workspace before anything is sealed. The claim boundary is DECLARED,
never inferred: provenance says what happened, declaration says what the
claim is.
"""
import ast
import os

from . import kernel
from . import render
from ._util import copy_into, read_json, safe_path

#: Where a session's observations live. Residue: outside every root.
TRACE = ".reticuli/draft.jsonl"

#: The format a fresh claim is born at. Guidance is outside identity here, so
#: two conforming authoring tools that word a hint differently mint one root.
DEFAULT_FORMAT = 3


def trace(ws: str) -> list:
    """The session's observations, in the order they were made."""
    import json
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
    except (OSError, UnicodeDecodeError):
        return []
    return events


def _confined(ws: str, declared: str, why: str) -> str:
    """A trace-derived path is checked BEFORE it is copied, not after.

    An escaping path refused at the seal would already have been copied out of
    the workspace on the way there.
    """
    resolved = safe_path(ws, declared)
    if resolved is None:
        raise kernel.ClaimError(
            f"{why} {declared!r} escapes the session; a claim may only name "
            f"files inside it")
    return resolved


def _entry_exists(ws: str, declared: str) -> bool:
    """Does this name match a real directory entry, case and all?

    `os.path.isfile` folds case on macOS and Windows, so the shell token `ok`
    in `printf ok > OK` tested true against the file `OK` and got pinned --
    sealing one session to different roots on different filesystems.
    """
    if safe_path(ws, declared) is None:
        return False
    parts = [p for p in declared.replace("\\", "/").split("/")
             if p not in ("", ".")]
    here = ws
    for index, part in enumerate(parts):
        try:
            entries = os.listdir(here)
        except OSError:
            return False
        if part not in entries:
            return False
        here = os.path.join(here, part)
        if index < len(parts) - 1 and not os.path.isdir(here):
            return False
    return os.path.isfile(here)


def _tokens(command: str) -> list:
    """Every word a gate command names, as written."""
    import re
    return [t for t in re.split(r"[\s'\"<>|&;()]+", command or "") if t]


def _imported(ws: str, start: str) -> list:
    """One level of ordinary Python import, followed from a decider.

    The canonical Python flow is `python3 check.py` where check.py says
    `from primes import ...`; the command never names primes.py, and coverage
    has to see it anyway.
    """
    path = safe_path(ws, start)
    if not path or not os.path.isfile(path) or not start.endswith(".py"):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    found = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module.split(".")[0]]
        for name in names:
            candidate = name + ".py"
            if candidate not in found and _entry_exists(ws, candidate):
                found.append(candidate)
    return found


def _session(ws: str, accept) -> dict:
    """What the session observed, declared, and left unresolved."""
    events = trace(ws)
    accepted = [a for a in (accept or [])]
    writes, reads, commands, meta = [], [], [], {}
    for event in events:
        kind = event.get("event")
        if kind == "write" and event.get("path"):
            _confined(ws, event["path"], "a traced write")
            if event["path"] not in writes:
                writes.append(event["path"])
        elif kind == "read" and event.get("path"):
            _confined(ws, event["path"], "a traced read")
            if event["path"] not in reads:
                reads.append(event["path"])
        elif kind == "bash" and event.get("cmd"):
            commands.append(event["cmd"])
        elif kind == "session":
            meta = dict(event)
    gate = None
    for command in commands:
        if any(a in _tokens(command) for a in accepted):
            gate = command
    if gate is None and commands:
        gate = commands[-1]
    named = set()
    for command in commands:
        for token in _tokens(command):
            if _entry_exists(ws, token):
                named.add(token)
    for decider in kernel.gate_deciders(gate or ""):
        named.add(decider)
        for reached in _imported(ws, decider):
            named.add(reached)
    present = [w for w in writes if _entry_exists(ws, w)]
    unresolved = [w for w in present
                  if w not in named and w not in accepted]
    stamps = [e["ts"] for e in events if isinstance(e.get("ts"), (int, float))]
    prompts = [e for e in events if e.get("event") == "prompt"]
    return {"events": events, "writes": writes, "present": present,
            "reads": reads, "commands": commands, "gate": gate,
            "named": sorted(named), "unresolved": unresolved,
            "accepted": accepted, "meta": meta,
            "calls": len(prompts),
            "seconds": (max(stamps) - min(stamps)) if stamps else 0.0}


def propose(ws: str, accept, name: str, claim=None, generated=None,
            claim_format: int = DEFAULT_FORMAT) -> dict:
    """Offer the recipe this session earned -- declaration, not inference."""
    session = _session(ws, accept)
    accepted = session["accepted"]
    if not accepted:
        raise kernel.ClaimError(
            "name the verdict(s) this session accepts: a claim is what its "
            "gate pins")
    if not session["gate"]:
        raise kernel.ClaimError(
            "this session ran no command, so it earned no verdict")
    claimed = [c for c in (claim or [])]
    for declared in claimed:
        _confined(ws, declared, "a declared input")
        if not _entry_exists(ws, declared):
            raise kernel.ClaimError(
                f"the declared input {declared!r} is not a file in this "
                f"session")
    forced = [g for g in (generated or [])]
    for declared in forced:
        _confined(ws, declared, "a declared output")

    produced = list(forced)
    for written in session["present"]:
        if written in claimed or written in accepted or written in produced:
            continue
        produced.append(written)

    inputs = []
    for declared in claimed:
        if declared not in inputs:
            inputs.append(declared)
    for candidate in session["reads"] + session["named"]:
        if candidate in produced or candidate in accepted \
                or candidate in inputs:
            continue
        if not _entry_exists(ws, candidate):
            continue
        inputs.append(candidate)

    hint = "guidance" if claim_format >= 3 else "request"
    table = {"name": name}
    if claim_format > 1:
        table["format"] = claim_format
    table["inputs"] = sorted(inputs)
    steps = [{"kind": "produce", "output": output, "class": "generated",
              hint: f"regenerate {output} to pass the gate"}
             for output in sorted(produced)]
    for verdict in accepted:
        steps.append({"kind": "gate", "output": verdict,
                      "class": "validated", "run": session["gate"]})
    return {"claim": table, "step": steps}


def build_claim(ws: str, accept, into: str, name: str | None = None,
                claim=None, generated=None,
                claim_format: int = DEFAULT_FORMAT) -> dict:
    """Certify a session COLD: seal, then re-earn every verdict from bytes."""
    session = _session(ws, accept)
    proposed = propose(ws, accept, name or os.path.basename(
        os.path.abspath(into)), claim=claim, generated=generated,
        claim_format=claim_format)
    vacuous = kernel.vacuous_gates(proposed)
    if vacuous:
        raise kernel.ClaimError(
            f"vacuous gate(s) {', '.join(str(v) for v in vacuous)}: every "
            f"file deciding the verdict is generated, so the root would fit "
            f"any implementation that prints ok. Declare the check with "
            f"`claim=` to make it a criterion")

    os.makedirs(into, exist_ok=True)
    with open(os.path.join(into, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.toml(proposed))
    for declared in proposed["claim"]["inputs"]:
        copy_into(_confined(ws, declared, "a declared input"),
                  os.path.join(into, declared))
    for step in proposed["step"]:
        output = step["output"]
        source = _confined(ws, output, "a declared output")
        if os.path.isfile(source):
            copy_into(source, os.path.join(into, output))

    manifest = kernel.seal(into)
    judged = kernel.audit(into)
    if not judged["ok"]:
        raise kernel.ClaimError(
            f"this session cannot be sealed: its verdict does not reproduce "
            f"cold ({judged['verdict']}; "
            f"{', '.join(g['output'] + '=' + g['status'] for g in judged['gates'])})")
    kernel.ledger(into, {"event": "oracle", "calls": session["calls"],
                         "seconds": round(session["seconds"], 6)})
    # The discovery bill rides the claim as reported testimony and is
    # SCOPE-STAMPED, so it never feeds the cost band: the first real
    # three-machine proof was rejected for exactly that, its 154k discovery
    # tokens compared against a 7.4k redo.
    from . import feedback
    discovery = feedback.session_usage(ws)
    if discovery:
        kernel.ledger(into, dict({"event": "discovery",
                                  "scope": "discovery"}, **discovery))
    return {"ok": True, "root": manifest["root"], "name": manifest["name"],
            "claim": into, "recipe": proposed,
            "gates": judged["gates"], "calls": session["calls"],
            "seconds": session["seconds"]}
