"""Sessions become claims: propose a boundary, then certify it cold.

A session leaves a TRACE — what was written, what was read, what was run.
The trace has **no authority**.  It is a record of what was OBSERVED, and a
claim's boundary is DECLARED: provenance never decides a step's class, or the
README flow (the agent writes both the solver and its test) would seal a
vacuous check at the same root as the real thing.  So `propose` reads the
trace into a candidate recipe and `build_claim` holds that candidate to the
only standard that matters — the gates must re-earn their verdicts COLD, in a
clean workspace, on bytes nobody carried in.

Two refusals here were measured rather than imagined.  A candidate input must
match a real directory entry EXACTLY, case included: `printf ok > OK` makes
the shell token `ok` a candidate, and on a case-folding filesystem it tests
true against the file `OK` — so the same session sealed to different roots on
different hosts, and the macOS-sealed claim named an input a case-sensitive
host could not find.  And a trace-derived path is confined BEFORE anything is
copied, or an escaping read is carried out of the workspace on its way to the
seal that refuses it.
"""
import json
import os
import shutil
import tempfile

from . import _util, kernel, render

#: A session's observation trace.
TRACE = ".reticuli/draft.jsonl"


def _events(workspace: str) -> list:
    path = os.path.join(workspace, TRACE)
    if not os.path.isfile(path):
        return []
    out = []
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
                    out.append(event)
    except (OSError, UnicodeDecodeError):
        return out
    return out


def _entry(workspace: str, name: str) -> bool:
    """Does this name match a real directory entry, case and all?

    `os.path.isfile` folds case on macOS and Windows, so it is not usable
    here: identity may depend only on bytes and on declarations, never on
    what a particular host's filesystem is willing to resolve.
    """
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts:
        return False
    here = workspace
    for part in parts:
        try:
            if part not in os.listdir(here):
                return False
        except OSError:
            return False
        here = os.path.join(here, part)
    return os.path.isfile(here)


def _tokens(command: str) -> list:
    import shlex
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _imports(workspace: str, script: str) -> list:
    """What a decider script imports from beside it — one level.

    The canonical Python shape reaches the implementation through an import
    the gate command never names: `python3 check.py` where check.py says
    `from primes import ...`.  Coverage has to see through that, or the
    canonical flow reports an uncovered file for no reason.
    """
    import ast
    path = os.path.join(workspace, script)
    if not script.endswith(".py") or not os.path.isfile(path):
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
        elif isinstance(node, ast.ImportFrom) and node.module and \
                node.level == 0:
            names = [node.module.split(".")[0]]
        for name in names:
            candidate = name + ".py"
            if _entry(workspace, candidate):
                found.append(candidate)
    return found


def _gate_for(commands: list, output: str):
    """The traced command that earns one accepted output."""
    for command in reversed(commands):
        if output in command:
            return command
    return commands[-1] if commands else None


