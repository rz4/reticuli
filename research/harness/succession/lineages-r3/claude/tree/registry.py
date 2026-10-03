"""Claims meeting claims: the registry (spec/layers.md, "exchange").

A workspace is a plain directory holding a `.reticuli/sealed/<name>/`
claim store (`claims`, `deps`, `detect_components`, `pull`); a composed
claim additionally carries its own layered components self-contained,
under its own `.reticuli/sealed/<name>/` (`seal_with`, `rebuild_chain`,
`audit_deep`, `crosscheck_deep`). `sign_root` folds the bottom-anchored
signature chain over either shape, keyed by the same `ws` convention.

Nothing here reaches into a kernel private: every identity, gate, and
recipe fact is read through `reticuli.kernel`'s pinned surface.
"""
import json
import os
import shutil
import subprocess

from reticuli import _util
from reticuli import kernel


def _sealed_root(base: str) -> str:
    return os.path.join(base, kernel.STORE, "sealed")


def _component_dir(name: str, d: str, ws=None) -> str:
    base = ws if ws else d
    return os.path.join(_sealed_root(base), name)


# ===========================================================================
# detect_components: content-addressed links between a workspace's loose
# files and the sealed claims already in its store.
# ===========================================================================


def detect_components(ws: str, candidates) -> list:
    """Every content-addressed link between a file named in `candidates`
    (relative to `ws`) and a declared file of a sealed claim in `ws`'s
    store: same bytes, so the candidate is really that claim's output.
    """
    sealed_root = _sealed_root(ws)
    links = []
    if not os.path.isdir(sealed_root):
        return links

    cand_hashes = {}
    for cand in candidates:
        path = os.path.join(ws, cand)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                cand_hashes[cand] = _util.hash_bytes(f.read())

    for name in sorted(os.listdir(sealed_root)):
        comp_dir = os.path.join(sealed_root, name)
        if not os.path.isdir(comp_dir):
            continue
        try:
            manifest = kernel.read_manifest(comp_dir)
            parsed = kernel.load_recipe(comp_dir)
        except kernel.ClaimError:
            continue

        declared = set(_util.declared_inputs(parsed))
        for step in parsed.get("step", []):
            declared.add(step["output"])

        for cand, cand_hash in cand_hashes.items():
            for out_name in declared:
                out_path = os.path.join(comp_dir, out_name)
                if not os.path.isfile(out_path):
                    continue
                with open(out_path, "rb") as f:
                    out_hash = _util.hash_bytes(f.read())
                if out_hash == cand_hash:
                    links.append({"input": cand, "component": name,
                                 "root": manifest["root"], "output": out_name})
                    break
    return links


# ===========================================================================
# seal_with: seal, then attach exchange-layer residue (components, proof)
# the kernel manifest itself has no opinion about.
# ===========================================================================


def seal_with(d: str, components=None, proof=None) -> dict:
    """Seal `d` and attach `components` and/or `proof` onto its manifest,
    alongside the identity `kernel.seal` already computed.
    """
    manifest = kernel.seal(d)
    extra = {}
    if components is not None:
        extra["components"] = components
    if proof is not None:
        extra["proof"] = proof
    if extra:
        manifest = dict(manifest)
        manifest.update(extra)
        _util.write_json(os.path.join(d, kernel.MANIFEST), manifest)
    return manifest


# ===========================================================================
# claims / deps: the store's inventory and its dependency graph.
# ===========================================================================


def claims(ws: str) -> list:
    """Every sealed claim in `ws`'s store: name, root, and phase."""
    sealed_root = _sealed_root(ws)
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
            ph = kernel.phase(d)
        except kernel.ClaimError:
            ph = "draft"
        out.append({"name": manifest.get("name", name), "root": manifest.get("root"),
                    "phase": ph})
    return out


