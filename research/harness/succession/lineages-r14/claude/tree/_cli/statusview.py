"""reticuli._cli.statusview -- the status/draft/tree family (spec/layers.md:
surface).

Where `report.py` renders a verb's own one-shot result, this module
renders standing state: a sealed claim's status (terse, verbose, and
ledger-focused readings over `views._claim_view`), a not-yet-sealed
session's draft state, and the registry's whole shape (every claim, its
dependency DAG, one claim's own file anatomy). Read-only commentary, like
the rest of `_cli`: nothing here writes a byte.
"""
import os

from reticuli import kernel, registry, feedback, render, _util
from reticuli._cli import views

_DECLARED_ROLE = {
    "draft": "a session trace, not yet sealed -- no root to speak of",
    "sealed": "a root is computed and its gates are earned -- not yet authorized",
    "signed": "authorized by a trusted key and proven by a recorded crosscheck",
}


# -- one sealed claim: terse, verbose, ledger-focused -----------------------

def _t_status_claim(d: str) -> str:
    """One terse status line: name, short root, phase."""
    view = views._claim_view(d)
    return render.table([[view.get("name", ""), render.short(view.get("root", "")), view.get("phase", "")]])


def _v_status_claim(d: str) -> dict:
    """The full status view (`views._claim_view`), with the declared
    meaning of its own phase folded in -- the same dict a `--json` reader
    sees."""
    view = views._claim_view(d)
    view["phase_meaning"] = _DECLARED_ROLE.get(view.get("phase"), "")
    return view


def _ledger_status_claim(d: str) -> dict:
    """A claim's cost residue: every ledger entry, and the totals
    `kernel.cost` folds them into -- host bookkeeping, never identity."""
    events = kernel.ledger_events(d)
    return {"entries": len(events), "events": events, "cost": kernel.cost(d)}


def _files_claim(d: str) -> dict:
    """Every file a claim declares, and whether it is present now --
    pinned inputs and each class of produce step, read straight off the
    recipe, never inferred from what happens to sit on disk."""
    parsed = kernel.load_recipe(d)
    out = {"inputs": []}
    for name in _util.declared_inputs(d):
        out["inputs"].append({"path": name, "present": os.path.isfile(_util.safe_path(d, name))})
    for step in parsed.get("step", []):
        output, cls = _util.step_output(step)
        if not isinstance(output, str):
            continue
        out.setdefault(cls, []).append(
            {"path": output, "present": os.path.isfile(_util.safe_path(d, output))})
    return out


# -- a draft session, not yet sealed ----------------------------------------

def _r_status_draft(ws: str) -> dict:
    """Does `ws`'s session trace look sealable yet (`feedback.advise`),
    plus whether a trace exists at all -- the one rung before
    `_v_status_claim` has anything to read."""
    advice = feedback.advise(ws)
    advice["trace_present"] = os.path.isfile(os.path.join(ws, feedback.TRACE))
    return advice


# -- the registry's whole shape ----------------------------------------

def _r_claims(ws: str) -> str:
    """Every claim sealed into `ws`'s store, one row each
    (`registry.claims`)."""
    rows = [(c["name"], render.short(c["root"]), c["phase"]) for c in registry.claims(ws)]
    return render.table(rows, headers=("name", "root", "phase"))


def _r_deps(ws: str) -> dict:
    """The dependency DAG `ws`'s claims form (`registry.deps`)."""
    return registry.deps(ws)


def _r_tree(ws: str) -> str:
    """`_r_deps`'s DAG, rendered as a simple indented tree (`render.tree`)."""
    return render.tree(_r_deps(ws)["claims"])


def _r_structure(d: str) -> dict:
    """One claim's own anatomy: the files it declares, by class
    (`_files_claim`), and which store subdirectories (`sealed`, `deps`,
    `sign`, `attest`, ...) are present -- the CLI's own read of what sits
    on disk (spec/layers.md's `structure`, v1 `anatomy`)."""
    store = os.path.join(d, kernel.STORE)
    substructure = sorted(
        name for name in (os.listdir(store) if os.path.isdir(store) else ())
        if os.path.isdir(os.path.join(store, name)))
    return {"files": _files_claim(d), "store": substructure}
