"""Claims meeting claims: the store, the component DAG, and the deep audit.

A claim becomes a *component* of another when the dependent ships bytes the
component's own criteria judge.  Two species of link exist, and both must be
RE-EARNED rather than remembered:

* the CODE half — a `from` produce step, where the dependent ships the
  component's generated output.  The component's own gate is re-run on the
  DEPENDENT's bytes, because the dependent's gate is blind to a forgery its
  own check does not exercise.
* the DATA half — a pinned input content-matched to a component's output at
  seal time, with no `from` step.  That match had no fixture once, so it was
  checked ONCE and never re-earned: a forged input rode the manifest's
  attribution through verify, audit, the deep audit and the deps view, in
  every realization including the shipped tool.

The walk REMEMBERS.  A diamond is the smallest shape that can tell: a walk
that forgets reports three components where two are correct, and on a real
chain that became 311 layers where 18 were right.  And it resolves FLAT, by
root, wherever a component lives in the store — never by where it physically
nests, because a shared store is the layout a long chain actually uses.
"""
import os
import shutil

from . import _util, kernel

#: Where a workspace keeps the claims it knows about.
SEALED = "sealed"
#: Where an exported claim carries its components' claims.
DEPS = "deps"


# -- the store --------------------------------------------------------------


def _store(workspace: str) -> str:
    return os.path.join(workspace, kernel.STORE, SEALED)


