"""registry.py: the exchange layer's claim store -- content-addressed
component links, the DAG they form, DAG-aware rebuild, and the deep
audit that walks the whole chain.

A sealed claim lives at `<ws>/.reticuli/sealed/<name>/` (or, for a
self-contained composed claim, nested at `<claim>/.reticuli/sealed/<name>/`
-- both are the same convention, just rooted differently). A manifest's
`components` list is the provenance link to each one: `{"input", "component",
"root", "output"}`, read back by every verb here; nothing above the
kernel's own `seal`/`verify`/`audit`/`rebuild` is trusted beyond what this
module re-derives from bytes on disk.
"""
import os
import tempfile

from . import kernel
from . import _util


def _component_dir(d: str, ws: str, name: str):
    """Resolve a declared component's directory: prefer `ws`'s registry
    when a workspace is given, else the claim's own self-contained store."""
    if ws:
        candidate = os.path.join(ws, kernel.STORE, "sealed", name)
        if os.path.isdir(candidate):
            return candidate
    candidate = os.path.join(d, kernel.STORE, "sealed", name)
    if os.path.isdir(candidate):
        return candidate
    return None


# =====================================================================
# content-addressed linking
# =====================================================================

def detect_components(ws: str, candidates: list) -> list:
    """Every candidate path under `ws` whose bytes match some output of
    a sealed component already registered in `ws` -- a content-addressed
    dependency link, found by comparing hashes, never by name."""
    links = []
    sealed_dir = os.path.join(ws, kernel.STORE, "sealed")
    if not os.path.isdir(sealed_dir):
        return links
    for name in sorted(os.listdir(sealed_dir)):
        comp_dir = os.path.join(sealed_dir, name)
        if not os.path.isdir(comp_dir):
            continue
        try:
            manifest = kernel.read_manifest(comp_dir)
            parsed = kernel.load_recipe(comp_dir)
        except kernel.ClaimError:
            continue
        for step in parsed.get("step", []):
            output = step.get("output")
            if not output:
                continue
            out_path = os.path.join(comp_dir, output)
            if not os.path.isfile(out_path):
                continue
            out_hash = _util.hash_bytes(out_path)
            for cand in candidates:
                cand_path = os.path.join(ws, cand)
                if not os.path.isfile(cand_path):
                    continue
                if _util.hash_bytes(cand_path) == out_hash:
                    links.append({"input": cand, "component": name,
                                  "root": manifest["root"], "output": output})
    return links


def seal_with(d: str, *, components: list = None, proof: dict = None) -> dict:
    """`kernel.seal`, with the registry's own provenance residue laid on
    top: the component links a claim was sealed with, and (once earned)
    its recorded proof. Neither is identity-bearing."""
    manifest = kernel.seal(d)
    full = dict(manifest)
    if components is not None:
        full["components"] = components
    if proof is not None:
        full["proof"] = proof
    _util.write_json(os.path.join(d, kernel.MANIFEST), full)
    return full


# =====================================================================
# the claim store and its DAG
# =====================================================================

def claims(ws: str) -> list:
    """Every sealed claim registered in `ws`, with its verifiable phase
    -- never a manifest bit taken on faith."""
    sealed_dir = os.path.join(ws, kernel.STORE, "sealed")
    out = []
    if not os.path.isdir(sealed_dir):
        return out
    for name in sorted(os.listdir(sealed_dir)):
        d = os.path.join(sealed_dir, name)
        if not os.path.isdir(d):
            continue
        try:
            manifest = kernel.read_manifest(d)
        except kernel.ClaimError:
            continue
        try:
            ph = kernel.phase(d)
        except kernel.ClaimError:
            ph = "draft"
        out.append({"name": manifest["name"], "root": manifest["root"],
                    "phase": ph, "path": d})
    return out


def deps(ws: str) -> dict:
    """The claim store's dependency DAG: every claim's declared
    components, and whether each link still resolves against the
    registry's current state."""
    entries = claims(ws)
    by_name = {c["name"]: c for c in entries}
    out = []
    for c in entries:
        manifest = kernel.read_manifest(c["path"])
        components = manifest.get("components") or []
        depends_on = []
        for link in components:
            comp = by_name.get(link["component"])
            if comp is None:
                status = "missing"
            elif comp["root"] == link["root"]:
                status = "ok"
            else:
                status = "broken"
            depends_on.append({"component": link["component"], "status": status})
        out.append({"name": c["name"], "depends_on": depends_on})
    return {"claims": out}


# =====================================================================
# DAG-aware rebuild: leaves first, provenance preserved
# =====================================================================

