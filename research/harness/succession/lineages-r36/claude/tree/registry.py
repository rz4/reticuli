"""Claims meeting claims: the store, the component DAG, and the deep audit.

A claim's store holds the claims it depends on (`.reticuli/sealed/<name>`,
or `.reticuli/deps/<name>` when they arrived in an archive). A dependency
has two species and both are re-earned here, because the dependent's own
gate is blind to either by construction:

  * the CODE half -- a produce step carrying `from` -- ships a component's
    bytes, and the component's OWN check must re-earn its verdict on the
    bytes the outer claim ships, not on the component's sealed copy;
  * the DATA half -- a pinned input content-matched to a component's output
    -- must re-earn that match, or a forged input rides the manifest's
    attribution through every verb.

Resolution is by ROOT wherever a component lives in the store, never by
where it physically nests: the real chains are staged flat.
"""
import os
import shutil
import tempfile

from . import _util
from . import kernel

SEALED = os.path.join(kernel.STORE, "sealed")
DEPS = os.path.join(kernel.STORE, "deps")


# -- the store -------------------------------------------------------------
def _stores(claim: str, ws: str | None = None) -> list:
    places = []
    for base in ([claim] if claim else []) + ([ws] if ws else []):
        for drawer in (SEALED, DEPS):
            where = os.path.join(base, drawer)
            if os.path.isdir(where):
                places.append(where)
    return places


def _claim_dirs(store: str) -> list:
    found = []
    for name in sorted(os.listdir(store)):
        where = os.path.join(store, name)
        if not os.path.isdir(where):
            continue
        try:
            kernel.recipe_path(where)
        except kernel.ClaimError:
            continue
        found.append(where)
    return found


def claims(ws: str) -> list:
    """Every claim in a workspace's store, with the phase it can prove.

    The phase comes from the verifiable state, never from a bit in a
    manifest: an injected `proof` is not an authorization, and must not
    surface as signed anywhere.
    """
    out = []
    for store in _stores(ws):
        for where in _claim_dirs(store):
            try:
                manifest = kernel.read_manifest(where)
                phase = kernel.phase(where)
            except kernel.ClaimError:
                continue
            out.append({"name": manifest["name"], "root": manifest["root"],
                        "phase": phase, "path": where,
                        "components": manifest.get("components") or []})
    return out


def _resolve(link: dict, claim: str, ws: str | None = None):
    """Where this component's claim is -- by name, then by root."""
    name, root = link.get("component"), link.get("root")
    for store in _stores(claim, ws):
        candidate = os.path.join(store, name or "")
        if name and os.path.isdir(candidate):
            try:
                kernel.recipe_path(candidate)
                return candidate
            except kernel.ClaimError:
                pass
    for store in _stores(claim, ws):
        for where in _claim_dirs(store):
            try:
                if kernel.read_manifest(where)["root"] == root:
                    return where
            except kernel.ClaimError:
                continue
    return None


def _links(claim: str) -> list:
    try:
        return kernel.read_manifest(claim).get("components") or []
    except kernel.ClaimError:
        return []


def seal_with(claim: str, components=None, proof=None) -> dict:
    """Seal a claim and record what it was built on, as manifest residue."""
    return kernel.seal(claim, components=components, proof=proof)


def detect_components(ws: str, inputs) -> list:
    """Content-addressed dependency detection.

    A pinned input whose bytes ARE some stored claim's output is that
    claim's output: the link is discovered by content, never declared by
    hand, so it cannot name a component the bytes did not come from.
    """
    catalogue = {}
    for store in _stores(ws):
        for where in _claim_dirs(store):
            try:
                parsed = kernel.load_recipe(where)
                manifest = kernel.read_manifest(where)
            except kernel.ClaimError:
                continue
            for step in parsed.get("step") or []:
                output = step.get("output")
                if not output:
                    continue
                path = os.path.join(where, output)
                if not os.path.isfile(path):
                    continue
                catalogue.setdefault(_util.hash_file(path), []).append(
                    {"component": manifest["name"], "root": manifest["root"],
                     "output": output})
    links = []
    for declared in inputs:
        path = os.path.join(ws, declared)
        if not os.path.isfile(path):
            continue
        for found in catalogue.get(_util.hash_file(path), []):
            links.append(dict(found, input=declared))
            break
    return links