def deps(ws: str) -> dict:
    """The DAG over `ws`'s store: each claim and the status of every
    component it declares (`ok` when the link resolves and verifies,
    `broken` when it resolves but fails identity, `missing` otherwise).
    """
    out = []
    for c in claims(ws):
        name = c["name"]
        d = os.path.join(_sealed_root(ws), name)
        try:
            manifest = kernel.read_manifest(d)
        except kernel.ClaimError:
            manifest = {}
        edges = []
        for comp in manifest.get("components", []):
            comp_dir = os.path.join(_sealed_root(ws), comp["component"])
            status = "missing"
            if os.path.isdir(comp_dir):
                try:
                    status = "ok" if kernel.verify(comp_dir)["ok"] else "broken"
                except kernel.ClaimError:
                    status = "broken"
            edges.append({"component": comp["component"], "status": status})
        out.append({"name": name, "depends_on": edges})
    return {"claims": out}


# ===========================================================================
# pull: a sealed claim becomes a dependency of a fresh workspace.
# ===========================================================================


def pull(d: str, into: str) -> dict:
    """Materialize `d`'s declared bytes (recipe, inputs, every present
    step output) and its manifest into `into`.
    """
    parsed = kernel.load_recipe(d)
    names = {_util.recipe_name(d), kernel.MANIFEST}
    names.update(_util.declared_inputs(parsed))
    for step in parsed.get("step", []):
        names.add(step["output"])
    _util.copy_into(d, into, sorted(names))
    manifest = kernel.read_manifest(d)
    return {"materialized": True, "root": manifest["root"], "name": manifest.get("name")}


# ===========================================================================
# sign_root: the bottom-anchored signature chain, folded over the DAG.
# ===========================================================================


def sign_root(d: str, ws=None) -> str:
    """The signature-chain node for `d`: a fold of its own root and build
    digest with the folded nodes of every component it declares, found
    under `ws`'s store when given, or self-contained under `d`'s own
    store otherwise. Refuses to fold over a declared component that
    cannot be found.
    """
    vr = kernel.verify(d)
    digest = kernel.build_digest(d)
    manifest = kernel.read_manifest(d)
    links = []
    for comp in manifest.get("components", []):
        comp_dir = _component_dir(comp["component"], d, ws)
        if not os.path.isdir(comp_dir):
            raise kernel.ClaimError(f"missing declared component {comp['component']!r}")
        links.append(sign_root(comp_dir, ws))
    return kernel.sign_node(vr["root"], digest, links)


# ===========================================================================
# rebuild_chain: the DAG-aware rebuild. Leaf components first, threaded
# into the dependent via its declared inputs or its `from` produce steps.
# ===========================================================================


