"""The registry: claims meeting claims (spec/layers.md's exchange layer).

A workspace (`ws`) holds sealed claims under `.reticuli/sealed/<name>`.
`detect_components` finds content-addressed links between a workspace's
files and another claim's pinned bytes; `seal_with` seals a claim while
recording which components it was built from (and, later, a recorded
proof); `claims`/`deps` read that registry back as a DAG; `rebuild_chain`
regrows a composed claim leaf-first; `sign_root` folds a signature-chain
node bottom-up over the DAG; `audit_deep`/`crosscheck_deep` re-earn every
ancestor's own gate on the bytes a dependent actually ships, not merely
the dependent's own gate.
"""
import os
import shutil
import tempfile

from . import _util
from . import kernel


# ------------------------------------------------------------- helpers --

def _is_generated(step: dict) -> bool:
    default_cls = "generated" if step.get("kind") == "produce" else "pinned"
    return step.get("class", default_cls) == "generated"


def _generated_outputs(recipe: dict) -> list:
    out = []
    for step in recipe.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", "generated") == "generated" and "from" not in step:
            out.append(step["output"])
    return out


def _patch_materialize_for_from_sources() -> None:
    """Every audit-style room (`kernel.audit`'s own, and the ones built
    deep inside `kernel.crosscheck`'s per-leg `_earned` and its mutation
    harness) is built by the SAME kernel primitive, `_materialize`, whose
    `include_generated` branch copies only what `generated_outputs`
    names -- and that function deliberately drops a `from`-sourced step,
    because `rebuild`'s single producer invocation must target exactly
    one output at a time, and a `from`-sourced one is supplied through
    `rebuild_chain`'s `input_from` instead, never asked of the producer.

    A composed claim that SHIPS a component's code through such a step
    therefore never receives it in any of those rooms: the dependent's
    own gate cannot even run, let alone be blind to a forgery one layer
    down, and `crosscheck`'s `every verdict earned` check rejects a
    perfectly honest chain for a reason that has nothing to do with its
    verdicts. Supplying the SAME bytes `d` already carries for that
    output -- exactly what every other `produce_from` substitution in
    this codebase does -- closes the gap for every one of those rooms at
    once, without touching `rebuild`'s own producer dispatch, which reads
    `generated_outputs` directly and never goes through this copy."""
    from reticuli._kernel import build as kernel_build

    original = kernel_build._materialize

    def materialize_with_from_sources(d, into, recipe, include_generated=False):
        original(d, into, recipe, include_generated=include_generated)
        if not include_generated:
            return
        for step in recipe.get("step", []):
            if step.get("kind") != "produce":
                continue
            if step.get("class", "generated") != "generated" or "from" not in step:
                continue
            output = step.get("output")
            src = os.path.join(d, output) if output else None
            if src and os.path.isfile(src):
                shutil.copyfile(src, os.path.join(into, output))

    kernel_build._materialize = materialize_with_from_sources


_patch_materialize_for_from_sources()


def find_component_dir(claim_dir: str, ws, name: str):
    """Where a declared component's own claim lives: the claim's local
    registry, the shared workspace's, or the deps a transfer left behind."""
    candidates = [os.path.join(claim_dir, kernel.STORE, "sealed", name)]
    if ws:
        candidates.append(os.path.join(ws, kernel.STORE, "sealed", name))
    candidates.append(os.path.join(claim_dir, kernel.STORE, "deps", name))
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


# ------------------------------------------------------------- sealing --

def seal_with(d: str, components=None, proof=None) -> dict:
    """Seal `d` (compute root, write the manifest) while carrying forward
    (or overriding) the component links and recorded proof it names --
    residue outside the root, so editing neither moves the claim."""
    manifest_path = os.path.join(d, kernel.MANIFEST)
    old = None
    if os.path.isfile(manifest_path):
        try:
            old = kernel.read_manifest(d)
        except kernel.ClaimError:
            old = None
    manifest = kernel.seal(d)
    if components is None and old:
        components = old.get("components")
    if proof is None and old:
        proof = old.get("proof")
    if components is not None:
        manifest["components"] = components
    if proof is not None:
        manifest["proof"] = proof
    _util.write_json(manifest_path, manifest)
    return manifest


# -------------------------------------------------------- content links --

