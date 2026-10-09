"""The surface layer's status/draft/tree family: the `-v` and terse views
of one claim (`status`), of a workspace registry (`claims`, `deps`, `tree`),
and of a claim's own declared shape (`structure`) -- plus `_files_claim`,
which pairs every file a claim declares with its role in plain words
(`_DECLARED_ROLE`), read from the step classes `spec/claim-format.md` names.

`_t_status_claim`/`_v_status_claim` are the terse and verbose renderings of
`_cli/views.py`'s `_claim_view`; `_r_status_draft` is their counterpart for
a workspace that has not sealed yet, where `_claim_view` has no manifest to
read. None of these run a gate or recompute a hash beyond what `views.py`
and `kernel.phase` already do -- a status view reports carried state, not
earned truth (`spec/verification.md`).

Built from `reticuli.kernel`, `reticuli._util`, `reticuli.render`,
`reticuli.registry`, `reticuli.feedback`, and `reticuli._cli.views`/
`report` -- the exchange and authoring layers below the surface
(`spec/layers.md`); never a kernel private. Stdlib only.
"""
import os

from reticuli import _util, feedback, kernel, registry, render
from reticuli._cli import report, views

_DECLARED_ROLE = {
    "generated": "regrowable",
    "free": "regrowable",
    "pinned": "fixed",
    "exact": "fixed",
    "validated": "earned",
}


def _files_claim(d: str) -> list:
    """Every file claim `d` declares, present on disk, paired with its
    role in plain words: the recipe and every pinned input read as
    `fixed`, every step output read by its own declared class.
    """
    doc = kernel.load_recipe(d)
    rows = []

    recipe_name = kernel.RECIPE if os.path.isfile(os.path.join(d, kernel.RECIPE)) \
        else kernel.LEGACY_RECIPE
    if os.path.isfile(os.path.join(d, recipe_name)):
        rows.append((recipe_name, _DECLARED_ROLE["pinned"]))

    for p in _util.declared_inputs(d, doc):
        if os.path.isfile(os.path.join(d, p)):
            rows.append((p, _DECLARED_ROLE["pinned"]))

    for step in doc.get("step") or []:
        output = step.get("output")
        if not output or not os.path.isfile(os.path.join(d, output)):
            continue
        cls = step.get("class") or ("generated" if step.get("kind") == "produce" else "pinned")
        rows.append((output, _DECLARED_ROLE.get(cls, cls)))

    return rows


def _ledger_status_claim(d: str) -> str:
    """One line summarizing claim `d`'s cost ledger: how many events it
    carries, and totals per unit where any were measured.
    """
    events = kernel.ledger_events(d)
    if not events:
        return "ledger: empty"
    count = f"{len(events)} event" + ("s" if len(events) != 1 else "")
    totals = kernel.cost(d)
    if not totals:
        return f"ledger: {count}"
    measured = ", ".join(f"{k}={v}" for k, v in sorted(totals.items()))
    return f"ledger: {count}, {measured}"


def _t_status_claim(d: str) -> str:
    """The one-line status of claim `d`: name, root prefix, phase, verdict
    -- or, for an unsealed workspace, the first line of `_r_status_draft`.
    """
    if views._phase(d) == "draft":
        return _r_status_draft(d).splitlines()[0]
    view = views._claim_view(d)
    return f"{view['name']} {render.short(view['root'])} {view['phase']} ({view['verdict']})"


def _v_status_claim(d: str) -> str:
    """The verbose, multi-line status of claim `d`: every field
    `_claim_view` reports, one `report._row` per field."""
    if views._phase(d) == "draft":
        return _r_status_draft(d)
    view = views._claim_view(d)
    lines = [f"{view['name']} ({view['root']})",
             report._row("phase", view["phase"]),
             report._row("verified", view["verified"]),
             report._row("verdict", view["verdict"])]
    for output, present in sorted(view["gates"].items()):
        lines.append(report._row(f"gate {output}", "present" if present else "missing"))
    lines.append(report._row("signatures", ", ".join(view["signatures"]) or "none"))
    lines.append(report._row("residue", view["residue"]))
    lines.append(report._row("proof", "recorded" if view["proof"] else "none"))
    lines.append(report._row("next", view["next"]))
    return "\n".join(lines)