def rebuild_chain(d: str, producer: str, into: str, ws=None, reuse: bool = False) -> dict:
    """Regrow `d`'s chain into `into`: every declared component rebuilt
    (or, with `reuse`, reused verbatim from its sealed bytes) before `d`
    itself, so a dependent's own produce step never has to repay what a
    component has already earned.
    """
    into_abs = os.path.abspath(into)
    if os.path.isdir(into_abs) and os.listdir(into_abs):
        raise kernel.ClaimError(f"rebuild target {into!r} already holds bytes")
    os.makedirs(into_abs, exist_ok=True)

    parsed = kernel.load_recipe(d)
    missing = kernel.preflight(parsed)
    if missing:
        raise kernel.ClaimError(f"environment: missing requirement(s) {missing}")

    manifest = kernel.read_manifest(d)
    links = manifest.get("components", [])

    declared = set(_util.declared_inputs(parsed))
    from_map = {s["output"]: s.get("from") for s in parsed.get("step", [])
                if s.get("kind") == "produce" and "from" in s}

    rebuilt_components = []
    new_links = []
    input_overrides = {}
    from_bytes = {}

    for link in links:
        comp_name = link["component"]
        comp_dir = _component_dir(comp_name, d, ws)
        if not os.path.isdir(comp_dir):
            raise kernel.ClaimError(f"missing declared component {comp_name!r}")
        output_name = link.get("output", comp_name)
        target_name = link.get("input")
        comp_into = os.path.join(into_abs, kernel.STORE, "sealed", comp_name)

        if reuse:
            shutil.copytree(comp_dir, comp_into)
            comp_root = kernel.verify(comp_into)["root"]
            src_path = os.path.join(comp_into, output_name)
        else:
            comp_result = rebuild_chain(comp_dir, producer, comp_into, ws=ws, reuse=reuse)
            rebuilt_components.extend(comp_result["rebuilt_components"])
            comp_root = comp_result["root"]
            src_path = os.path.join(comp_into, output_name)

        rebuilt_components.append({"component": comp_name, "root": comp_root})
        new_links.append({"input": target_name, "component": comp_name,
                          "root": comp_root, "output": output_name})

        if target_name in declared:
            input_overrides[target_name] = src_path
        if target_name in from_map:
            from_bytes[target_name] = src_path

    for name in declared:
        src = input_overrides.get(name, os.path.join(d, name))
        dest = os.path.join(into_abs, name)
        os.makedirs(os.path.dirname(dest) or into_abs, exist_ok=True)
        shutil.copy2(src, dest)

    recipe_file = _util.recipe_name(d)
    shutil.copy2(os.path.join(d, recipe_file), os.path.join(into_abs, recipe_file))

    for output_name, src in from_bytes.items():
        dest = os.path.join(into_abs, output_name)
        os.makedirs(os.path.dirname(dest) or into_abs, exist_ok=True)
        shutil.copy2(src, dest)

    remaining = [s for s in parsed.get("step", [])
                 if s.get("kind") == "produce"
                 and s.get("class", "generated") == "generated"
                 and "from" not in s]

    if remaining:
        env = dict(os.environ)
        env["RETICULI_CLAIM"] = into_abs
        if len(remaining) == 1:
            env["RETICULI_OUTPUT"] = os.path.join(into_abs, remaining[0]["output"])
        env["RETICULI_OUTPUTS"] = json.dumps(
            [os.path.join(into_abs, s["output"]) for s in remaining])
        result = subprocess.run(producer, shell=True, cwd=into_abs, env=env,
                                capture_output=True, timeout=600)
        if result.returncode != 0:
            raise kernel.ClaimError(
                "producer failed: " + result.stderr.decode("utf-8", "replace")[-500:])

    for step in parsed.get("step", []):
        if step.get("kind") != "gate":
            continue
        outcome = kernel.run_gate(step["run"], into_abs, parsed)
        if outcome["status"] != "ok":
            raise kernel.ClaimError(f"gate {step['output']!r} did not pass: {outcome['status']}")

    manifest_out = seal_with(into_abs, components=new_links or None)
    return {"root": manifest_out["root"], "rebuilt_components": rebuilt_components}


# ===========================================================================
# audit_deep / crosscheck_deep: re-earning a component's OWN gate on the
# dependent's shipped bytes, so a forged layer the dependent's own gate
# cannot see still fails the chain.
# ===========================================================================


def audit_deep(d: str) -> dict:
    """Re-earn every declared component's OWN gate, run fresh against the
    bytes `d` actually ships for it -- never the component's own stored
    copy. A component the manifest declares but `d` cannot resolve (no
    sealed copy, no shipped bytes) is a failed layer, `unresolved`.
    """
    manifest = kernel.read_manifest(d)
    layers = []
    ok_all = True
    for comp in manifest.get("components", []):
        name = comp["component"]
        comp_dir = _component_dir(name, d, None)
        shipped = os.path.join(d, comp["input"]) if comp.get("input") else None
        entry = {"name": name, "root": comp.get("root")}
        if not os.path.isdir(comp_dir) or not shipped or not os.path.isfile(shipped):
            entry.update(ok=False, status="unresolved")
            ok_all = False
        else:
            aud = kernel.audit(comp_dir, produce_from={comp["output"]: shipped})
            entry.update(ok=bool(aud.get("ok")), status="checked", bytes_from=[comp["input"]])
            if not entry["ok"]:
                ok_all = False
        layers.append(entry)
    return {"ok": ok_all, "layers": layers}


def crosscheck_deep(m1: str, m2: str, m3: str) -> dict:
    """`kernel.crosscheck`, strengthened: every directory leg must also
    re-earn its declared components deep (`audit_deep`), so a layer
    forged beneath a passing shallow gate still fails the chain.
    """
    base = kernel.crosscheck(m1, m2, m3)
    deep_ok = True
    for leg in (m1, m2, m3):
        if os.path.isdir(leg):
            if not audit_deep(leg).get("ok", True):
                deep_ok = False
    result = dict(base)
    result["deep_ok"] = deep_ok
    result["satisfied"] = base["satisfied"] and deep_ok
    return result