def detect_components(ws: str, paths: list) -> list:
    """A pinned input that content-matches a sealed component's own step
    output is a dependency: the content-addressed link between claims."""
    sealed_root = os.path.join(ws, kernel.STORE, "sealed")
    links = []
    if not os.path.isdir(sealed_root):
        return links

    comps = []
    for name in sorted(os.listdir(sealed_root)):
        comp_dir = os.path.join(sealed_root, name)
        if not os.path.isdir(comp_dir):
            continue
        try:
            manifest = kernel.read_manifest(comp_dir)
            recipe = kernel.load_recipe(comp_dir)
        except kernel.ClaimError:
            continue
        comps.append((name, comp_dir, manifest["root"], recipe))

    for path in paths:
        full = os.path.join(ws, path)
        if not os.path.isfile(full):
            continue
        try:
            digest = kernel._hash_file(full)
        except kernel.ClaimError:
            continue
        for name, comp_dir, root, recipe in comps:
            matched = _match_output(comp_dir, recipe, digest)
            if matched:
                links.append({"input": path, "component": name, "root": root,
                              "output": matched})
                break
    return links


def _match_output(comp_dir: str, recipe: dict, digest: str):
    for step in recipe.get("step", []):
        output = step.get("output")
        if not output:
            continue
        full = os.path.join(comp_dir, output)
        if not os.path.isfile(full):
            continue
        try:
            if kernel._hash_file(full) == digest:
                return output
        except kernel.ClaimError:
            continue
    return None


# ------------------------------------------------------------ the DAG --

def claims(ws: str) -> list:
    """Every sealed claim in the workspace's registry, phase recomputed
    from verifiable state -- never read off a manifest bit."""
    sealed_root = os.path.join(ws, kernel.STORE, "sealed")
    out = []
    if not os.path.isdir(sealed_root):
        return out
    for name in sorted(os.listdir(sealed_root)):
        path = os.path.join(sealed_root, name)
        if not os.path.isdir(path):
            continue
        try:
            manifest = kernel.read_manifest(path)
        except kernel.ClaimError:
            continue
        try:
            ph = kernel.phase(path)
        except kernel.ClaimError:
            ph = "draft"
        out.append({"name": manifest["name"], "root": manifest["root"],
                    "phase": ph, "path": path})
    return out


def deps(ws: str) -> dict:
    """The dependency graph: every sealed claim, and whether each of its
    declared components currently resolves in the registry."""
    nodes = []
    for c in claims(ws):
        try:
            manifest = kernel.read_manifest(c["path"])
        except kernel.ClaimError:
            manifest = {}
        depends_on = []
        for link in (manifest.get("components") or []):
            name = link.get("component")
            comp_dir = find_component_dir(c["path"], ws, name)
            status = "missing"
            if comp_dir is not None:
                try:
                    comp_manifest = kernel.read_manifest(comp_dir)
                    status = "ok" if comp_manifest["root"] == link.get("root") else "stale"
                except kernel.ClaimError:
                    status = "broken"
            depends_on.append({"component": name, "input": link.get("input"),
                               "output": link.get("output"), "status": status})
        nodes.append({"name": c["name"], "depends_on": depends_on})
    return {"claims": nodes}


def pull(claim_dir: str, target_ws: str) -> dict:
    """Materialize a claim's bytes into a fresh workspace as a dependency."""
    os.makedirs(target_ws, exist_ok=True)
    shutil.copytree(claim_dir, target_ws, dirs_exist_ok=True)
    manifest = kernel.read_manifest(target_ws)
    return {"materialized": True, "root": manifest["root"]}


# --------------------------------------------------------- DAG rebuild --