def deps(ws: str) -> dict:
    """The DAG, as the store can prove it."""
    rows = []
    for entry in claims(ws):
        edges = []
        for link in entry["components"]:
            where = _resolve(link, entry["path"], ws)
            status = "unresolved"
            if where:
                try:
                    status = "ok" if kernel.read_manifest(where)["root"] == \
                        link.get("root") else "moved"
                except kernel.ClaimError:
                    status = "unresolved"
            edges.append({"component": link.get("component"),
                          "root": link.get("root"), "status": status,
                          "input": link.get("input")})
        rows.append({"name": entry["name"], "root": entry["root"],
                     "phase": entry["phase"], "depends_on": edges})
    return {"claims": rows, "workspace": ws}


def structure(claim: str, ws: str | None = None) -> dict:
    """What this claim is made of: its own files by role, and its layers."""
    parsed = kernel.load_recipe(claim)
    table = parsed.get("claim") or {}
    files = []
    for path in _util.declared_inputs(parsed):
        files.append({"path": path, "role": "input", "class": "pinned"})
    for step in parsed.get("step") or []:
        files.append({"path": step.get("output"),
                      "role": step.get("kind"),
                      "class": kernel.step_class(step),
                      "from": step.get("from")})
    layers = []
    for link in _links(claim):
        where = _resolve(link, claim, ws)
        layers.append({"name": link.get("component"), "root": link.get("root"),
                       "resolved": bool(where), "input": link.get("input")})
    return {"name": table.get("name"), "files": files, "layers": layers,
            "format": table.get("format", 1)}


# -- the deep audit --------------------------------------------------------
def _shipped_source(link: dict, shipped: str, parent: str, component: str):
    """Whose bytes a component's check must judge.

    The bytes the OUTERMOST claim ships, where that claim carries the path:
    an inner layer must not pass on its own sealed copy while something else
    travels. Falling back inward keeps a partially shipped chain judgeable.
    """
    declared = link.get("input") or link.get("output")
    for base in (shipped, parent, component):
        if not base:
            continue
        candidate = os.path.join(base, declared)
        if os.path.isfile(candidate):
            return candidate
    return None


def _judge_layer(links: list, where: str, shipped: str, parent: str,
                 strict: bool = True) -> dict:
    """One component, re-earned on the bytes the outer claim ships.

    A component is judged ONCE however many paths link to it, with every
    one of those paths substituted together: a walk that forgot would judge
    a composition nobody ships, and a walk that judged per path would report
    one layer many times.
    """
    first = links[0]
    row = {"name": first.get("component"), "root": first.get("root"),
           "ok": False, "status": "unresolved", "bytes_from": []}
    try:
        kernel.load_recipe(where)
        declaring = kernel.load_recipe(parent)
    except kernel.ClaimError as exc:
        row["status"] = f"unreadable: {exc}"
        return row
    # the SPECIES comes from the claim that declared the link: a `from`
    # produce step ships a component's code, while a pinned input
    # content-matched to a component's output is a data dependency.
    declared_inputs = set(_util.declared_inputs(declaring))
    outputs = {s.get("output") for s in kernel.produces(declaring)}

    substitute, carried = {}, []
    for link in links:
        name = link.get("input") or link.get("output")
        source = _shipped_source(link, shipped, parent, where)
        if not source:
            continue
        carried.append(name)
        if name in declared_inputs and name not in outputs:
            # the DATA half: the attribution itself is the claim, so the
            # content match is re-earned rather than read off a manifest
            theirs = os.path.join(where, link.get("output") or name)
            if not os.path.isfile(theirs) or \
                    _util.hash_file(source) != _util.hash_file(theirs):
                row["bytes_from"] = carried
                row["status"] = ("attribution no longer holds: the shipped "
                                 "bytes are not this component's output")
                return row
        else:
            substitute[link.get("output") or name] = source
    row["bytes_from"] = carried
    try:
        verdict = kernel.audit(where, produce_from=substitute or None,
                               strict=strict)
    except kernel.ClaimError as exc:
        row["status"] = f"refused: {exc}"
        return row
    row["ok"] = bool(verdict["ok"])
    row["status"] = verdict["verdict"]
    row["gates"] = verdict["gates"]
    return row


