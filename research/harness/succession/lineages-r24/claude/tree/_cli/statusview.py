"""reticuli._cli.statusview: the status/draft/tree family (spec/layers.md
"surface").

`views._claim_view` reads what the kernel already computed into one small
state dict; this module turns that dict into the two displays a human asks
for -- `_t_status_claim` (one line, the default) and `_v_status_claim`
(every field, under `-v`) -- plus the sibling renderers a workspace-level
`status` needs: a draft claim's own readiness (`_r_status_draft`, over
`feedback.advise`, since a claim with no manifest yet has nothing for
`views._claim_view` to read), its production cost so far
(`_ledger_status_claim`), its declared files (`_files_claim`), and the
dependency views across a whole store (`_r_claims`, `_r_deps`, `_r_tree`,
`_r_structure`). `_DECLARED_ROLE` names the three crosscheck positions a
claim can be read into (spec/verification.md); a record or a claim never
carries a role itself, so this is the surface's own label, not a kernel
fact. None of this touches identity -- it only displays what the layers
below already established.
"""
import os

from reticuli import feedback, kernel, registry, render

from . import output, views

_DECLARED_ROLE = {
    "M1": "the original workspace: verify in place",
    "M2": "transfer: export, import elsewhere, verify from received bytes",
    "M3": "independent rebuild: a producer sees only the pinned inputs",
}


# -- one claim's own state: terse and verbose -------------------------------

def _t_status_claim(d: str) -> str:
    """One line: name, short root, phase, verified y/n -- the default view."""
    view = views._claim_view(d)
    mark = "verified" if view["verified"] else "DRIFTED"
    return f"{view['name']}  {render.short(view['root'])}  {view['phase']}  {mark}"


def _v_status_claim(d: str) -> str:
    """Every field `views._claim_view` carries, one per line -- the `-v` form."""
    view = views._claim_view(d)
    lines = [
        f"name: {view['name']}",
        f"root: {view['root']}",
        f"phase: {view['phase']}",
        f"verified: {view['verified']}",
        f"vacuous_gates: {', '.join(sorted(view['vacuous'])) or '(none)'}",
    ]
    for gate in view["gates"]:
        lines.append(f"  gate {gate['output']}: {gate['deciders']}")
    for sig in view["signatures"]:
        lines.append(f"  signature: {sig}")
    lines.append(f"next: {view['next']}")
    return "\n".join(lines)


def _ledger_status_claim(d: str) -> dict:
    """Production cost totals so far (`kernel.cost`), plus the number of
    ledger events recorded -- an absent cost means nothing was ever
    measured, reported as such rather than guessed at (spec/kernel-api.md)."""
    return {"cost": kernel.cost(d), "events": len(kernel.ledger_events(d))}


def _files_claim(d: str) -> list:
    """Every file one recipe step declares, its class, and whether it is
    present on disk right now -- the recipe's own account of what belongs
    to this claim (spec/claim-format.md step classes), never a raw
    directory listing."""
    parsed = kernel.load_recipe(d)
    out = []
    for p in parsed.get("claim", {}).get("inputs", []) or []:
        out.append({"path": p, "class": "input",
                     "present": os.path.isfile(os.path.join(d, p))})
    for step in parsed.get("step", []) or []:
        cls = step.get("class")
        if cls is None:
            cls = "generated" if step.get("kind") == "produce" else "pinned"
        out.append({"path": step["output"], "class": cls,
                     "present": os.path.isfile(os.path.join(d, step["output"]))})
    return out


# -- a draft claim: nothing sealed yet, so nothing for views to read -------

def _r_status_draft(ws: str, args):
    """`status` on a claim that has not sealed yet: whether its session
    trace looks sealable (`feedback.advise`), through the same envelope
    every other verb renders through."""
    data = feedback.advise(ws)
    status = "sealable" if data["sealable"] else "not_sealable"
    return output._finish("status", data, data["sealable"], status, args)


# -- the store-wide views: claims, deps, tree, structure --------------------

def _r_claims(ws: str, args):
    """`claims` (v1: `records`): every sealed claim in `ws`'s store."""
    data = {"claims": registry.claims(ws)}
    return output._finish("claims", data, True, "ok", args)


def _r_deps(ws: str, args):
    """`deps`: the dependency DAG across `ws`'s store."""
    data = registry.deps(ws)
    return output._finish("deps", data, True, "ok", args)


def _r_tree(ws: str, args):
    """`tree`: the same dependency DAG, rendered as an indented text tree."""
    dag = registry.deps(ws)
    data = {"claims": dag["claims"], "tree": render.tree(dag)}
    return output._finish("tree", data, True, "ok", args)


def _r_structure(d: str, args):
    """`structure` (v1: `anatomy`): one claim's own layout -- its declared
    files, not its dependents -- over `_files_claim`."""
    data = {"files": _files_claim(d)}
    return output._finish("structure", data, True, "ok", args)