def _session_cost(workspace: str, events: list) -> dict:
    """What the session cost, read from the harness's own usage records.

    Testimony, stamped as such.  Tokens always, usd only when the harness
    reported one: a price table maintained here would drift, and a wrong
    price is worse than an absent one.  The discovery bill is reported
    BESIDE the cost band and never inside it — the first real three-machine
    proof was rejected because a 154k-token authoring session was compared
    against a 7.4k redo, and that gap is the measurement, not a violation.
    """
    tokens, usd, calls = 0, 0.0, 0
    for event in events:
        if event.get("event") != "session":
            continue
        transcript = event.get("transcript")
        if not transcript or not os.path.isfile(transcript):
            continue
        try:
            with open(transcript, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            usage = (entry.get("message") or {}).get("usage") \
                if isinstance(entry.get("message"), dict) else None
            usage = usage or entry.get("usage")
            if not isinstance(usage, dict):
                continue
            calls += 1
            for key in ("input_tokens", "output_tokens",
                        "cache_read_input_tokens",
                        "cache_creation_input_tokens"):
                value = usage.get(key)
                if isinstance(value, (int, float)) and \
                        not isinstance(value, bool):
                    tokens += value
            cost = entry.get("costUSD") or entry.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                usd += cost
    out = {}
    if tokens:
        out["tokens"] = tokens
    if usd:
        out["usd"] = usd
    if calls:
        out["calls"] = calls
    return out


def propose(workspace: str, accept, name: str, claim=None,
            generated=None) -> dict:
    """Read a session's trace into a candidate recipe.

    What comes back is a PROPOSAL.  Nothing here is authority: the classes
    are declared (by `claim=` and `generated=`) or defaulted from
    observation, and `build_claim` is what holds the result to the gates.
    """
    events = _events(workspace)
    accepted = list(accept or [])
    declared = list(claim or [])
    writes, reads, commands, prompts, stamps = [], [], [], 0, []
    for event in events:
        kind = event.get("event")
        if event.get("ts") is not None:
            try:
                stamps.append(float(event["ts"]))
            except (TypeError, ValueError):
                pass
        if kind == "prompt":
            prompts += 1
        elif kind == "write" and event.get("path"):
            writes.append(event["path"])
        elif kind == "read" and event.get("path"):
            reads.append(event["path"])
        elif kind == "bash" and event.get("cmd"):
            commands.append(event["cmd"])

    # Confinement FIRST, before a single byte is copied.
    for path in writes + reads:
        kernel._safe(workspace, path)

    produced = list(generated or [])
    for path in writes:
        if path in accepted or path in declared or path in produced:
            continue
        produced.append(path)
    # A traced write whose file was later deleted is an observation about a
    # file that is gone, not a claim about one.
    produced = [p for p in produced if _entry(workspace, p)]

    gates = [c for c in commands
             if any(output in c for output in accepted)] or list(commands)
    inputs = list(declared)
    for command in gates:
        for token in _tokens(command):
            if token in accepted or token in produced or token in inputs:
                continue
            try:
                kernel._safe(workspace, token)
            except kernel.ClaimError:
                continue
            if _entry(workspace, token):
                inputs.append(token)
    for path in reads:
        if path in accepted or path in produced or path in inputs:
            continue
        if _entry(workspace, path):
            inputs.append(path)

    steps = []
    for output in produced:
        steps.append({"kind": "produce", "output": output,
                      "class": "generated",
                      "guidance": f"regenerate {output} to pass the gate"})
    for output in accepted:
        command = _gate_for(commands, output)
        if not command:
            continue
        steps.append({"kind": "gate", "output": output, "class": "validated",
                      "run": command})
    recipe = {"claim": {"name": name, "format": 3, "inputs": inputs},
              "step": steps}
    recipe["_session"] = {
        "calls": prompts,
        "seconds": (max(stamps) - min(stamps)) if len(stamps) > 1 else 0.0,
        "discovery": _session_cost(workspace, events),
        "unresolved": [],
    }
    return recipe


def build_claim(workspace: str, accept, target: str, name: str = None,
                claim=None, generated=None) -> dict:
    """Seal a session into a claim — and certify it COLD before sealing.

    The trace said these gates passed.  That is not evidence: a verdict is
    earned by running the gates against the bytes present, so the candidate
    is sealed and immediately audited, and a pinned verdict that cannot
    reproduce (a nondeterministic gate) refuses to seal at all.  No claim
    forms from one the workspace cannot re-earn.
    """
    recipe = propose(workspace, accept, name or os.path.basename(
        os.path.abspath(workspace)), claim=claim, generated=generated)
    session = recipe.pop("_session")
    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"the gate(s) {', '.join(vacuous)} are vacuous: every file that "
            f"decides them is generated, so the verdict depends on no claim "
            f"and the root would fit any implementation that prints ok. "
            f"Declare the check as a criterion (claim=[...])")
    if not kernel.gates(recipe):
        raise kernel.ClaimError(
            "nothing to seal: the session traced no command earning an "
            "accepted output")

    if os.path.exists(target) and os.listdir(target):
        raise kernel.ClaimError(f"{target!r} already holds bytes")
    os.makedirs(target, exist_ok=True)
    with open(os.path.join(target, kernel.RECIPE), "w",
              encoding="utf-8") as handle:
        handle.write(render.dump_recipe(recipe))
    carry = list(recipe["claim"]["inputs"])
    carry += [s["output"] for s in recipe["step"]]
    for path in carry:
        source = kernel._safe(workspace, path)
        if os.path.isfile(source):
            _util.copy_into(source, kernel._safe(target, path))

    kernel.seal(target)
    verdict = kernel.audit(target)
    if not verdict["ok"]:
        shutil.rmtree(target, ignore_errors=True)
        detail = "; ".join(f"{g['output']}: {g['status']}"
                           for g in verdict["gates"])
        raise kernel.ClaimError(
            f"the session's verdicts do not re-earn cold ({detail or ''}); a "
            f"claim never forms from a verdict the workspace cannot reproduce")

    event = {"event": "oracle", "calls": session["calls"],
             "seconds": session["seconds"], "when": _util.stamp(),
             "scope": "session"}
    kernel.ledger(target, event)
    if session["discovery"]:
        kernel.ledger(target, dict({"event": "discovery",
                                    "scope": "discovery",
                                    "when": _util.stamp()},
                                   **session["discovery"]))
    manifest = kernel.read_manifest(target)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"],
            "claim": target, "gates": verdict["gates"]}
