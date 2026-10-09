"""The registry: claim stores, content-addressed component links, and
DAG-aware rebuild (`spec/layers.md`).

A directory of sealed claims lives at `<ws>/.reticuli/sealed/<name>`; a
composed claim's OWN declared components live at the identical convention
rooted at its own directory (`<claim>/.reticuli/sealed/<name>`) -- one
convention serves both a shared workspace registry and a single claim's
local dependency store. `detect_components` links a pinned input to a
sealed claim by content, not by name. `rebuild_chain` regrows a composed
claim leaf-first, threading each component's realized bytes into any
`from`-declared produce step. `audit_deep` walks the whole chain, re-earning
every ancestor's own gate on the bytes actually shipped -- a forgery at any
depth fails the composed verdict. `sign_root` folds a signed identity
bottom-up over the same chain.

Stdlib only.
"""
import os
import shutil
import tempfile

from reticuli import _util, kernel

_SEALED = os.path.join(".reticuli", "sealed")


def _sealed_dir(root_dir: str, name: str) -> str:
    return _util.safe_path(root_dir, f".reticuli/sealed/{name}")


def _component_names(components) -> list:
    names = []
    for link in components or []:
        if link["component"] not in names:
            names.append(link["component"])
    return names


# -- detect_components: a content-addressed link, not a declared one. -----


def detect_components(ws: str, paths: list) -> list:
    """For each of `paths` (relative to `ws`), does its content match an
    output of some claim already sealed in `ws`'s registry? Returns one
    link per match: `{input, component, root, output}`.
    """
    sealed_root = os.path.join(ws, ".reticuli", "sealed")
    links = []
    if not os.path.isdir(sealed_root):
        return links

    candidates = []
    for name in sorted(os.listdir(sealed_root)):
        comp_dir = os.path.join(sealed_root, name)
        if not os.path.isdir(comp_dir):
            continue
        try:
            manifest = kernel.read_manifest(comp_dir)
            doc = kernel.load_recipe(comp_dir)
        except kernel.ClaimError:
            continue
        candidates.append((name, comp_dir, manifest, doc))

    for path in paths:
        full = os.path.join(ws, path)
        if not os.path.isfile(full):
            continue
        with open(full, "rb") as f:
            digest = _util.hash_bytes(f.read())
        for name, comp_dir, manifest, doc in candidates:
            for step in doc.get("step", []):
                output = step.get("output")
                if not output:
                    continue
                out_full = os.path.join(comp_dir, output)
                if not os.path.isfile(out_full):
                    continue
                with open(out_full, "rb") as f:
                    out_digest = _util.hash_bytes(f.read())
                if out_digest == digest:
                    links.append({"input": path, "component": name,
                                  "root": manifest["root"], "output": output})
    return links


# -- seal_with: seal, then attach exchange-layer residue. -----------------


def seal_with(d: str, components=None, proof=None) -> dict:
    """Seal `d` (computing its root fresh) and attach `components` and/or
    `proof` onto its manifest as residue -- neither is part of the root.
    """
    manifest = kernel.seal(d)
    if components is not None:
        manifest["components"] = components
    if proof is not None:
        manifest["proof"] = proof
    _util.write_json(os.path.join(d, kernel.MANIFEST), manifest)
    return manifest


# -- claims / deps: the registry's own view of what it holds. -------------


def claims(ws: str) -> list:
    """Every claim sealed in `ws`'s registry: `{name, root, phase}`."""
    sealed_root = os.path.join(ws, ".reticuli", "sealed")
    out = []
    if not os.path.isdir(sealed_root):
        return out
    for name in sorted(os.listdir(sealed_root)):
        d = os.path.join(sealed_root, name)
        if not os.path.isdir(d):
            continue
        try:
            manifest = kernel.read_manifest(d)
        except kernel.ClaimError:
            continue
        try:
            phase = kernel.phase(d)
        except kernel.ClaimError:
            phase = "broken"
        out.append({"name": manifest["name"], "root": manifest["root"], "phase": phase})
    return out


def deps(ws: str) -> dict:
    """The dependency edges of every claim in `ws`'s registry."""
    sealed_root = os.path.join(ws, ".reticuli", "sealed")
    claim_edges = []
    if os.path.isdir(sealed_root):
        for name in sorted(os.listdir(sealed_root)):
            d = os.path.join(sealed_root, name)
            if not os.path.isdir(d):
                continue
            try:
                manifest = kernel.read_manifest(d)
            except kernel.ClaimError:
                continue
            edges = []
            for comp_name in _component_names(manifest.get("components")):
                link = next(l for l in manifest["components"] if l["component"] == comp_name)
                comp_dir = os.path.join(sealed_root, comp_name)
                status = "missing"
                if os.path.isdir(comp_dir):
                    try:
                        comp_manifest = kernel.read_manifest(comp_dir)
                        status = "ok" if comp_manifest["root"] == link.get("root") else "stale"
                    except kernel.ClaimError:
                        status = "broken"
                edges.append({"component": comp_name, "status": status})
            claim_edges.append({"name": manifest["name"], "depends_on": edges})
    return {"claims": claim_edges}


# -- pull: a claim becomes a dependency of a fresh workspace. --------------


def pull(d: str, into: str) -> dict:
    """Materialize claim `d`'s declared content (recipe, inputs, every
    output present) flat into workspace `into`.
    """
    doc = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    os.makedirs(into, exist_ok=True)
    for rel in _util.claim_files(doc, d, include_generated=True):
        _util.copy_into(d, into, rel)
    return {"materialized": True, "name": manifest["name"], "root": manifest["root"]}


