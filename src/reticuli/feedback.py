"""The feedback loop: in a draft session, what's observed, what would be
declared, and what remains unresolved.

Reads the trace and classifies each present file along the authoring triad:

    observed   how the work touched it        read | write | command | -
    declared   what pack would make of it     input | generated | validated | -
    evidence   where the observation came     hook | shell | gate | trace | -

The `declared` column mirrors `authoring.propose` exactly — reads and
command-named files become pinned inputs, covered writes become generated
produce steps, gate outputs become validated verdicts, and an untraced
present file becomes NOTHING (dashes), because observation discovers
possible dependencies and declaration decides. A generated file no gate
covers is unresolved: pack refuses it without --force. Read-only.
"""
from __future__ import annotations

import os
import re

from . import authoring as A

_INTERPRETERS = ("python3", "python", "sh", "bash")


def _executed_scripts(session: str, cmd: str) -> list[str]:
    """The scripts a command RUNS (python3 check.py, sh test.sh): deciders,
    never outputs — a command executes its script, it does not write it."""
    toks = cmd.replace('"', " ").replace("'", " ").split()
    out = []
    for i, tok in enumerate(toks):
        t = tok.strip(";,()|&<>")
        if not t.endswith((".py", ".sh")):
            continue
        ran = (i > 0 and os.path.basename(toks[i - 1]) in _INTERPRETERS) or i == 0
        if ran and A._names_a_file(session, t):
            out.append(t)
    return out


def _mentioned_in(session: str, scripts: list[str], base: str) -> bool:
    """Does any executed script name this file's module? `from primes import
    is_prime` covers primes.py — the canonical Python shape, where the check
    reaches the implementation through an import the command never names.
    A static word-match, honest about being one: the kernel still certifies
    cold, so a false quiet here costs advice, never identity."""
    stem = re.escape(os.path.splitext(base)[0])
    word = re.compile(rf"\b{stem}\b")
    for rel in scripts:
        try:
            with open(os.path.join(session, rel), encoding="utf-8",
                      errors="ignore") as f:
                if word.search(f.read(200_000)):
                    return True
        except OSError:
            continue
    return False


def _present(session: str) -> list[str]:
    out = []
    for base, dirs, files in os.walk(session):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(base, f), session).replace(os.sep, "/")
            if not rel.startswith(".") and not rel.endswith((".pyc", ".pyo")):
                out.append(rel)
    return out


def _via(events: list[dict], kind: str, path: str | None = None) -> str:
    """The evidence behind one observation: how the observing event arrived.
    Old traces carry no `via`, which is reported as `trace`, not guessed."""
    for e in events:
        if e.get("event") != kind:
            continue
        if path is not None and e.get("path") != path:
            continue
        return e.get("via") or "trace"
    return "-"


def advise(session: str) -> dict:
    session = os.path.abspath(session)
    ev = A._events(session)
    writes = {e["path"] for e in ev if e.get("event") == "write" and e.get("path")}
    reads = {e["path"] for e in ev if e.get("event") == "read" and e.get("path")}
    bashes = [e for e in ev if e.get("event") == "bash" and e.get("cmd")]

    gate_of: dict[str, str] = {}
    ran: list[str] = []
    for e in bashes:
        ran += _executed_scripts(session, e["cmd"])
    for f in _present(session):
        for e in bashes:
            # a script the command executes is a decider, not its output
            if A._writes(e["cmd"], f) \
                    and f not in _executed_scripts(session, e["cmd"]):
                gate_of.setdefault(f, e["cmd"])
                break

    # files a command NAMES become pinned inputs (authoring.propose's rule),
    # with the same token extraction, so the advisor never promises a
    # declaration the proposer would not make
    named: set[str] = set()
    for e in bashes:
        for t in e["cmd"].replace('"', " ").replace("'", " ").split():
            named.add(t.strip(";,()|&<>'\""))

    files = []
    for f in _present(session):
        base = os.path.basename(f)
        if f in gate_of:
            row = {"path": f, "observed": "write", "declared": "validated",
                   "evidence": "gate", "covered": True,
                   "role": "generated", "kind": "gate"}
        elif f in writes:
            covered = any(base in c for c in gate_of.values()) \
                or _mentioned_in(session, ran, base)
            row = {"path": f, "observed": "write",
                   "declared": "generated" if covered else "-",
                   "evidence": _via(ev, "write", f), "covered": covered,
                   "role": "generated", "kind": "produced"}
        elif f in reads:
            row = {"path": f, "observed": "read", "declared": "input",
                   "evidence": _via(ev, "read", f), "covered": True,
                   "role": "pinned", "kind": "input"}
        elif f in named:
            e = next(x for x in bashes
                     if f in {t.strip(";,()|&<>'\"") for t in
                              x["cmd"].replace('"', " ").replace("'", " ").split()})
            row = {"path": f, "observed": "command", "declared": "input",
                   "evidence": e.get("via") or "trace", "covered": True,
                   "role": "pinned", "kind": "input"}
        else:
            # present but untraced: observation saw nothing, pack declares
            # nothing — dashes, never a silent pin
            row = {"path": f, "observed": "-", "declared": "-",
                   "evidence": "-", "covered": True,
                   "role": "-", "kind": "present"}
        files.append(row)

    uncovered = sorted(x["path"] for x in files
                       if x["observed"] == "write" and x["declared"] == "-")
    gates = sorted(gate_of)
    sealable = bool(gates) and not uncovered
    if uncovered:
        nudge = ("add a gate that writes an output and names "
                 + ", ".join(os.path.basename(u) for u in uncovered))
    elif sealable:
        nudge = f"packable — `ret pack --accept {os.path.basename(gates[-1])} -o <claim>`"
    else:
        nudge = "run a check with `ret run` to author a gate"

    return {"phase": "draft", "session": session, "files": files,
            "uncovered": uncovered, "gates": gates, "sealable": sealable,
            "nudge": nudge, "trace_events": len(ev)}
