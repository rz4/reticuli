"""Feedback: sensing whether a session is ready to seal.

`advise` reads a workspace's trace and reports whether it looks sealable
-- a prompt that asked for something, and a gate that was actually run to
check it -- without certifying anything itself. The real certification,
cold and authoritative, is `authoring.build_claim`; this is only the
advisor that tells a human (or an agent) it is worth trying.
"""
from . import authoring


def advise(ws: str) -> dict:
    """Is `ws` sealable right now: has it been prompted, and has a gate
    actually been run against it?"""
    events = authoring._read_trace(ws)
    has_prompt = any(e.get("event") == "prompt" for e in events)
    bash_events = [e for e in events if e.get("event") == "bash" and e.get("cmd")]

    reasons = []
    if not has_prompt:
        reasons.append("no prompt recorded in the trace")
    if not bash_events:
        reasons.append("no gate has been run")

    return {"sealable": has_prompt and bool(bash_events), "reasons": reasons}
