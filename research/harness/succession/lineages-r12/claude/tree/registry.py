"""The claim store: content-addressed component links, the DAG, and the
registry-aware verbs built on top of it (`spec/layers.md`'s exchange layer).

A *component link* is `{"input", "component", "root", "output"}`: `input`
names a path within the claim that carries the link (either a pinned input
whose bytes happen to match a sealed component's output -- content-addressed
reuse found by `detect_components` -- or a `produce` step's own output,
shipped from that component via its `from` key); `component` and `root` name
what it links to; `output` is the name under the component's own directory.
`seal_with` is how a claim's manifest records a list of these links. Every
other function here reads that list.

A component is looked up, in order, under `<ws>/.reticuli/sealed/<name>`
(a shared workspace registry) and `<claim>/.reticuli/sealed/<name>` (a claim
vendoring its own dependencies, the shape a transferred claim travels in).

Stdlib only.
"""
import os
import shutil
import tempfile

from . import _util
from . import kernel

_SEALED = "sealed"


def _sealed_dir(ws: str, name: str) -> str:
    return os.path.join(os.path.abspath(ws), kernel.STORE, _SEALED, name)


def _component_dir(d: str, ws, name: str):
    """Where component `name` is vendored, relative to `ws` (if given) or
    `d` itself; `None` if neither holds it."""
    candidates = []
    if ws:
        candidates.append(_sealed_dir(ws, name))
    candidates.append(_sealed_dir(d, name))
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def _dedup_names(entries: list) -> list:
    names = []
    for e in entries:
        if e["component"] not in names:
            names.append(e["component"])
    return names


def _is_from_link(recipe: dict, entry: dict) -> bool:
    """Does `entry` correspond to a `from`-sourced produce step (the
    dependent SHIPS this component's bytes), as opposed to a pinned input
    that merely content-matches a sealed output?"""
    for step in recipe.get("step", []):
        if (step.get("kind") == "produce"
                and step.get("output") == entry.get("input")
                and step.get("from") == entry.get("component")):
            return True
    return False


# ---------------------------------------------------------------------------
# Sealing with provenance
# ---------------------------------------------------------------------------

def seal_with(d: str, components: list = None, proof: dict = None) -> dict:
    """Seal (or re-seal) `d`, then attach `components` and/or `proof` to its
    manifest -- fields `kernel.seal` itself does not know about and would
    otherwise overwrite. A field omitted here is carried over from the
    manifest that existed before this call.
    """
    d = os.path.abspath(d)
    manifest_path = os.path.join(d, kernel.MANIFEST)
    old = {}
    if os.path.isfile(manifest_path):
        try:
            old = kernel.read_manifest(d)
        except kernel.ClaimError:
            old = {}

    manifest = kernel.seal(d)
    if components is not None:
        manifest["components"] = components
    elif "components" in old:
        manifest["components"] = old["components"]
    if proof is not None:
        manifest["proof"] = proof
    elif "proof" in old:
        manifest["proof"] = old["proof"]

    _util.write_json(manifest_path, manifest)
    return manifest


# ---------------------------------------------------------------------------
# Detecting components: content-addressed links
# ---------------------------------------------------------------------------

def detect_components(ws: str, paths: list) -> list:
    """Which of `paths` (pinned inputs in `ws`) content-match a step output
    of a claim already sealed in `ws`'s registry."""
    ws = os.path.abspath(ws)
    sealed_root = os.path.join(ws, kernel.STORE, _SEALED)
    links = []
    if not os.path.isdir(sealed_root):
        return links

    index = {}
    for name in sorted(os.listdir(sealed_root)):
        comp_dir = os.path.join(sealed_root, name)
        if not os.path.isdir(comp_dir):
            continue
        try:
            manifest = kernel.read_manifest(comp_dir)
            recipe = kernel.load_recipe(comp_dir)
        except kernel.ClaimError:
            continue
        for step in recipe.get("step", []):
            output = step.get("output")
            if not output:
                continue
            full = os.path.join(comp_dir, output)
            if not os.path.isfile(full):
                continue
            try:
                h = _util.hash_bytes(full)
            except OSError:
                continue
            index.setdefault(h, []).append((name, output, manifest["root"]))

    for path in paths:
        full = os.path.join(ws, path)
        if not os.path.isfile(full):
            continue
        h = _util.hash_bytes(full)
        for name, output, root in index.get(h, []):
            links.append({"input": path, "component": name,
                          "root": root, "output": output})
    return links


# ---------------------------------------------------------------------------
# The registry: claims and their dependency edges
# ---------------------------------------------------------------------------