# -- rebuild_chain: DAG-aware rebuild, leaf first. -------------------------


def rebuild_chain(d: str, producer: str, into: str, ws=None, reuse: bool = False) -> dict:
    """Regrow composed claim `d` into fresh directory `into`: every
    declared component is realized first (rebuilt leaf-first with the same
    producer, or -- with `reuse=True` -- reused verbatim from the registry
    without ever asking the producer), then threaded into any
    `from`-declared produce step before `d` itself is regrown.
    """
    registry_root = ws if ws is not None else d
    doc = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    components = manifest.get("components") or []
    names = _component_names(components)

    produce_from = {}
    rebuilt_components = []
    staged = {}
    for name in names:
        comp_src = _sealed_dir(registry_root, name)
        if not os.path.isdir(comp_src):
            raise kernel.ClaimError(f"declared component {name!r} missing from the registry")
        if reuse:
            comp_bytes_dir = comp_src
        else:
            comp_scratch = tempfile.mkdtemp(prefix="reticuli-chain-")
            sub = rebuild_chain(comp_src, producer, comp_scratch, ws=registry_root, reuse=False)
            rebuilt_components.append({"component": name, "root": sub["root"]})
            rebuilt_components.extend(sub.get("rebuilt_components", []))
            comp_bytes_dir = comp_scratch
        staged[name] = comp_bytes_dir
        for step in doc.get("step", []):
            if step.get("kind") == "produce" and step.get("from") == name:
                produce_from[step["output"]] = os.path.join(comp_bytes_dir, step["output"])

    result = kernel.rebuild(d, producer, into, produce_from=produce_from or None)

    for name, bytes_dir in staged.items():
        dest = os.path.join(into, ".reticuli", "sealed", name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(bytes_dir, dest)

    seal_with(into, components=components)
    result["rebuilt_components"] = rebuilt_components
    return result


# -- sign_root: fold a signed identity bottom-up over the chain. ----------


def sign_root(d: str, ws=None) -> str:
    """Fold claim `d`'s root and build digest with the (recursively folded)
    signature-chain nodes of every component it declares.
    """
    registry_root = ws if ws is not None else d
    doc = kernel.load_recipe(d)
    r = kernel.root(doc, d)
    bd = kernel.build_digest(d)
    manifest = kernel.read_manifest(d)
    links = []
    for name in _component_names(manifest.get("components")):
        comp_dir = _sealed_dir(registry_root, name)
        if not os.path.isdir(comp_dir):
            raise kernel.ClaimError(f"declared component {name!r} missing from the registry")
        links.append(sign_root(comp_dir, registry_root))
    return kernel.sign_node(r, bd, links)


# -- audit_deep: the deep audit walks the whole chain. ---------------------


def audit_deep(d: str) -> dict:
    """Re-earn every ancestor's own gate, on the bytes `d` actually ships
    for it -- recursively, so a forgery at any depth fails the composed
    verdict (GATES COMPOSE, VERDICTS NEVER CARRY).
    """
    manifest = kernel.read_manifest(d)
    layers = []
    state = {"ok": True}
    seen = set()

    def walk(parent_dir, parent_links, shipped_at_parent):
        names = _component_names(parent_links)
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            own_links = [l for l in parent_links if l["component"] == name]
            bytes_from = sorted({l["input"] for l in own_links})
            comp_dir = os.path.join(parent_dir, ".reticuli", "sealed", name)
            if not os.path.isdir(comp_dir):
                layers.append({"name": name, "ok": False, "status": "unresolved",
                               "bytes_from": bytes_from})
                state["ok"] = False
                continue

            produce_from = {}
            for l in own_links:
                concrete = shipped_at_parent.get(l["input"], os.path.join(parent_dir, l["input"]))
                produce_from[l["output"]] = concrete

            try:
                sub = kernel.audit(comp_dir, shallow=True, produce_from=produce_from)
            except kernel.ClaimError as e:
                sub = {"ok": False, "verdict": "broken", "reason": str(e)}

            layer_ok = bool(sub.get("ok"))
            layers.append({"name": name, "ok": layer_ok, "status": sub.get("verdict", "?"),
                           "root": sub.get("root"), "bytes_from": bytes_from})
            if not layer_ok:
                state["ok"] = False

            try:
                comp_manifest = kernel.read_manifest(comp_dir)
                comp_links = comp_manifest.get("components") or []
            except kernel.ClaimError:
                comp_links = []
            if comp_links:
                walk(comp_dir, comp_links, produce_from)

    walk(d, manifest.get("components") or [], {})
    return {"ok": state["ok"], "layers": layers}


# -- crosscheck_deep: the three-machine test, plus a deep audit per leg. --


def crosscheck_deep(m1: str, m2: str, m3: str) -> dict:
    """`kernel.crosscheck`, strengthened: every directory leg must also
    re-earn its whole component chain, not just its own gates.
    """
    base = kernel.crosscheck(m1, m2, m3)
    if not base["satisfied"]:
        return base
    deep_reports = {}
    deep_ok = True
    for label, leg in (("M1", m1), ("M2", m2), ("M3", m3)):
        if os.path.isdir(leg):
            rep = audit_deep(leg)
            deep_reports[label] = rep
            if not rep["ok"]:
                deep_ok = False
    result = dict(base)
    result["deep"] = deep_reports
    result["satisfied"] = base["satisfied"] and deep_ok
    return result