def rebuild_chain(d: str, producer: str, into: str, *, ws: str = None,
                   reuse: bool = False) -> dict:
    """Rebuild claim `d` into `into`, regrowing every declared component
    first (leaf first) unless `reuse` lets a `from`-sourced component's
    already-sealed bytes stand in for its own regrowth -- the
    incremental, layered build."""
    parsed = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    components = manifest.get("components") or []
    from_steps = {s["from"]: s["output"] for s in parsed.get("step", [])
                  if s.get("kind") == "produce" and "from" in s}

    rebuilt_components = []
    comp_sources = {}
    seen = set()
    for link in components:
        name = link["component"]
        if name in seen:
            continue
        seen.add(name)
        comp_dir = _component_dir(d, ws, name)
        if comp_dir is None:
            raise kernel.ClaimError(
                f"rebuild_chain: declared component {name!r} not found")
        if name in from_steps and reuse:
            comp_sources[name] = comp_dir
        else:
            scratch = tempfile.mkdtemp(prefix=f"reticuli-chain-{name}-")
            sub = rebuild_chain(comp_dir, producer, scratch, ws=ws, reuse=reuse)
            rebuilt_components.append({"component": name, "root": sub["root"]})
            comp_sources[name] = scratch

    produce_from = {}
    for name, src_dir in comp_sources.items():
        if name in from_steps:
            output = from_steps[name]
            produce_from[output] = _util.safe_path(src_dir, output)

    kernel.rebuild(d, producer, into, produce_from=produce_from or None)

    manifest_into = kernel.read_manifest(into)
    full = dict(manifest_into)
    full["components"] = components
    _util.write_json(os.path.join(into, kernel.MANIFEST), full)

    for name, src_dir in comp_sources.items():
        _util.copy_into(src_dir, os.path.join(into, kernel.STORE, "sealed", name))

    return {"root": full["root"], "name": full["name"],
            "rebuilt_components": rebuilt_components}


def pull(d: str, ws: str) -> dict:
    """A claim becomes a dependency of a fresh workspace: its declared
    bytes materialize directly into `ws`."""
    manifest = kernel.read_manifest(d)
    _util.copy_into(d, ws)
    return {"materialized": True, "name": manifest["name"], "root": manifest["root"]}


# =====================================================================
# the signature chain: a bottom-anchored fold over the DAG
# =====================================================================

def sign_root(d: str, ws: str = None) -> str:
    """The signature-chain node for `d`: its own root/build-digest,
    folded with every declared component's own node, bottom-up. A
    declared component the registry cannot find refuses the fold."""
    manifest = kernel.read_manifest(d)
    root = manifest["root"]
    digest = kernel.build_digest(d)
    links = []
    for link in manifest.get("components") or []:
        comp_dir = _component_dir(d, ws, link["component"])
        if comp_dir is None:
            raise kernel.ClaimError(
                f"sign_root: declared component {link['component']!r} not found")
        links.append(sign_root(comp_dir, ws))
    return kernel.sign_node(root, digest, links)


# =====================================================================
# the deep audit: re-earn every ancestor's gate, on shipped bytes
# =====================================================================

def audit_deep(d: str) -> dict:
    """Walk every ancestor of `d` (self-contained components, nested
    `.reticuli/sealed/<name>` all the way down) and re-run EACH
    component's own gate, substituting the bytes `d` actually ships for
    whatever the component produced -- GATES COMPOSE, VERDICTS NEVER
    CARRY. A declared-but-missing ancestor is a failed layer, not a
    skipped one."""
    layers = []
    _collect_layers(d, d, layers, set())
    ok = all(layer["ok"] for layer in layers)
    return {"ok": ok, "layers": layers}


def _collect_layers(top: str, current: str, layers: list, visited: set) -> None:
    try:
        manifest = kernel.read_manifest(current)
    except kernel.ClaimError:
        return
    components = manifest.get("components") or []
    by_name = {}
    for link in components:
        by_name.setdefault(link["component"], []).append(link["output"])

    for name, outputs in by_name.items():
        if name in visited:
            continue
        visited.add(name)
        comp_dir = os.path.join(current, kernel.STORE, "sealed", name)
        bytes_from = sorted(set(outputs))
        layer = {"name": name, "bytes_from": bytes_from}
        if not os.path.isdir(comp_dir):
            layer.update(status="unresolved", ok=False, root=None)
            layers.append(layer)
            continue
        produce_from = {}
        for out in bytes_from:
            src = os.path.join(top, out)
            if os.path.isfile(src):
                produce_from[out] = src
        try:
            comp_manifest = kernel.read_manifest(comp_dir)
            result = kernel.audit(comp_dir, produce_from=produce_from or None)
        except kernel.ClaimError:
            layer.update(status="unresolved", ok=False, root=None)
            layers.append(layer)
            continue
        status = result.get("verdict") or ("ok" if result["ok"] else "mismatch")
        layer.update(status=status, ok=result["ok"], root=comp_manifest.get("root"))
        layers.append(layer)
        _collect_layers(top, comp_dir, layers, visited)


# =====================================================================
# crosscheck_deep: the three-machine test, with every directory leg
# re-earned all the way down its chain, not just at its own gate.
# =====================================================================

def crosscheck_deep(m1: str, m2: str, m3: str, *, mutants: int = None) -> dict:
    result = kernel.crosscheck(m1, m2, m3, mutants=mutants)
    if not result["satisfied"]:
        return result
    for leg in (m1, m2, m3):
        if os.path.isdir(leg) and not audit_deep(leg)["ok"]:
            rejected = list(result["rejected"]) + ["deep"]
            return dict(result, satisfied=False, verdict="reject", rejected=rejected)
    return result