def claims(ws: str) -> list:
    """Every claim sealed in `ws`'s registry: `{name, root, phase}`."""
    ws = os.path.abspath(ws)
    sealed_root = os.path.join(ws, kernel.STORE, _SEALED)
    out = []
    if not os.path.isdir(sealed_root):
        return out
    for name in sorted(os.listdir(sealed_root)):
        comp_dir = os.path.join(sealed_root, name)
        if not os.path.isdir(comp_dir):
            continue
        try:
            manifest = kernel.read_manifest(comp_dir)
            phase = kernel.phase(comp_dir)
        except kernel.ClaimError:
            continue
        out.append({"name": manifest["name"], "root": manifest["root"], "phase": phase})
    return out


def deps(ws: str) -> dict:
    """The dependency DAG over `ws`'s registry: one node per claim, with
    `depends_on` edges whose `status` is `ok` (component present and its
    root still matches the recorded link), `drifted`, `missing`, or `broken`.
    """
    ws = os.path.abspath(ws)
    out_claims = []
    for row in claims(ws):
        comp_dir = _sealed_dir(ws, row["name"])
        try:
            manifest = kernel.read_manifest(comp_dir)
        except kernel.ClaimError:
            manifest = {}
        entries = manifest.get("components") or []
        names = _dedup_names(entries)
        edges = []
        for name in names:
            entry = next(e for e in entries if e["component"] == name)
            target = _sealed_dir(ws, name)
            if not os.path.isdir(target):
                status = "missing"
            else:
                try:
                    target_manifest = kernel.read_manifest(target)
                    status = "ok" if target_manifest.get("root") == entry.get("root") else "drifted"
                except kernel.ClaimError:
                    status = "broken"
            edges.append({"component": name, "status": status})
        out_claims.append({"name": row["name"], "depends_on": edges})
    return {"claims": out_claims}


def pull(d: str, ws2: str) -> dict:
    """Materialize claim `d` as a dependency of a fresh workspace `ws2`:
    its declared files land at `ws2`'s top level, and a self-contained
    sealed copy lands in `ws2`'s own registry."""
    d = os.path.abspath(d)
    ws2 = os.path.abspath(ws2)
    manifest = kernel.read_manifest(d)
    name = manifest["name"]
    os.makedirs(ws2, exist_ok=True)

    for entry in sorted(os.listdir(d)):
        if entry == kernel.STORE:
            continue
        _util.copy_into(os.path.join(d, entry), os.path.join(ws2, entry))

    dest_sealed = _sealed_dir(ws2, name)
    if not os.path.isdir(dest_sealed):
        _util.copy_into(d, dest_sealed)

    return {"materialized": True, "name": name, "root": manifest["root"]}


# ---------------------------------------------------------------------------
# DAG-aware rebuild
# ---------------------------------------------------------------------------

def rebuild_chain(d: str, producer: str, into: str, ws: str = None,
                  reuse: bool = False) -> dict:
    """Rebuild `d` into `into`, regrowing every declared component first
    (leaf first), leaf-first recursion unless `reuse` is set -- in which
    case a `from`-sourced component is threaded straight from its existing
    sealed bytes instead of being regrown. The result carries the same
    component links as `d`, and a self-contained sealed copy of each.
    """
    d = os.path.abspath(d)
    into = os.path.abspath(into)
    manifest = kernel.read_manifest(d)
    recipe = kernel.load_recipe(d)
    entries = manifest.get("components") or []
    names = _dedup_names(entries)

    rebuilt_components = []
    comp_results = {}
    created_tmp = set()
    for name in names:
        comp_dir = _component_dir(d, ws, name)
        if not comp_dir:
            raise kernel.ClaimError(
                f"refused: declared component not found in the registry: {name!r}"
            )
        entry_for_name = next(e for e in entries if e["component"] == name)
        if reuse and _is_from_link(recipe, entry_for_name):
            comp_results[name] = comp_dir
        else:
            comp_tmp = tempfile.mkdtemp(prefix="reticuli-dep-")
            sub = rebuild_chain(comp_dir, producer, comp_tmp, ws=ws, reuse=reuse)
            rebuilt_components.append({"component": name, "root": sub["root"]})
            rebuilt_components.extend(sub.get("rebuilt_components", []))
            comp_results[name] = comp_tmp
            created_tmp.add(name)

    produce_map = {}
    input_map = {}
    for entry in entries:
        name = entry["component"]
        source_path = os.path.join(comp_results[name], entry["output"])
        if _is_from_link(recipe, entry):
            produce_map[entry["input"]] = source_path
        else:
            input_map[entry["input"]] = source_path

    result = kernel.rebuild(d, producer, into,
                            produce_from=produce_map or None,
                            input_from=input_map or None)

    seal_with(into, components=entries or None)
    for name in names:
        dest = _sealed_dir(into, name)
        if not os.path.isdir(dest):
            _util.copy_into(comp_results[name], dest)
        if name in created_tmp:
            shutil.rmtree(comp_results[name], ignore_errors=True)

    return {"root": result["root"], "name": result["name"],
            "rebuilt_components": rebuilt_components}