def _is_claim(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    for name in (kernel.RECIPE, kernel.LEGACY_RECIPE):
        if os.path.isfile(os.path.join(path, name)):
            return True
    return False


def claims(workspace: str) -> list:
    """Every claim this workspace knows, with the phase its bytes support.

    Phase is read from the verifiable state, never from a manifest bit: an
    injected `proof` is not an authorization, and must not surface as signed
    anywhere.
    """
    out = []
    store = _store(workspace)
    if not os.path.isdir(store):
        return out
    for name in sorted(os.listdir(store)):
        where = os.path.join(store, name)
        if not _is_claim(where):
            continue
        row = {"name": name, "path": where, "root": None, "phase": "draft",
               "ok": False, "components": []}
        try:
            checked = kernel.verify(where)
            row.update(name=checked["name"], root=checked["root"],
                       ok=checked["ok"])
            row["phase"] = kernel.phase(where)
            row["components"] = kernel.read_manifest(where).get(
                "components") or []
        except kernel.ClaimError as exc:
            row["error"] = str(exc)
        out.append(row)
    return out


def detect_components(workspace: str, inputs: list) -> list:
    """Content-addressed links: a pinned input that IS a claim's output.

    Nothing is inferred from names or paths — the link exists because the
    bytes match, and re-earning it later is just hashing them again.
    """
    links = []
    known = []
    for row in claims(workspace):
        if not row.get("root"):
            continue
        try:
            parsed = kernel.load_recipe(row["path"])
        except kernel.ClaimError:
            continue
        for step in parsed.get("step", []):
            output = step.get("output")
            if not output:
                continue
            path = os.path.join(row["path"], output)
            if not os.path.isfile(path):
                continue
            try:
                known.append((row["name"], row["root"], output,
                              kernel._hash_file(path)))
            except kernel.ClaimError:
                continue
    for name in inputs:
        path = os.path.join(workspace, name)
        if not os.path.isfile(path):
            continue
        try:
            digest = kernel._hash_file(path)
        except kernel.ClaimError:
            continue
        for component, root, output, other in known:
            if other == digest:
                links.append({"input": name, "component": component,
                              "root": root, "output": output})
                break
    return links


def seal_with(claimdir: str, components: list = None, proof=None) -> dict:
    """Seal, carrying the component links (and a proof) as manifest residue.

    The links are provenance, not identity: they say where bytes came from,
    and the deep audit re-earns every one of them.
    """
    residue = {}
    if components is not None:
        residue["components"] = list(components)
    if proof is not None:
        residue["proof"] = proof
    return kernel.seal(claimdir, **residue)


# -- resolving the DAG ------------------------------------------------------


def _index(claimdir: str, workspace: str = None) -> dict:
    """Every claim directory reachable as a component, keyed by name.

    The search covers the claim's own drawer, its `deps/` drawer (where an
    export carries its components), and the workspace's shared store.  A
    component's components resolve from the SAME index, which is what makes
    a flat chain work: physical nesting is not a resolution rule.
    """
    found: dict = {}
    roots: list = []
    for base in ([claimdir] + ([workspace] if workspace else [])):
        for drawer in (SEALED, DEPS):
            where = os.path.join(base, kernel.STORE, drawer)
            if os.path.isdir(where):
                roots.append(where)
    # Deduped by REALPATH, because a shared store reaches the same layer
    # through many names: the chain symlinks every ancestor into every
    # layer's drawer, so a walk keyed on the literal path revisits each
    # layer once per PATH that reaches it — the traversal shape this
    # project has measured as an unfolding more than once.
    seen_dirs = set()
    while roots:
        where = roots.pop(0)
        real = os.path.realpath(where)
        if real in seen_dirs:
            continue
        seen_dirs.add(real)
        try:
            names = sorted(os.listdir(where))
        except OSError:
            continue
        for name in names:
            path = os.path.join(where, name)
            if not _is_claim(path):
                continue
            found.setdefault(name, path)
            for drawer in (SEALED, DEPS):
                nested = os.path.join(path, kernel.STORE, drawer)
                if os.path.isdir(nested):
                    roots.append(nested)
    return found


def _links(claimdir: str) -> list:
    try:
        return list(kernel.read_manifest(claimdir).get("components") or [])
    except kernel.ClaimError:
        return []


def _supplied(parsed: dict) -> dict:
    """Which of this claim's outputs are declared `from` a component."""
    return {s["output"]: s["from"] for s in kernel.produces(parsed)
            if s.get("from")}


def _source_of(top: str, dependent: str, shipped: str):
    """Where the bytes under judgement actually live.

    The OUTER claim's copy is preferred: a deep audit judges each layer's
    check against the bytes the outer claim SHIPS, not against the layer's
    own sealed copy, or a forgery one layer down would be judged by the very
    bytes it replaced.
    """
    for base in (top, dependent):
        if not base:
            continue
        path = os.path.join(base, shipped)
        if os.path.isfile(path):
            return base, path
    return None, None


def _judge_layer(top: str, dependent: str, name: str, group: list,
                 index: dict) -> dict:
    """Re-earn one component's criteria on the bytes its dependents ship."""
    row = {"name": name, "root": (group[0] or {}).get("root"), "ok": False,
           "status": "unresolved", "bytes_from": []}
    where = index.get(name)
    if not where:
        return row
    row["path"] = where
    try:
        checked = kernel.verify(where)
    except kernel.ClaimError as exc:
        row["status"] = f"unresolved ({exc})"
        return row
    row["root"] = checked["recomputed"]
    declared = next((l.get("root") for l in group if l.get("root")), None)
    if declared and checked["recomputed"] != declared:
        row["status"] = "moved: the component is off its declared root"
        return row

    produce_from, data = {}, []
    for link in group:
        shipped = link.get("input") or link.get("output")
        if not shipped:
            continue
        row["bytes_from"].append(shipped)
        base, source = _source_of(top, dependent, shipped)
        if not source:
            row["status"] = ("missing: no dependent ships "
                             f"{shipped!r} any more")
            return row
        try:
            parsed = kernel.load_recipe(base)
        except kernel.ClaimError as exc:
            row["status"] = f"unreadable dependent ({exc})"
            return row
        if shipped in _supplied(parsed):
            produce_from[link.get("output") or shipped] = source
        else:
            data.append((shipped, source, link.get("output") or shipped))

    # The DATA half: the attribution itself is the claim, so hash it again.
    for shipped, source, output in data:
        target = os.path.join(where, output)
        if not os.path.isfile(target):
            row["status"] = ("attribution unresolved: the matched bytes are "
                             "gone from the component")
            return row
        try:
            same = kernel._hash_file(source) == kernel._hash_file(target)
        except kernel.ClaimError as exc:
            row["status"] = f"attribution unresolved ({exc})"
            return row
        if not same:
            row["status"] = (f"attribution broken: {shipped!r} no longer "
                             f"holds the bytes {name!r} produced")
            return row

    try:
        verdict = kernel.audit(where, produce_from=produce_from or None)
    except kernel.ClaimError as exc:
        row["status"] = f"failed ({exc})"
        return row
    row["ok"] = bool(verdict["ok"])
    row["status"] = verdict["verdict"]
    row["gates"] = verdict.get("gates")
    return row


def _grouped(links: list) -> list:
    """One entry per component, carrying every path attributed to it."""
    order, groups = [], {}
    for link in links:
        name = link.get("component")
        if not name:
            continue
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append(link)
    return [(name, groups[name]) for name in order]


def audit_deep(claimdir: str, ws: str = None, **kwargs) -> dict:
    """Audit a claim AND re-earn every component beneath it, however deep.

    The result keeps `kernel.audit`'s shape, because this claim's OWN gates
    compose too: "gates compose, verdicts never carry" applies to the top of
    a chain as much as to its floor.  Depth must propagate refusals, not just
    visits — a broken GRANDPARENT, invisible to every gate above it, fails
    the composed verdict.
    """
    own = kernel.audit(claimdir, **kwargs)
    index = _index(claimdir, ws)
    layers, judged = [], set()
    frontier = [(claimdir, _links(claimdir))]
    while frontier:
        dependent, links = frontier.pop(0)
        for name, group in _grouped(links):
            if name in judged:
                continue
            judged.add(name)
            row = _judge_layer(claimdir, dependent, name, group, index)
            layers.append(row)
            where = row.get("path")
            if where:
                frontier.append((where, _links(where)))
    result = dict(own)
    result["layers"] = layers
    result["ok"] = bool(own["ok"]) and all(r["ok"] for r in layers)
    if not result["ok"] and own["ok"]:
        result["verdict"] = "composed"
    return result


def deps(workspace: str) -> dict:
    """The component DAG as the workspace can see it, edge by edge."""
    out = []
    index_cache: dict = {}
    for row in claims(workspace):
        edges = []
        index = index_cache.setdefault(
            row["path"], _index(row["path"], workspace))
        for name, group in _grouped(_links(row["path"])):
            judged = _judge_layer(row["path"], row["path"], name, group,
                                  index)
            edges.append({
                "component": name,
                "root": group[0].get("root"),
                "input": group[0].get("input"),
                "output": group[0].get("output"),
                "status": "ok" if judged["ok"] else judged["status"],
            })
        out.append({"name": row["name"], "root": row["root"],
                    "phase": row["phase"], "depends_on": edges})
    return {"claims": out}


def structure(claimdir: str, ws: str = None) -> dict:
    """What a claim is made of: its files by role, and the layers beneath."""
    parsed = kernel.load_recipe(claimdir)
    fmt = int(parsed.get("claim", {}).get("format", 1) or 1)
    files = []
    for name in kernel.declared_inputs(parsed, claimdir):
        files.append({"path": name, "class": "input", "role": "criterion"})
    for step in parsed.get("step", []):
        cls = kernel.step_class(step, fmt)
        role = {"generated": "free", "carried": "shipped",
                "validated": "verdict"}.get(cls, "pinned")
        if step.get("kind") == "gate":
            role = "verdict"
        files.append({"path": step.get("output"), "class": cls, "role": role,
                      "from": step.get("from")})
    index = _index(claimdir, ws)
    layers, frontier, seen = [], list(_links(claimdir)), set()
    while frontier:
        link = frontier.pop(0)
        name = link.get("component")
        if not name or name in seen:
            continue
        seen.add(name)
        where = index.get(name)
        layers.append({"name": name, "root": link.get("root"),
                       "resolved": bool(where), "path": where})
        if where:
            frontier.extend(_links(where))
    try:
        checked = kernel.verify(claimdir)
    except kernel.ClaimError:
        checked = {"name": parsed["claim"]["name"], "root": None, "ok": False}
    return {"name": checked.get("name"), "root": checked.get("root"),
            "ok": checked.get("ok"), "files": files, "layers": layers,
            "format": fmt}


# -- the signature chain ----------------------------------------------------


def sign_root(claimdir: str, ws: str = None) -> str:
    """Fold signed identity bottom-up over the DAG.

    The bottom is the most significant digit: a change at one layer moves its
    node and every node above, never one below, so the lowest node that moves
    names the floor of the change.  A declared component missing from the
    registry refuses the fold rather than eliding it — a chain root over an
    incomplete DAG is not a chain root.
    """
    index = _index(claimdir, ws)

    def fold(where: str, trail: tuple) -> str:
        checked = kernel.verify(where)
        below = []
        for link in _links(where):
            name = link.get("component")
            nested = index.get(name)
            if not nested:
                raise kernel.ClaimError(
                    f"the declared component {name!r} is missing from the "
                    f"registry, so this chain root would elide a layer")
            if name in trail:
                continue
            below.append(fold(nested, trail + (name,)))
        return kernel.sign_node(checked["root"],
                                kernel.build_digest(where), below)

    return fold(claimdir, ())


# -- rebuilding a chain -----------------------------------------------------


def _stage(component_dir: str, into: str, name: str) -> None:
    """Put a component's claim where the dependent's deep audit will find it."""
    target = os.path.join(into, kernel.STORE, SEALED, name)
    if os.path.exists(target):
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copytree(component_dir, target, symlinks=True,
                    ignore=shutil.ignore_patterns("scratch"))


def rebuild_chain(claimdir: str, producer: str, into: str, ws: str = None,
                  reuse: bool = False, **kwargs) -> dict:
    """Reproduce a composed claim, leaves first — or reuse what is sealed.

    With `reuse`, the sealed component's bytes are threaded in and the
    producer is never asked to reproduce a layer already earned: that is the
    layered build for large software, and the reason a coverage gap here let
    a cooperative producer mask a rebuild that silently regenerated the whole
    stack.
    """
    index = _index(claimdir, ws)
    parsed = kernel.load_recipe(claimdir)
    supplied = _supplied(parsed)
    links = _links(claimdir)
    rebuilt, produce_from, input_from = [], {}, {}
    scratch = os.path.join(os.path.abspath(into) + ".components")

    for link in links:
        name = link.get("component")
        where = index.get(name)
        if not where:
            raise kernel.ClaimError(
                f"the declared component {name!r} is not in the registry, so "
                f"this chain cannot be reproduced")
        shipped = link.get("input") or link.get("output")
        output = link.get("output") or shipped
        if reuse:
            source = os.path.join(where, output)
        else:
            target = os.path.join(scratch, name)
            if not os.path.isdir(target):
                nested = rebuild_chain(where, producer, target, ws=ws,
                                       reuse=reuse, **kwargs)
                rebuilt.append({"component": name, "root": nested["root"]})
            source = os.path.join(target, output)
        if not os.path.isfile(source):
            raise kernel.ClaimError(
                f"the component {name!r} does not carry {output!r}")
        if shipped in supplied:
            produce_from[shipped] = source
        else:
            input_from[shipped] = source

    result = kernel.rebuild(claimdir, producer, into,
                            produce_from=produce_from or None,
                            input_from=input_from or None, **kwargs)
    for link in links:
        name = link.get("component")
        origin = os.path.join(scratch, name)
        _stage(origin if os.path.isdir(origin) else index[name], into, name)
    if links:
        seal_with(into, components=[dict(l) for l in links])
        result.update(kernel.read_manifest(into))
    result["rebuilt_components"] = rebuilt
    return result


def pull(claimdir: str, workspace: str) -> dict:
    """Make a claim a dependency of a workspace, with its whole closure.

    A pulled claim STANDS ALONE — its source removed, it still verifies and
    its chain re-earns — and it stays DISK-COMPACT: each dependency's bytes
    appear O(1) times, never once per path that reaches them.  The corpus
    spanned all three regimes, including an exponential unfolding of shared
    ancestors, and 23G of chain history says which of those scales.
    """
    index = _index(claimdir, workspace)
    store = _store(workspace)
    os.makedirs(store, exist_ok=True)

    name = kernel.read_manifest(claimdir)["name"]
    order, frontier, seen = [], [(name, claimdir)], set()
    while frontier:
        label, where = frontier.pop(0)
        if label in seen:
            continue
        seen.add(label)
        order.append((label, where))
        for link in _links(where):
            child = link.get("component")
            resolved = index.get(child)
            if child and resolved and child not in seen:
                frontier.append((child, resolved))

    materialized = []
    for label, where in order:
        target = os.path.join(store, label)
        if not os.path.exists(target):
            # One copy per dependency, and its own drawer is left behind:
            # the closure is flat in the shared store, resolved by root.
            shutil.copytree(
                where, target, symlinks=False,
                ignore=shutil.ignore_patterns(SEALED, DEPS, "scratch"))
        materialized.append(label)

    parsed = kernel.load_recipe(claimdir)
    for path in kernel.declared_inputs(parsed, claimdir):
        source = kernel._safe(claimdir, path)
        if os.path.isfile(source):
            _util.copy_into(source, kernel._safe(workspace, path))
    for step in parsed.get("step", []):
        output = step.get("output")
        source = os.path.join(claimdir, output) if output else None
        if source and os.path.isfile(source):
            _util.copy_into(source, kernel._safe(workspace, output))
    return {"materialized": materialized, "name": name,
            "root": kernel.read_manifest(claimdir)["root"]}


# -- the composed comparison -----------------------------------------------


def crosscheck_deep(m1: str, m2: str, m3: str, ws: str = None,
                    **kwargs) -> dict:
    """The three-machine test with every leg's CHAIN re-earned.

    A shallow crosscheck is fooled by a forged layer: the dependent's own
    gate is blind to it by construction, so only the composed audit can see
    it.
    """
    result = kernel.crosscheck(m1, m2, m3, **kwargs)
    deep, rejected = {}, list(result["rejected"])
    for label, leg in zip(("M1", "M2", "M3"), (m1, m2, m3)):
        if not os.path.isdir(leg):
            deep[label] = result["audited"][label]
            continue
        try:
            deep[label] = bool(audit_deep(leg, ws)["ok"])
        except kernel.ClaimError:
            deep[label] = False
        if not deep[label] and result["audited"][label]:
            rejected.append(f"the composed chain beneath {label}")
    verdict = "reject" if rejected else result["verdict"]
    return dict(result, audited=deep, rejected=rejected, verdict=verdict,
                satisfied=verdict == "accept", deep=True)
