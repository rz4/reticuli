"""The status/draft/tree family: the `-v` and terse views of a claim's state,
and the registry-wide listings (`claims`, `deps`, `tree`) built over it.

`views._claim_view` already reads a sealed/signed claim's full documented
state; `_v_status_claim`/`_t_status_claim` are its two renderings (a
multi-line report, and one terse line), and `_ledger_status_claim` is the
residue portion of that same view rendered on its own, since a caller may
want cost/environment/producer facts without the rest. A claim still in
`draft` has no root and no gate history yet, so it gets its own renderer
(`_r_status_draft`) rather than forcing `views._claim_view` to paper over
an identity that does not exist yet.

`_files_claim`/`_DECLARED_ROLE` classify a claim's declared files by the
step class that governs them (`generated`/`pinned`/`validated`); `_r_structure`
renders that classification. `_r_claims`/`_r_deps`/`_r_tree` render the
registry's own view of a workspace's store (`registry.claims`/`registry.deps`):
a flat listing, a flat edge table, and the same edges as an indented tree.
"""
from reticuli import feedback, kernel, registry, render
from reticuli._cli import output, views

_DECLARED_ROLE = {
    "generated": "generated -- regrowable, outside the root",
    "pinned": "pinned -- fixed bytes, inside the root",
    "validated": "validated -- a gate's own verdict",
}


def _dir(args) -> str:
    """The claim/workspace directory a verb operates on, defaulting to cwd."""
    return getattr(args, "dir", None) or "."


# --------------------------------------------------------------- status views
def _v_status_claim(d: str) -> str:
    """A claim's full documented state (`views._claim_view`), as a
    multi-line human-readable report -- the `-v` view."""
    view = views._claim_view(d)
    lines = [f"name: {view.get('name')}", f"root: {view.get('root')}",
             f"phase: {view.get('phase')}"]

    verified = view.get("verified")
    if verified is not None:
        lines.append(f"verified: {'ok' if verified.get('ok') else 'mismatch'}")

    for gate in view.get("gates") or []:
        lines.append(f"  gate {gate['output']}: {gate['words']}")
    for sig in view.get("signatures") or []:
        lines.append(f"  signature {sig['identity']}: {sig['verdict']}")

    residue = _ledger_status_claim(d)
    if residue:
        lines.append(residue)
    lines.append(f"next: {view.get('next')}")
    return "\n".join(lines)


def _t_status_claim(d: str) -> str:
    """A claim's state as one terse line: name, short root, phase."""
    view = views._claim_view(d)
    root = render.short(view.get("root") or "") or "-" * 8
    return f"{view.get('name')}  {root}  {view.get('phase')}"


def _ledger_status_claim(d: str) -> str:
    """The claim's ledger residue (`views._read_residue`) rendered on its
    own: cost totals, and the most recent environment/producer facts."""
    residue = views._read_residue(d)
    lines = []
    cost = residue.get("cost")
    if cost:
        lines.append("cost: " + ", ".join(f"{k}={v}" for k, v in sorted(cost.items())))
    environment = residue.get("environment")
    if environment:
        lines.append("environment: " + ", ".join(f"{k}={v}" for k, v in sorted(environment.items())))
    producer = residue.get("producer")
    if producer:
        lines.append("producer: " + ", ".join(f"{k}={v}" for k, v in sorted(producer.items())))
    return "\n".join(lines)


def _r_status_draft(args) -> int:
    """Render status for a claim still in `draft` phase: no root exists
    yet, so this shows its recipe's declared structure and whether its
    traced session looks ready to seal, in place of a verdict that
    cannot exist until it is sealed."""
    d = _dir(args)
    try:
        files = _files_claim(d)
    except kernel.ClaimError as e:
        output._err("status", str(e))
        output._finish("status", {"error": str(e)}, False, "error", args, None)
        return 1

    readiness = feedback.advise(d)
    data = {"phase": "draft", "files": files, "sealable": readiness["sealable"]}
    if not getattr(args, "json", False):
        word = "sealable" if readiness["sealable"] else "not yet sealable"
        output._line(args, f"draft  ({len(files)} declared file(s), {word})")
    output._finish("status", data, True, "draft", args, None)
    return 0


# -------------------------------------------------------------------- files
def _files_claim(d: str) -> list:
    """Every file `d`'s recipe declares, each labeled with its role
    (`_DECLARED_ROLE`): the claim's own pinned `inputs`, then every step's
    output classified by its `class` (`generated`/`pinned`/`validated`)."""
    recipe = kernel.load_recipe(d)
    claim = recipe.get("claim", {})
    rows = []
    seen = set()
    for path in claim.get("inputs", []):
        rows.append({"path": path, "role": "pinned"})
        seen.add(path)
    for step in recipe.get("step", []):
        path = step.get("output")
        if not path or path in seen:
            continue
        default = "generated" if step.get("kind") == "produce" else "validated"
        rows.append({"path": path, "role": step.get("class", default)})
        seen.add(path)
    return rows


def _r_structure(args) -> int:
    """Render `d`'s recipe structure: every declared file grouped by its
    role, plus the gate command(s) that decide the `validated` ones."""
    d = _dir(args)
    try:
        recipe = kernel.load_recipe(d)
        files = _files_claim(d)
    except kernel.ClaimError as e:
        output._err("structure", str(e))
        output._finish("structure", {"error": str(e)}, False, "error", args, None)
        return 1

    gates = [{"output": s["output"], "run": s.get("run")}
              for s in recipe.get("step", []) if s.get("kind") == "gate"]
    data = {"name": recipe.get("claim", {}).get("name"), "files": files, "gates": gates}

    if not getattr(args, "json", False):
        for role in ("pinned", "generated", "validated"):
            rows = [f["path"] for f in files if f["role"] == role]
            if rows:
                output._line(args, f"{_DECLARED_ROLE.get(role, role)}:")
                for path in rows:
                    output._line(args, f"  {path}")
    output._finish("structure", data, True, "ok", args, None)
    return 0


# ------------------------------------------------------------------ registry
def _r_claims(args) -> int:
    """Render every sealed claim in `ws`'s store: name, short root, phase."""
    ws = _dir(args)
    rows = registry.claims(ws)
    if not getattr(args, "json", False):
        text = render.table([[c["name"], render.short(c["root"]), c["phase"]] for c in rows])
        if text:
            output._line(args, text)
    output._finish("claims", {"claims": rows}, True, "ok", args, None)
    return 0


def _r_deps(args) -> int:
    """Render `ws`'s dependency report as a flat table: one row per
    claim/component edge, with whether that edge still resolves."""
    ws = _dir(args)
    graph = registry.deps(ws)
    rows = [[c["name"], dep["component"], dep["status"]]
             for c in graph.get("claims", []) for dep in c.get("depends_on", [])]
    if not getattr(args, "json", False):
        text = render.table(rows)
        if text:
            output._line(args, text)
    output._finish("deps", graph, True, "ok", args, None)
    return 0


def _r_tree(args) -> int:
    """Render `ws`'s dependency DAG as an indented tree (`render.tree`):
    each claim, and the components it depends on."""
    ws = _dir(args)
    graph = registry.deps(ws)
    node = {}
    for c in graph.get("claims", []):
        children = [f"{dep['component']} ({dep['status']})" for dep in c.get("depends_on", [])]
        node[c["name"]] = children or None
    if not getattr(args, "json", False):
        text = render.tree(node)
        if text:
            output._line(args, text)
    output._finish("tree", graph, True, "ok", args, None)
    return 0
