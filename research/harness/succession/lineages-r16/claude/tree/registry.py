"""The claim registry: claims meeting claims.

A **store** is a `.reticuli/sealed/<name>/` directory holding one or more
sealed claims -- either a shared workspace (`ws`) that several claims sit
side by side in, or a single claim's own nested store of the components it
was composed from. Both are read the same way (`claims`), which is why a
claim's own directory can double as a miniature workspace for its
dependencies.

`detect_components` finds a content-addressed dependency: a claim's pinned
input whose bytes equal some sealed claim's own output. `seal_with` layers
that link -- or a recorded proof -- onto the kernel's plain `{name, root}`
manifest, as residue that never enters the root. `rebuild_chain` regrows a
composed claim leaf-first: each declared component is rebuilt (or, with
`reuse=True`, reused as sealed) before the claim itself, which is handed
the fresh bytes through the kernel's own `produce_from`/`input_from`
rebuild hooks depending on whether the dependency is code shipped via a
`from` produce step or a pinned input that merely happens to match a
component's output.

`audit_deep` is the chain the kernel's own (shallow) `audit` cannot see:
it re-earns not just a claim's own gates but, recursively, every ancestor's
gates too -- each ancestor judged on whatever bytes were actually shipped
for it, threaded transitively down the chain, so a forged grandparent
cannot hide behind an honest parent. `crosscheck_deep` folds that into the
three-machine test.
"""
import os
import shutil
import tempfile

from reticuli import kernel
from reticuli import _util


# --------------------------------------------------------------- the store
def claims(ws: str) -> list:
    """Every sealed claim in `ws`'s store: `{name, root, phase, path}`."""
    sealed_root = os.path.join(ws, kernel.STORE, "sealed")
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
        out.append({"name": manifest["name"], "root": manifest["root"],
                     "phase": kernel.phase(d), "path": d})
    return out


def deps(ws: str) -> dict:
    """The DAG over `ws`'s store: each claim's declared components, and
    whether each one is reachable in the registry and roots the same."""
    out = []
    for c in claims(ws):
        try:
            manifest = kernel.read_manifest(c["path"])
        except kernel.ClaimError:
            manifest = {}
        depends_on = []
        for link in manifest.get("components") or []:
            comp_name = link.get("component")
            comp_dir = (os.path.join(ws, kernel.STORE, "sealed", comp_name)
                        if comp_name else None)
            status = "missing"
            if comp_dir and os.path.isdir(comp_dir):
                try:
                    comp_manifest = kernel.read_manifest(comp_dir)
                    status = ("ok" if comp_manifest["root"] == link.get("root")
                               else "root_mismatch")
                except kernel.ClaimError:
                    status = "missing"
            depends_on.append({"component": comp_name, "status": status})
        out.append({"name": c["name"], "depends_on": depends_on})
    return {"claims": out}


def detect_components(ws: str, paths: list) -> list:
    """Links from `paths` (relative to `ws`) to any sealed claim in `ws`'s
    store whose own step output has the same bytes -- a content-addressed
    dependency, found without either side declaring the other by name."""
    links = []
    for c in claims(ws):
        comp_dir = c["path"]
        try:
            recipe = kernel.load_recipe(comp_dir)
        except kernel.ClaimError:
            continue
        for step in recipe.get("step", []):
            output = step.get("output")
            if not output:
                continue
            out_path = os.path.join(comp_dir, output)
            if not os.path.isfile(out_path):
                continue
            try:
                out_hash = kernel._hash_file(out_path)
            except kernel.ClaimError:
                continue
            for path in paths:
                full = os.path.join(ws, path)
                if not os.path.isfile(full):
                    continue
                try:
                    in_hash = kernel._hash_file(full)
                except kernel.ClaimError:
                    continue
                if in_hash == out_hash:
                    links.append({"input": path, "component": c["name"],
                                  "root": c["root"], "output": output})
    return links


