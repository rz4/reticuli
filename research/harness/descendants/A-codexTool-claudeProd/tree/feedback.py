"""Sensing what a session has, and what it still owes.

The authoring triad is three different questions, and conflating any two of
them is how a session seals the wrong boundary:

* **observed** — what the session was seen to do (a trace, with no authority);
* **declared** — what a claim would say about each file (a class, which only
  a declaration decides);
* **unresolved** — generated files no gate reaches, so nothing would judge
  them.

An untraced file is dashes in every column: observation is not silently a
declaration.  Coverage follows one level of import, because the canonical
Python shape reaches the implementation through an import the gate command
never names.
"""
import os

from . import authoring, kernel

#: Directories that are never a session's content.
_SKIP = {".reticuli", ".git", ".claude", "__pycache__", ".venv", "venv",
         ".launcher", "node_modules"}


def _walk(workspace: str) -> list:
    out = []
    for base, dirs, files in os.walk(workspace):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP)
        for name in sorted(files):
            path = os.path.relpath(os.path.join(base, name), workspace)
            out.append(path.replace(os.sep, "/"))
    return out


def advise(workspace: str) -> dict:
    """Read a session into the authoring triad, and say whether it is sealable."""
    if not os.path.isdir(workspace):
        raise kernel.ClaimError(f"no such directory: {workspace}")
    events = authoring._events(workspace)
    traced, commands = {}, []
    for event in events:
        kind = event.get("event")
        if kind in ("write", "read") and event.get("path"):
            traced.setdefault(event["path"], {"action": kind, "via": []})
            traced[event["path"]]["action"] = kind
            via = event.get("via")
            if via and via not in traced[event["path"]]["via"]:
                traced[event["path"]]["via"].append(via)
        elif kind == "bash" and event.get("cmd"):
            commands.append(event["cmd"])

    verdicts, deciders, named = [], [], set()
    for command in commands:
        deciders.extend(kernel.gate_deciders(command))
        # A gate NAMES what it reads, so any token that is a real entry is
        # reached by the gate.  Coverage is "does a gate judge this file",
        # which is wider than "does an interpreter run it".
        for token in authoring._tokens(command):
            if authoring._entry(workspace, token):
                named.add(token)
        parts = command.replace(">>", ">").split(">")
        if len(parts) > 1:
            target = parts[-1].strip().split()
            if target:
                verdicts.append(target[0])
    covered = set(named)
    for decider in deciders:
        covered.add(decider)
        # One level of import: the canonical Python shape reaches the
        # implementation through a name the gate command never writes down.
        covered.update(authoring._imports(workspace, decider))

    present = _walk(workspace)
    rows, unresolved = [], []
    for path in sorted(set(present) | set(traced)):
        info = traced.get(path)
        observed = info["action"] if info else "-"
        if path in verdicts:
            declared = "verdict"
        elif info and info["action"] == "write":
            declared = "generated"
        elif path in covered:
            declared = "criterion"
        else:
            declared = "-"
        evidence = list(info["via"]) if info else []
        if path in covered or path in verdicts:
            if "gate" not in evidence:
                evidence.append("gate")
        rows.append({"path": path, "observed": observed,
                     "declared": declared,
                     "evidence": ",".join(evidence) or "-",
                     "present": path in present})
        if declared == "generated" and path not in covered \
                and path in present:
            unresolved.append(path)

    observed_count = len(traced)
    declared_count = sum(1 for r in rows if r["declared"] != "-")
    sealable = bool(commands) and bool(verdicts) and not unresolved
    return {
        "state": "draft",
        "sealable": sealable,
        "observed": observed_count,
        "declared": declared_count,
        "unresolved": len(unresolved),
        "undeclared": unresolved,
        "files": rows,
        "gates": commands,
        "verdicts": verdicts,
        "deciders": deciders,
    }
