"""Statusview: rendering for the status/draft/tree family -- the reads
that never run a gate (`views._claim_view` already did the only cheap
identity check that needs). `_t_status_claim`/`_v_status_claim` are the
terse and verbose forms of one claim's status; `_r_status_draft` is the
status view's own branch for a claim with no manifest yet, where there
is no root or phase ladder to show, only the files it declares;
`_r_structure`/`_r_tree` render one claim's declared shape and a
workspace's dependency forest; `_r_claims`/`_r_deps`/`_files_claim`/
`_ledger_status_claim` are the smaller readers those draw on.
"""
from .. import kernel
from .. import registry
from .. import render
from . import output
from . import views

_DECLARED_ROLE = {
    "generated": "regrowable output",
    "pinned": "input, pinned byte-for-byte",
    "validated": "gate verdict",
}


def _verbose(args) -> bool:
    return bool(getattr(args, "verbose", False)) and not getattr(args, "json", False)


def _files_claim(d: str) -> list:
    """Every file a claim's recipe declares, by role: the pinned
    `[claim] inputs`, then each step's own output under the role its
    `class` names (`_DECLARED_ROLE`)."""
    recipe = kernel.load_recipe(d)
    claim = recipe.get("claim", {})
    files = [{"path": p, "role": _DECLARED_ROLE["pinned"], "kind": "input"}
              for p in claim.get("inputs", [])]
    for step in recipe.get("step", []):
        cls = step.get("class", "generated" if step.get("kind") == "produce" else "pinned")
        files.append({"path": step["output"], "role": _DECLARED_ROLE.get(cls, cls),
                      "kind": step.get("kind")})
    return files


def _ledger_status_claim(d: str) -> list:
    """The claim's cost ledger, one human line per event, oldest first --
    diagnostic residue, read through `views._read_residue` rather than
    re-parsing the file here."""
    lines = []
    for event in views._read_residue(d):
        when = render.ago(event["when"]) if event.get("when") else "unknown"
        kind = event.get("event", "?")
        detail = ", ".join(f"{k}={v}" for k, v in event.items() if k not in ("event", "when"))
        lines.append(f"{when}: {kind}" + (f" ({detail})" if detail else ""))
    return lines


def _t_status_claim(view: dict) -> str:
    """The one-line status a terse read prints: name, phase, and --
    once sealed -- whether the present bytes still verify."""
    bits = [view.get("name") or "(unnamed)", f"[{view.get('phase') or '?'}]"]
    if view.get("phase") != "draft":
        bits.append("verified" if view.get("verified") else "BROKEN")
    return " ".join(bits)


def _v_status_claim(view: dict) -> str:
    """The full status table `-v` prints: every field of the documented
    state dict (`views._claim_view`), signatures and residue counted
    rather than dumped whole."""
    rows = [
        ("name", view.get("name") or "-"),
        ("root", render.short(view["root"]) if view.get("root") else "-"),
        ("phase", view.get("phase") or "-"),
        ("verified", view.get("verified")),
        ("signatures", len(view.get("signatures") or [])),
        ("residue events", len(view.get("residue") or [])),
        ("next", view.get("next") or "-"),
    ]
    return render.table(rows)


def _r_status_draft(d: str, args) -> dict:
    """The status view's branch for a claim still in draft: no manifest,
    no root, no phase ladder -- only the files its recipe already
    declares and the one rung that gets it off the ground."""
    files = _files_claim(d)
    data = {"phase": "draft", "files": files, "next": "seal the claim to compute its root"}
    if _verbose(args):
        rows = [(f["path"], f["role"]) for f in files]
        output._line(render.table(rows, headers=("path", "role")), args=args)
    else:
        output._line(f"draft, {len(files)} declared file(s)", args=args)
    return output._finish("status", data, True, "draft", args, None)


def _r_structure(d: str, args) -> dict:
    """One claim's declared shape: every file it names, grouped by the
    role its recipe gives it."""
    files = _files_claim(d)
    grouped = {}
    for f in files:
        grouped.setdefault(f["role"], []).append(f["path"])
    output._line(render.tree(grouped), args=args)
    return output._finish("structure", grouped, True, "ok", args, None)


def _r_tree(ws: str, args) -> dict:
    """The dependency forest of every claim staged under `ws`
    (`registry.deps`), as an indented tree of component names."""
    graph = registry.deps(ws)
    forest = {node["name"]: [e.get("component") or "?" for e in node["depends_on"]]
              for node in graph["claims"]}
    output._line(render.tree(forest), args=args)
    return output._finish("tree", graph, True, "ok", args, None)


def _r_claims(ws: str, args) -> dict:
    """Every claim staged under `ws` (`registry.claims`), one row per
    claim: name, root (truncated for display), phase."""
    items = registry.claims(ws)
    rows = [(c.get("name") or "-", render.short(c["root"]) if c.get("root") else "-", c.get("phase") or "-")
            for c in items]
    output._line(render.table(rows, headers=("name", "root", "phase")), args=args)
    return output._finish("claims", items, True, "ok", args, None)


def _r_deps(ws: str, args) -> dict:
    """The dependency edges of every claim staged under `ws`
    (`registry.deps`), one row per edge: the claim, the component it
    names, and whether that component actually resolves."""
    graph = registry.deps(ws)
    rows = []
    for node in graph["claims"]:
        edges = node.get("depends_on") or []
        if not edges:
            rows.append((node["name"], "-", "-"))
            continue
        for e in edges:
            rows.append((node["name"], e.get("component") or "-", e.get("status")))
    output._line(render.table(rows, headers=("claim", "component", "status")), args=args)
    return output._finish("deps", graph, True, "ok", args, None)