def seal_with(d: str, *, components=None, proof=None) -> dict:
    """Seal `d` and layer `components`/`proof` onto its manifest as residue
    (never the root): the kernel's own `{name, root}`, plus whichever of
    these this call supplies, plus whatever it leaves untouched from
    before."""
    try:
        old = kernel.read_manifest(d)
    except kernel.ClaimError:
        old = {}
    manifest = dict(kernel.seal(d))
    comps = components if components is not None else old.get("components")
    pr = proof if proof is not None else old.get("proof")
    if comps is not None:
        manifest["components"] = comps
    if pr is not None:
        manifest["proof"] = pr
    _util.write_json(os.path.join(d, kernel.MANIFEST), manifest)
    return manifest


def pull(src: str, dest: str) -> dict:
    """Materialize `src` -- every byte, trusted as-is -- at `dest`, so it
    becomes a dependency a fresh workspace can use directly."""
    if not os.path.isdir(src):
        raise kernel.ClaimError(f"pull: no such claim {src!r}")
    for entry in sorted(os.listdir(src)):
        s = os.path.join(src, entry)
        t = os.path.join(dest, entry)
        if os.path.isdir(s):
            shutil.copytree(s, t, dirs_exist_ok=True)
        elif os.path.isfile(s):
            _util.copy_into(s, t)
    manifest = kernel.read_manifest(dest)
    return {"materialized": True, "root": manifest["root"], "name": manifest["name"]}


# ------------------------------------------------------------- rebuilding
def _component_dir(claim_dir: str, ws, name: str) -> str:
    if ws is not None:
        candidate = os.path.join(ws, kernel.STORE, "sealed", name)
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(claim_dir, kernel.STORE, "sealed", name)


def _needs_producer(recipe: dict) -> bool:
    return any(s.get("kind") == "produce" and s.get("class", "generated") == "generated"
               and "from" not in s for s in recipe.get("step", []))


