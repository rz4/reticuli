"""The status/draft/tree family: renderers that show a claim's (or a
workspace's) current state without judging anything (`spec/layers.md`'s
surface layer).

`_v_status_claim` extends `views._claim_view` (name, phase, gates,
signatures, residue, next step) with the two things a status report also
wants: which declared files are present (`_files_claim`) and what the cost
ledger shows (`_ledger_status_claim`). `_t_status_claim` renders that view
as text. `_r_status_draft` is the same question asked of an unsealed
workspace, where there is no recipe yet to view -- only a session trace.
`_r_tree`/`_r_structure` render a claim's dependency tree and its recipe's
own anatomy; `_r_claims`/`_r_deps` render a workspace's whole registry.

Stdlib only.
"""
import json
import os

from .. import feedback
from .. import kernel
from .. import registry
from .. import render
from . import report
from . import views

_TRACE = ".reticuli/draft.jsonl"

_DECLARED_ROLE = {
    "input": "pinned input",
    "generated": "generated",
    "free": "generated",
    "pinned": "pinned output",
    "exact": "pinned output",
    "validated": "gate verdict",
}


# ---------------------------------------------------------------------------
# A sealed claim's status view
# ---------------------------------------------------------------------------

def _files_claim(d: str) -> list:
    """Every file a claim's recipe declares (pinned inputs, then every
    step's output in order), and whether it is present on disk right now."""
    recipe = kernel.load_recipe(d)
    rows = []
    seen = set()
    for path in recipe.get("claim", {}).get("inputs", []):
        if path in seen:
            continue
        seen.add(path)
        rows.append({"path": path, "role": "input",
                    "present": os.path.isfile(os.path.join(d, path))})
    for step in recipe.get("step", []):
        path = step.get("output")
        if not path or path in seen:
            continue
        seen.add(path)
        default_role = "generated" if step.get("kind") == "produce" else "pinned"
        rows.append({"path": path, "role": step.get("class", default_role),
                    "present": os.path.isfile(os.path.join(d, path))})
    return rows


def _ledger_status_claim(d: str) -> dict:
    """A claim's cost ledger, summarized: how many entries it holds, the
    totals per unit (`kernel.cost`), and when the last one was recorded."""
    events = kernel.ledger_events(d)
    last_when = None
    for entry in reversed(events):
        if entry.get("when"):
            last_when = entry["when"]
            break
    return {"events": len(events), "cost": kernel.cost(d), "last": last_when}


def _v_status_claim(d: str) -> dict:
    """The full status view for a sealed claim: `views._claim_view` plus
    which declared files are present and what the ledger shows."""
    view = dict(views._claim_view(d))
    view["files"] = _files_claim(d)
    view["ledger"] = _ledger_status_claim(d)
    return view


def _t_status_claim(view: dict) -> str:
    """`_v_status_claim`'s dict, rendered as the lines a human `status`
    reads: name, phase, root, per-gate verdict presence, declared files,
    the ledger summary, then the next rung to climb."""
    lines = [
        report._row("name", view.get("name")),
        report._row("phase", view.get("phase")),
        report._row("root", view.get("root")),
        report._row("verified", view.get("verified")),
    ]
    for gate in view.get("gates", []):
        lines.append(report._row(f"gate {gate['output']}", gate["status"]))
    for f in view.get("files", []):
        role = _DECLARED_ROLE.get(f["role"], f["role"])
        mark = "present" if f["present"] else "missing"
        lines.append(report._row(f"file {f['path']}", f"{role} ({mark})"))
    ledger = view.get("ledger") or {}
    lines.append(report._row("ledger", f"{ledger.get('events', 0)} events"))
    if ledger.get("last"):
        lines.append(report._row("last recorded", report._when(ledger["last"])))
    lines.append(report._row("next", view.get("next")))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# An unsealed workspace's draft status
# ---------------------------------------------------------------------------

def _read_draft_trace(ws: str) -> list:
    path = os.path.join(ws, _TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _r_status_draft(ws: str, args) -> dict:
    def _run(ws):
        events = _read_draft_trace(ws)
        counts = {}
        for event in events:
            kind = event.get("event", "?")
            counts[kind] = counts.get(kind, 0) + 1
        result = {"ok": True, "events": len(events), "counts": counts}
        result.update(feedback.advise(ws))
        return result
    return report._generic_contract("status", _run, args, ws)


# ---------------------------------------------------------------------------
# Dependency tree and recipe structure
# ---------------------------------------------------------------------------

def _sealed_dir(ws: str, name: str) -> str:
    return os.path.join(os.path.abspath(ws), kernel.STORE, "sealed", name)


def _dep_tree_node(d: str, ws: str = None) -> dict:
    """The nested `{component name: {...}}` shape `render.tree` expects,
    built from a claim's declared component links -- the registry lookup
    order (`ws` first, then `d`'s own vendored copy), recursed."""
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        return {}
    names = []
    for entry in manifest.get("components") or []:
        if entry["component"] not in names:
            names.append(entry["component"])
    node = {}
    for name in names:
        comp_dir = None
        for base in (ws, d):
            if base and os.path.isdir(_sealed_dir(base, name)):
                comp_dir = _sealed_dir(base, name)
                break
        node[name] = _dep_tree_node(comp_dir, ws) if comp_dir else {}
    return node


def _r_tree(d: str, args, ws: str = None) -> dict:
    label = os.path.basename(os.path.abspath(d).rstrip(os.sep)) or d
    text = render.tree({label: _dep_tree_node(d, ws)})

    def _run(d, ws):
        return {"ok": True, "tree": text}
    env = report._generic_contract("tree", _run, args, d, ws)
    if not getattr(args, "json", False):
        print(text)
    return env


def _r_structure(d: str, args) -> dict:
    def _run(d):
        recipe = kernel.load_recipe(d)
        claim = recipe.get("claim", {})
        steps = []
        for step in recipe.get("step", []):
            default_role = "generated" if step.get("kind") == "produce" else "pinned"
            steps.append({"kind": step.get("kind"), "output": step.get("output"),
                         "class": step.get("class", default_role)})
        return {"ok": True, "name": claim.get("name"), "format": claim.get("format", 1),
                "inputs": list(claim.get("inputs", [])), "steps": steps}
    env = report._generic_contract("structure", _run, args, d)
    if not getattr(args, "json", False) and env["data"].get("steps"):
        rows = [(s["kind"], s["output"], s["class"]) for s in env["data"]["steps"]]
        print(render.table(rows, headers=["kind", "output", "class"]))
    return env


# ---------------------------------------------------------------------------
# A workspace's whole registry
# ---------------------------------------------------------------------------

def _r_claims(ws: str, args) -> dict:
    def _run(ws):
        return {"ok": True, "claims": registry.claims(ws)}
    env = report._generic_contract("claims", _run, args, ws)
    if not getattr(args, "json", False) and env["data"].get("claims"):
        rows = [(c["name"], render.short(c["root"]), c["phase"]) for c in env["data"]["claims"]]
        print(render.table(rows, headers=["name", "root", "phase"]))
    return env


def _r_deps(ws: str, args) -> dict:
    def _run(ws):
        result = registry.deps(ws)
        return {"ok": True, "claims": result["claims"]}
    return report._generic_contract("deps", _run, args, ws)