def _rebuild_component(source, producer, into, ws, reuse, scratch, top):
    recipe = kernel.load_recipe(source)
    try:
        manifest = kernel.read_manifest(source)
    except kernel.ClaimError:
        manifest = {}
    components = manifest.get("components") or []

    by_name = {}
    for link in components:
        by_name.setdefault(link["component"], []).append(link)

    input_from = {}
    rebuilt = []
    comp_final_dirs = {}
    for name, links in by_name.items():
        comp_source = find_component_dir(source, ws, name)
        if comp_source is None:
            raise kernel.ClaimError(
                f"rebuild_chain refuses: missing declared component {name!r}")
        comp_scratch = os.path.join(scratch, f"comp-{len(comp_final_dirs)}-{name}")
        sub_root, sub_rebuilt = _rebuild_component(
            comp_source, producer, comp_scratch, ws, reuse, scratch, False)
        rebuilt.append({"component": name, "root": sub_root})
        rebuilt.extend(sub_rebuilt)
        comp_final_dirs[name] = comp_scratch
        for link in links:
            input_from[link["input"]] = os.path.join(comp_scratch, link["output"])

    outputs = _generated_outputs(recipe)
    if outputs and reuse and not top:
        result = kernel.rebuild(source, None, into, produce_from=source,
                                input_from=input_from or None)
    elif outputs:
        result = kernel.rebuild(source, producer, into,
                                input_from=input_from or None)
    else:
        result = kernel.rebuild(source, None, into, produce_from={},
                                input_from=input_from or None)

    for name, comp_scratch in comp_final_dirs.items():
        dest = os.path.join(into, kernel.STORE, "sealed", name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(comp_scratch, dest)
    if components:
        seal_with(into, components=components)
    return result["root"], rebuilt


def rebuild_chain(d: str, producer: str, into: str, *, ws: str = None,
                   reuse: bool = False) -> dict:
    """Regrow a composed claim leaf-first: every declared component is
    rebuilt (or, with `reuse`, threaded through from its sealed bytes)
    before `d`'s own producer runs, so the chain reproduces root and all."""
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError(f"refuses a non-empty rebuild target: {into!r}")
    scratch = tempfile.mkdtemp(prefix="reticuli-chain-")
    try:
        root, rebuilt = _rebuild_component(d, producer, into, ws, reuse, scratch, True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return {"root": root, "rebuilt_components": rebuilt}


# ------------------------------------------------------- signature chain --

def sign_root(d: str, ws: str = None) -> str:
    """One signature-chain node, folded bottom-up: `d`'s own root and
    build digest, over the SET of its components' own nodes. Refuses a
    chain root over an incomplete DAG rather than eliding the gap."""
    verified = kernel.verify(d)
    if not verified["ok"]:
        raise kernel.ClaimError(f"sign_root refuses: {d!r} does not verify")
    digest = kernel.build_digest(d)
    manifest = kernel.read_manifest(d)
    links = []
    for link in (manifest.get("components") or []):
        name = link.get("component")
        comp_dir = find_component_dir(d, ws, name)
        if comp_dir is None:
            raise kernel.ClaimError(
                f"sign_root refuses: missing declared component {name!r}")
        links.append(sign_root(comp_dir, ws))
    return kernel.sign_node(verified["root"], digest, links)


# -------------------------------------------------------------- deep audit --

def _audit_component_layer(d: str, comp_dir: str, links: list, name: str) -> dict:
    """Re-earn one component's OWN gate, on the bytes the dependent `d` is
    currently shipping for it -- never the component's own stored bytes."""
    produce_from = {l["output"]: os.path.join(d, l["input"]) for l in links}
    result = kernel.audit(comp_dir, produce_from=produce_from)
    return {"name": name, "root": result.get("root"), "ok": result["ok"],
            "status": result.get("verdict"),
            "bytes_from": sorted({l["input"] for l in links})}


def audit_deep(d: str) -> dict:
    """Walk the whole ancestor chain, not just the direct components: a
    broken grandparent, invisible to every gate above it, fails the
    composed verdict."""
    layers = []
    ok = True
    visited = set()

    def _walk(manifest_source):
        nonlocal ok
        try:
            manifest = kernel.read_manifest(manifest_source)
        except kernel.ClaimError:
            return
        by_name = {}
        for link in (manifest.get("components") or []):
            by_name.setdefault(link["component"], []).append(link)
        for name, links in by_name.items():
            if name in visited:
                continue
            visited.add(name)
            comp_dir = find_component_dir(manifest_source, None, name)
            bytes_from = sorted({l["input"] for l in links})
            if comp_dir is None:
                layers.append({"name": name, "status": "unresolved", "ok": False,
                              "root": None, "bytes_from": bytes_from})
                ok = False
                continue
            result = _audit_component_layer(d, comp_dir, links, name)
            layers.append(result)
            if not result["ok"]:
                ok = False
            _walk(comp_dir)

    _walk(d)
    return {"ok": ok, "layers": layers}


def crosscheck_deep(m1: str, m2: str, m3: str, mutants: int = None) -> dict:
    """The three-machine test, plus a deep audit of every directory leg:
    a forged layer that a shallow crosscheck cannot see still fails here."""
    kwargs = {} if mutants is None else {"mutants": mutants}
    base = kernel.crosscheck(m1, m2, m3, **kwargs)
    deep_results = {}
    deep_ok = True
    for label, path in (("M1", m1), ("M2", m2), ("M3", m3)):
        if os.path.isdir(path):
            dr = audit_deep(path)
            deep_results[label] = dr
            if not dr["ok"]:
                deep_ok = False
    result = dict(base)
    result["deep"] = deep_results
    result["satisfied"] = base["satisfied"] and deep_ok
    if not deep_ok:
        result["rejected"] = list(base.get("rejected", [])) + ["deep audit"]
    return result