def _grouped(links: list) -> list:
    """Links collected by the component they name, in first-seen order."""
    order, groups = [], {}
    for link in links:
        key = (link.get("component"), link.get("root"))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(link)
    return [(key, groups[key]) for key in order]


def audit_deep(claim: str, ws: str | None = None, reuse: bool = False,
               strict: bool = True) -> dict:
    """Audit this claim AND every claim beneath it, each exactly once.

    A composed verdict keeps `kernel.audit`'s shape, because the top claim's
    own gates compose too: gates compose, verdicts never carry. Depth
    propagates refusals, not merely visits -- a broken GRANDPARENT, which
    every gate above it is blind to, fails the composed verdict.
    """
    result = dict(kernel.audit(claim, strict=strict))
    layers, seen = [], set()
    frontier = [claim]
    while frontier:
        parent = frontier.pop(0)
        for key, links in _grouped(_links(parent)):
            if key in seen:
                continue
            seen.add(key)
            where = _resolve(links[0], parent, ws) or \
                _resolve(links[0], claim, ws)
            if not where:
                layers.append({"name": key[0], "root": key[1], "ok": False,
                               "status": "unresolved", "bytes_from": []})
                continue
            layers.append(_judge_layer(links, where, claim, parent,
                                       strict=strict))
            frontier.append(where)
    result["layers"] = layers
    result["ok"] = bool(result.get("ok")) and all(r["ok"] for r in layers)
    if not result["ok"] and result.get("verdict") == "earned":
        result["verdict"] = "composed"
    return result


def crosscheck_deep(m1: str, m2: str, m3: str, ws: str | None = None,
                    tolerance=None, mutants: int | None = None,
                    strict: bool = True) -> dict:
    """The three-machine test over COMPOSED claims: every layer of every leg
    re-earns, or the comparison is not satisfied. A shallow crosscheck is
    fooled by a forged layer the dependent's own gate cannot see."""
    result = dict(kernel.crosscheck(m1, m2, m3, tolerance=tolerance,
                                    mutants=mutants))
    composed, legs = {}, {"M1": m1, "M2": m2, "M3": m3}
    for name, leg in legs.items():
        if not os.path.isdir(leg):
            composed[name] = None
            continue
        deep = audit_deep(leg, ws=ws, strict=strict)
        composed[name] = {"ok": deep["ok"], "layers": deep["layers"]}
        if not deep["ok"]:
            result["rejected"] = list(result.get("rejected") or []) + \
                [f"{name} composed verdicts re-earned"]
    result["composed"] = composed
    if result.get("rejected"):
        result["verdict"] = "reject"
    result["satisfied"] = result.get("verdict") == "accept"
    return result


def record_proof_deep(m1: str, m2: str, m3: str, ws: str | None = None,
                      signers: str | None = None) -> dict:
    """A recorded proof over composed claims."""
    result = crosscheck_deep(m1, m2, m3, ws=ws)
    if not result["satisfied"]:
        out = dict(result)
        out["proof_recorded"] = False
        return out
    return kernel.record_proof(m1, m2, m3, signers=signers)


# -- the signature chain ---------------------------------------------------
def sign_root(claim: str, ws: str | None = None) -> str:
    """Signed identity, folded bottom-up over the DAG.

    The bottom is the most significant digit: a change at one layer moves
    its node and every node above it, and never one below -- so the lowest
    node that moved names the floor of the change. A declared component
    missing from the store refuses the fold rather than eliding it: a chain
    root over an incomplete DAG is not a chain root.
    """
    below = []
    for link in _links(claim):
        where = _resolve(link, claim, ws)
        if not where:
            raise kernel.ClaimError(
                f"the declared component {link.get('component')!r} is not in "
                f"the store, so this chain root cannot be folded")
        below.append(sign_root(where, ws))
    return kernel.sign_node(kernel.verify(claim)["recomputed"],
                            kernel.build_digest(claim), below)


