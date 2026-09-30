"""reticuli._cli.statusview: the status/draft/tree family (spec/layers.md,
surface layer).

`status` has a terse form and a verbose one: `_t_status_claim` is the one
line a script's own log wants, `_v_status_claim` is the full state a person
reads top to bottom, and `_ledger_status_claim` is the cost history
underneath either. `_files_claim` answers "what does this claim actually
have on disk right now" -- every declared path against the bytes present.
`_r_claims`/`_r_deps` read a registry workspace's claim store back as a
flat list and as its dependency edges; `_r_tree`/`_r_structure` render that
same store as a person reads a tree, one claim's own component nesting or
the whole workspace's forest of root claims. `_r_status_draft` asks the
same status question of a session that has not sealed yet, by way of
`feedback.advise`.
"""
import os

from reticuli import feedback, kernel, registry, render

from .views import _claim_view, _read_residue

_DECLARED_ROLE = {
    "oracle": "producer",
    "gate": "gate run",
    "environment": "host",
    "reuse": "component reuse",
}


def _files_claim(d: str) -> dict:
    """Every path the claim's recipe declares -- pinned inputs and every
    step's output -- against whether it is actually on disk right now."""
    parsed = kernel.load_recipe(d)
    files = {}
    for p in parsed.get("claim", {}).get("inputs", []):
        files[p] = os.path.isfile(os.path.join(d, p))
    for step in parsed.get("step", []):
        files[step["output"]] = os.path.isfile(os.path.join(d, step["output"]))
    return files


def _ledger_status_claim(d: str) -> list:
    """The claim's cost ledger as small labeled rows: each entry's declared
    role (`_DECLARED_ROLE`) beside whatever it measured -- residue, not
    identity, so a partial or absent ledger reads as an empty list, never
    a refusal."""
    entries = _read_residue(d, "ledger.jsonl") or []
    rows = []
    for entry in entries:
        role = _DECLARED_ROLE.get(entry.get("event"), entry.get("event") or "unknown")
        detail = {k: v for k, v in entry.items() if k != "event"}
        rows.append((role, detail))
    return rows


def _t_status_claim(d: str) -> str:
    """The one-line terse status: name, phase, and a shortened root."""
    view = _claim_view(d)
    return f"{view['name']}  {view['phase']}  {render.short(view['root'] or '')}"


def _v_status_claim(d: str) -> list:
    """The full status a person reads top to bottom: the claim view's own
    fields, its signatures, and the next rung toward `signed`."""
    view = _claim_view(d)
    lines = [
        f"{view['name']}  ({view['phase']})",
        f"  root: {view['root']}",
        f"  verified: {view['verified']}",
    ]
    for sig in view["signatures"]:
        lines.append(f"  signature: {sig['name']} ({sig.get('identity')})")
    lines.append(f"  next: {view['next']}")
    return lines


def _r_status_draft(ws: str) -> list:
    """A session that has not sealed yet, read the same way
    `feedback.advise` reads it: sealable or not, and why."""
    verdict = feedback.advise(ws)
    return [f"draft: {'sealable' if verdict['sealable'] else 'not sealable'}",
            f"  reason: {verdict['reason']}"]


def _r_claims(ws: str) -> list:
    """Every sealed claim in the workspace's store, one row apiece."""
    return [f"{c['name']}  {c['phase']}  {render.short(c['root'])}"
            for c in registry.claims(ws)]


def _r_deps(ws: str) -> list:
    """The claim store's DAG, flattened to one row per component edge."""
    lines = []
    for c in registry.deps(ws)["claims"]:
        if not c["depends_on"]:
            lines.append(f"{c['name']}  (no components)")
            continue
        for dep in c["depends_on"]:
            lines.append(f"{c['name']} -> {dep['component']}  ({dep['status']})")
    return lines


def _structure_node(name: str, path: str) -> dict:
    manifest = kernel.read_manifest(path)
    children = [_structure_node(cname, os.path.join(path, rel))
                for cname, rel in (manifest.get("components") or {}).items()]
    return {"label": name, "children": children}


def _r_structure(ws: str) -> str:
    """The workspace's claim store as one ASCII tree per root claim --
    `render.tree` applied to the same DAG `registry.deps` already reads
    back, starting from whichever claims no other claim depends on."""
    depended_on = {dep["component"]
                   for c in registry.deps(ws)["claims"] for dep in c["depends_on"]}
    roots = [c for c in registry.claims(ws) if c["name"] not in depended_on]
    return "\n".join(render.tree(_structure_node(c["name"], c["path"])) for c in roots)


def _r_tree(d: str) -> str:
    """One claim's own component tree, from its manifest alone -- the
    single-claim form of `_r_structure`, for `ret tree` on a claim that is
    not necessarily part of a larger registry workspace."""
    manifest = kernel.read_manifest(d)
    return render.tree(_structure_node(manifest.get("name", d), d))
