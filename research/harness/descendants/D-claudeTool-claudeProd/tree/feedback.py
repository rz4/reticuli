"""Feedback: sensing what a session is ready to say.

The advisor reads the trace and answers one question -- is there a claim here
yet? -- in the three terms the authoring triad is built on: what was
OBSERVED, what the session would DECLARE, and what is left UNRESOLVED. It
never executes anything; a verdict is earned by the gate, not guessed at
here.
"""
import os

from . import authoring
from . import kernel
from ._util import read_json, safe_path


def _verdicts(ws: str, session: dict) -> list:
    """Files a traced gate wrote and that are present: candidate verdicts."""
    found = []
    for command in session["commands"]:
        for token in authoring._tokens(command):
            if token in found:
                continue
            if token in session["present"]:
                continue
            if authoring._entry_exists(ws, token) and ">" in command:
                tail = command.split(">")[-1].strip().split()
                if tail and tail[0] == token:
                    found.append(token)
    return found


def advise(ws: str, accept=None) -> dict:
    """What this session has, and what it still needs, in plain terms."""
    if not os.path.isdir(ws):
        raise kernel.ClaimError(f"no such directory: {ws}")
    accepted = list(accept or [])
    session = authoring._session(ws, accepted)
    if not accepted:
        accepted = _verdicts(ws, session)
        session = authoring._session(ws, accepted)
    observed = sorted(set(session["present"]) | set(session["reads"]))
    declared = sorted(set(session["named"]) | set(accepted))
    unresolved = sorted(session["unresolved"])
    earned = [v for v in accepted
              if authoring._entry_exists(ws, v)]
    reasons = []
    if not session["events"]:
        reasons.append("no session trace: nothing has been observed")
    if not session["gate"]:
        reasons.append("no command was run, so no verdict was earned")
    if not earned:
        reasons.append("no verdict file is present")
    if unresolved:
        reasons.append(
            f"undeclared generated file(s): {', '.join(unresolved)}")
    return {"sealable": not reasons,
            "why": reasons,
            "observed": observed,
            "declared": declared,
            "unresolved": unresolved,
            "accept": accepted,
            "gate": session["gate"],
            "commands": session["commands"],
            "calls": session["calls"],
            "seconds": session["seconds"],
            "meta": session["meta"],
            "events": session["events"]}


def session_usage(ws: str) -> dict:
    """The harness's own usage records, priced over the session's window.

    Testimony, stamped as such: tokens always, money only where the harness
    reported one -- a price table of our own would drift.
    """
    session = authoring._session(ws, [])
    meta = session["meta"] or {}
    transcript = meta.get("transcript")
    totals = {"tokens": 0, "usd": 0.0, "calls": 0}
    measured = False
    if transcript and os.path.isfile(transcript):
        import json
        with open(transcript, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                usage = ((entry.get("message") or {}).get("usage")
                         if isinstance(entry.get("message"), dict) else None)
                if not isinstance(usage, dict):
                    continue
                measured = True
                for key in ("input_tokens", "output_tokens",
                            "cache_read_input_tokens",
                            "cache_creation_input_tokens"):
                    value = usage.get(key)
                    if isinstance(value, (int, float)) \
                            and not isinstance(value, bool):
                        totals["tokens"] += value
                totals["calls"] += 1
                cost = entry.get("costUSD") or entry.get("total_cost_usd")
                if isinstance(cost, (int, float)) \
                        and not isinstance(cost, bool):
                    totals["usd"] += cost
    if not measured:
        return {}
    report = {"tokens": totals["tokens"], "calls": totals["calls"]}
    if totals["usd"]:
        report["usd"] = totals["usd"]
    return report