# -- rebuilding a chain ----------------------------------------------------
def rebuild_chain(claim: str, producer: str, into: str,
                  ws: str | None = None, reuse: bool = False,
                  guidance: bool = True, producer_env=None) -> dict:
    """Rebuild a composed claim, leaves first.

    With `reuse`, a sealed component is threaded in rather than regrown --
    the layered build for large software: seal a component once, then build
    on it without repaying to reproduce it. Without it, every layer is
    regrown from its own criteria, which is what an independent redo of the
    whole chain means.
    """
    parsed = kernel.load_recipe(claim)
    outputs = {s.get("output") for s in kernel.produces(parsed)}
    declared = set(_util.declared_inputs(parsed))
    produce_from, input_from, rebuilt = {}, {}, []
    scratch = tempfile.mkdtemp(prefix="reticuli-chain-")
    try:
        for link in _links(claim):
            where = _resolve(link, claim, ws)
            if not where:
                raise kernel.ClaimError(
                    f"the declared component {link.get('component')!r} is "
                    f"not in the store, so this chain cannot be rebuilt")
            output = link.get("output") or link.get("input")
            if reuse:
                source = os.path.join(where, output)
            else:
                room = os.path.join(scratch, link.get("component") or "layer")
                grown = rebuild_chain(where, producer, room, ws=ws,
                                      reuse=reuse, guidance=guidance,
                                      producer_env=producer_env)
                rebuilt.append({"component": link.get("component"),
                                "root": grown["root"]})
                source = os.path.join(room, output)
            target = link.get("input") or output
            if target in outputs:
                produce_from[target] = source
            elif target in declared:
                input_from[target] = source
            else:
                produce_from[target] = source
        result = dict(kernel.rebuild(
            claim, producer, into, produce_from=produce_from or None,
            input_from=input_from or None, guidance=guidance,
            producer_env=producer_env))
        links = _links(claim)
        if links:
            # the rebuilt claim STANDS ALONE: its components' claims travel
            # into its own store, so its chain re-earns without the source.
            drawer = os.path.join(into, SEALED)
            os.makedirs(drawer, exist_ok=True)
            _closure(claim, ws, drawer, set())
            seal_with(into, components=links)
        result["rebuilt_components"] = rebuilt
        result["reused"] = sorted(produce_from) + sorted(input_from) \
            if reuse else []
        return result
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# -- pull ------------------------------------------------------------------
def _copy_claim(source: str, destination: str) -> None:
    """A claim, without its own store's drawers: those are copied flat, once
    each, so a shared ancestor appears O(1) times rather than once per path
    that reaches it."""
    def ignore(directory, names):
        skipped = set()
        if os.path.realpath(directory) == \
                os.path.realpath(os.path.join(source, kernel.STORE)):
            skipped |= {"sealed", "deps", "scratch"}
        return skipped
    shutil.copytree(source, destination, symlinks=False, ignore=ignore)


def _closure(claim: str, ws: str | None, into: str, seen: set) -> list:
    """Copy this claim's whole ancestry into one flat drawer."""
    brought = []
    for link in _links(claim):
        key = link.get("root") or link.get("component")
        if key in seen:
            continue
        seen.add(key)
        where = _resolve(link, claim, ws)
        if not where:
            continue
        target = os.path.join(into, link.get("component") or key)
        if not os.path.exists(target):
            _copy_claim(where, target)
        brought.append(link.get("component"))
        brought.extend(_closure(where, ws, into, seen))
    return brought


def pull(claim: str, ws: str, materialize: bool = True) -> dict:
    """Add another claim as a dependency of this workspace.

    The pulled claim STANDS ALONE: its whole closure travels with it, so the
    source can be removed and every layer still re-earns.
    """
    manifest = kernel.read_manifest(claim)
    parsed = kernel.load_recipe(claim)
    drawer = os.path.join(ws, SEALED)
    os.makedirs(drawer, exist_ok=True)
    target = os.path.join(drawer, manifest["name"])
    if os.path.exists(target):
        shutil.rmtree(target)
    _copy_claim(claim, target)
    carried = _closure(claim, os.path.dirname(os.path.dirname(claim)),
                       drawer, set())
    laid = []
    if materialize:
        for declared in _util.declared_inputs(parsed):
            source = os.path.join(target, declared)
            if os.path.isfile(source):
                _util.copy_into(source, os.path.join(ws, declared))
                laid.append(declared)
        for step in parsed.get("step") or []:
            output = step.get("output")
            source = os.path.join(target, output or "")
            if output and os.path.isfile(source):
                _util.copy_into(source, os.path.join(ws, output))
                laid.append(output)
    return {"name": manifest["name"], "root": manifest["root"],
            "path": target, "materialized": laid, "closure": carried}