def rebuild_chain(d: str, producer, into: str, *, ws=None, reuse: bool = False) -> dict:
    """Regrow the whole chain `d` depends on, leaf-first, into `into`.

    Each declared component is rebuilt (`reuse=False`) or reused as its
    sealed bytes (`reuse=True`), then threaded into `d`'s own rebuild as
    either `produce_from` (a `from` produce step: shipped code) or
    `input_from` (a pinned input that merely content-matches a component's
    output) -- the kernel's own hooks, so the composed claim's own identity
    is earned exactly as `kernel.rebuild` earns any other.
    """
    into = os.path.abspath(into)
    manifest = kernel.read_manifest(d)
    links = manifest.get("components") or []
    recipe = kernel.load_recipe(d)

    by_component = {}
    for link in links:
        by_component.setdefault(link["component"], []).append(link)

    rebuilt_components = []
    comp_targets = {}
    for comp_name, comp_links in by_component.items():
        comp_src = _component_dir(d, ws, comp_name)
        if reuse:
            comp_root = kernel.read_manifest(comp_src)["root"]
            comp_outputs_dir = comp_src
        else:
            comp_recipe = kernel.load_recipe(comp_src)
            child_producer = producer if _needs_producer(comp_recipe) else None
            comp_scratch = tempfile.mkdtemp()
            sub = rebuild_chain(comp_src, child_producer, comp_scratch, ws=ws, reuse=False)
            rebuilt_components.extend(sub["rebuilt_components"])
            comp_root = sub["root"]
            comp_outputs_dir = comp_scratch
        comp_targets[comp_name] = comp_outputs_dir
        rebuilt_components.append({"component": comp_name, "root": comp_root})

    produce_from, input_from = {}, {}
    for comp_name, comp_links in by_component.items():
        comp_outputs_dir = comp_targets[comp_name]
        for link in comp_links:
            output_name, input_name = link["output"], link["input"]
            source_path = os.path.join(comp_outputs_dir, output_name)
            is_from = any(
                s.get("kind") == "produce" and s.get("output") == input_name
                and s.get("from") == comp_name
                for s in recipe.get("step", [])
            )
            if is_from:
                produce_from[input_name] = source_path
            else:
                input_from[input_name] = source_path

    result = kernel.rebuild(d, producer, into, produce_from=produce_from,
                             input_from=input_from)

    if links:
        for comp_name, comp_outputs_dir in comp_targets.items():
            dest = os.path.join(into, kernel.STORE, "sealed", comp_name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copytree(comp_outputs_dir, dest)
        root_by_name = {c["component"]: c["root"] for c in rebuilt_components}
        registry_links = [
            {"input": l["input"], "component": l["component"],
             "root": root_by_name.get(l["component"], l.get("root")),
             "output": l["output"]}
            for l in links
        ]
        seal_with(into, components=registry_links)

    out = dict(result)
    out["rebuilt_components"] = rebuilt_components
    return out


def sign_root(d: str, ws) -> str:
    """One signature-chain node folded bottom-up over the DAG: the root and
    build digest of `d`, over the SET of its components' own nodes. A
    declared component the registry cannot reach refuses the fold rather
    than eliding it."""
    manifest = kernel.read_manifest(d)
    root = manifest["root"]
    build_dig = kernel.build_digest(d)
    links = manifest.get("components") or []
    child_signatures = []
    for link in links:
        comp_name = link["component"]
        comp_dir = os.path.join(ws, kernel.STORE, "sealed", comp_name)
        if not os.path.isdir(comp_dir):
            raise kernel.ClaimError(
                f"sign_root: declared component {comp_name!r} missing from the registry")
        child_signatures.append(sign_root(comp_dir, ws))
    return kernel.sign_node(root, build_dig, child_signatures)


# -------------------------------------------------------------- deep audit
def _layers(d: str, inherited: dict) -> list:
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        return []
    links = manifest.get("components") or []
    by_component = {}
    for link in links:
        by_component.setdefault(link["component"], []).append(link)

    layers = []
    for comp_name, comp_links in by_component.items():
        comp_dir = os.path.join(d, kernel.STORE, "sealed", comp_name)
        produce_from, resolved = {}, {}
        for link in comp_links:
            input_name, output_name = link["input"], link["output"]
            bytes_path = inherited.get(input_name, os.path.join(d, input_name))
            produce_from[output_name] = bytes_path
            resolved[output_name] = bytes_path

        if not os.path.isdir(comp_dir):
            layers.append({"name": comp_name, "status": "unresolved", "ok": False,
                           "root": None, "bytes_from": sorted(produce_from)})
            continue
        try:
            result = kernel.audit(comp_dir, produce_from=produce_from)
        except kernel.ClaimError:
            layers.append({"name": comp_name, "status": "error", "ok": False,
                           "root": None, "bytes_from": sorted(produce_from)})
            continue

        layers.append({
            "name": comp_name, "status": "ok" if result["ok"] else "broken",
            "ok": result["ok"], "root": result["root"],
            "bytes_from": sorted(produce_from),
        })
        layers.extend(_layers(comp_dir, resolved))
    return layers


def audit_deep(d: str) -> dict:
    """Re-earn every gate in `d`'s whole lineage, cold: `d`'s own gates,
    then every ancestor's, each judged on the bytes actually shipped for
    it. An unresolvable ancestor is a failed one."""
    own = kernel.audit(d)
    layers = _layers(d, {})
    ok = own["ok"] and all(layer["ok"] for layer in layers)
    return {"ok": ok, "root": own.get("root"), "own": own, "layers": layers}


def crosscheck_deep(m1: str, m2: str, m3: str, **kwargs) -> dict:
    """The three-machine test, folded with the deep audit on every
    directory leg: a forged ancestor that a shallow crosscheck cannot see
    fails the composed verdict."""
    result = dict(kernel.crosscheck(m1, m2, m3, **kwargs))
    deep_ok = True
    deep_reports = {}
    for label, path in (("M1", m1), ("M2", m2), ("M3", m3)):
        if os.path.isdir(path):
            report = audit_deep(path)
            deep_reports[label] = report
            if not report["ok"]:
                deep_ok = False
        else:
            deep_reports[label] = None
    result["deep"] = deep_reports
    result["satisfied"] = bool(result.get("satisfied")) and deep_ok
    return result
