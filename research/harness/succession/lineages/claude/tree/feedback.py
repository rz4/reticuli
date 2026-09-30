"""reticuli.feedback -- sensing what's sealable (`spec/layers.md`).

`advise` looks at a workspace's trace the way `authoring.propose` does,
but asks a narrower question: has this session already produced a
verdict a claim could be sealed around? A traced `bash` command that
redirects into a file present on disk right now is exactly that signal --
the same shape `authoring.build_claim` will later re-certify cold.
"""
from . import authoring as _authoring


def advise(ws: str) -> dict:
    """Whether `ws`'s traced session looks sealable, and what it found."""
    events = _authoring._read_trace(ws)
    targets = []
    for e in _authoring._bash_events(events):
        targets.extend(_authoring._redirect_targets(e["cmd"]))
    present = [t for t in targets if _authoring._exists_case_exact(ws, t)]
    return {
        "sealable": bool(present),
        "candidates": sorted(set(targets)),
        "verdicts": sorted(set(present)),
    }