def _r_status_draft(d: str) -> str:
    """The status of claim `d` before it is sealed: whatever recipe is
    already present (name, declared inputs, step counts), or -- with none
    yet -- a plain statement that nothing is declared; plus whether
    `feedback.advise` sees enough in the session's trace to be worth
    trying to seal.
    """
    lines = ["draft"]
    try:
        doc = kernel.load_recipe(d)
    except kernel.ClaimError:
        doc = None
        lines.append(report._row("recipe", "none yet"))

    if doc is not None:
        steps = doc.get("step") or []
        lines.append(report._row("name", doc.get("claim", {}).get("name", "?")))
        lines.append(report._row("inputs", len(_util.declared_inputs(d, doc))))
        lines.append(report._row("produce steps",
                                  sum(1 for s in steps if s.get("kind") == "produce")))
        lines.append(report._row("gate steps",
                                  sum(1 for s in steps if s.get("kind") == "gate")))

    try:
        advice = feedback.advise(d)
    except kernel.ClaimError:
        advice = None
    if advice is not None:
        lines.append(report._row("sealable", advice.get("sealable")))

    return "\n".join(lines)


def _r_claims(ws: str) -> str:
    """A table of every claim sealed in `ws`'s registry: name, root
    prefix, phase (`registry.claims`)."""
    rows = [(c["name"], render.short(c["root"]), c["phase"]) for c in registry.claims(ws)]
    return render.table(rows, headers=("name", "root", "phase"))


def _r_deps(ws: str) -> str:
    """A table of every dependency edge in `ws`'s registry: one row per
    (claim, component, status) (`registry.deps`); a claim with no
    components gets one row stating so.
    """
    rows = []
    for c in registry.deps(ws)["claims"]:
        if not c["depends_on"]:
            rows.append((c["name"], "-", "-"))
            continue
        for edge in c["depends_on"]:
            rows.append((c["name"], edge["component"], edge["status"]))
    return render.table(rows, headers=("claim", "component", "status"))


def _r_tree(ws: str) -> str:
    """The registry's dependency forest at `ws`: one `render.tree` per
    sealed claim that is not itself declared as another's component,
    recursing through `registry.deps`'s edges.
    """
    edges = {c["name"]: [e["component"] for e in c["depends_on"]]
              for c in registry.deps(ws)["claims"]}
    depended_on = {child for kids in edges.values() for child in kids}
    roots = sorted(name for name in edges if name not in depended_on) or sorted(edges)
    return "\n".join(render.tree(name, children=lambda n: edges.get(n, [])) for name in roots)


def _r_structure(d: str) -> str:
    """Claim `d`'s own shape: name, format, each step's `output` paired
    with `kind/class`, and -- for a composed claim -- the component tree
    rooted here, read from each manifest's own declared links (never run,
    never re-earned; that is `registry.audit_deep`'s job).
    """
    doc = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    claim = doc.get("claim", {})
    lines = [f"{claim.get('name', '?')} (format {claim.get('format', 1)})"]
    for step in doc.get("step") or []:
        cls = step.get("class") or ("generated" if step.get("kind") == "produce" else "pinned")
        lines.append(report._row(step["output"], f"{step['kind']}/{cls}"))

    if manifest.get("components"):
        def children(node):
            node_dir, node_manifest = node
            names = sorted({l["component"] for l in node_manifest.get("components") or []})
            kids = []
            for name in names:
                comp_dir = os.path.join(node_dir, ".reticuli", "sealed", name)
                try:
                    comp_manifest = kernel.read_manifest(comp_dir)
                except kernel.ClaimError:
                    comp_manifest = {"name": name}
                kids.append((comp_dir, comp_manifest))
            return kids

        def label(node):
            return node[1].get("name", "?")

        lines.append("components:")
        lines.append(render.tree((d, manifest), label=label, children=children))

    return "\n".join(lines)