# ---------------------------------------------------------------------------
# The signature-chain root: a bottom-up fold over the DAG
# ---------------------------------------------------------------------------

def sign_root(d: str, ws: str = None) -> str:
    """The signature-chain node for `d`: its own root/build-digest folded
    with the signature-chain nodes of every declared component, found via
    `ws`'s registry (or `d`'s own vendored copy). Refuses, rather than
    eliding, a declared component the registry does not hold.
    """
    d = os.path.abspath(d)
    manifest = kernel.read_manifest(d)
    root_value = manifest["root"]
    digest = kernel.build_digest(d)
    names = _dedup_names(manifest.get("components") or [])
    links = []
    for name in names:
        comp_dir = _component_dir(d, ws, name)
        if not comp_dir:
            raise kernel.ClaimError(
                f"refused: declared component missing from the registry: {name!r}"
            )
        links.append(sign_root(comp_dir, ws))
    return kernel.sign_node(root_value, digest, links)


# ---------------------------------------------------------------------------
# The deep audit: every ancestor, not just the first link
# ---------------------------------------------------------------------------

def audit_deep(d: str) -> dict:
    """Re-earn every ancestor claim's verdict, on the bytes this claim
    actually ships for it: a `from`-sourced output is judged against `d`'s
    OWN current bytes for that output (propagated unchanged through every
    further level of nesting, since a component's own `from` link names the
    same file by the same convention), never the component's frozen copy. A
    component the registry cannot resolve is a failed layer, not an
    omission; the same component named by more than one ancestor is judged
    once.
    """
    d = os.path.abspath(d)
    layers = []
    visited = set()

    def walk(level_dir: str) -> None:
        try:
            manifest = kernel.read_manifest(level_dir)
            recipe = kernel.load_recipe(level_dir)
        except kernel.ClaimError:
            return
        entries = manifest.get("components") or []
        names = _dedup_names(entries)
        for name in names:
            if name in visited:
                continue
            visited.add(name)
            comp_dir = _sealed_dir(level_dir, name)
            bytes_from = sorted(
                e["output"] for e in entries
                if e["component"] == name and _is_from_link(recipe, e)
            )
            if not os.path.isdir(comp_dir):
                layers.append({"name": name, "root": None, "ok": False,
                               "status": "unresolved", "bytes_from": bytes_from})
                continue

            produce_from = {}
            for e in entries:
                if e["component"] == name and _is_from_link(recipe, e):
                    produce_from[e["output"]] = os.path.join(d, e["input"])

            try:
                comp_root = kernel.read_manifest(comp_dir).get("root")
            except kernel.ClaimError:
                comp_root = None

            result = kernel.audit(comp_dir, produce_from=produce_from or None)
            ok = bool(result.get("ok"))
            layers.append({"name": name, "root": comp_root, "ok": ok,
                           "status": "ok" if ok else "broken",
                           "bytes_from": bytes_from})
            walk(comp_dir)

    walk(d)
    return {"ok": all(layer["ok"] for layer in layers), "layers": layers}


def crosscheck_deep(leg1: str, leg2: str, leg3: str, mutants: int = None) -> dict:
    """The three-machine test, strengthened: every directory leg must also
    pass the deep audit over its composed components, not merely its own
    gate -- `kernel.crosscheck` alone is fooled by a forged dependency a
    dependent's own gate cannot see.
    """
    result = kernel.crosscheck(leg1, leg2, leg3, mutants)
    deep_ok = True
    for leg in (leg1, leg2, leg3):
        if os.path.isdir(leg) and not audit_deep(leg)["ok"]:
            deep_ok = False

    out = dict(result)
    out["deep_ok"] = deep_ok
    satisfied = result["satisfied"] and deep_ok
    out["satisfied"] = satisfied
    if not satisfied and result.get("verdict") == "accept":
        out["verdict"] = "reject"
        out["rejected"] = list(result.get("rejected", [])) + ["deep"]
    return out
