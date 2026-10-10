"""The claim store: content-addressed component links, and a DAG-aware
rebuild over the chain they form.

A registry workspace is a directory carrying `.reticuli/sealed/<name>/` --
one subdirectory per staged claim, each a claim directory in its own right.
`detect_components` finds a content-addressed link between a pinned input
and some staged claim's bytes; `seal_with` is `kernel.seal` plus the extra
manifest residue (`components`, `proof`) the kernel itself never writes.
`claims`/`deps` read the store back: every staged claim's identity and
phase, and the dependency edges its manifest declares, each resolved
against what is actually staged. `rebuild_chain` regrows a composed claim
leaf-first -- every declared component is itself rebuilt (or, with
`reuse=True`, reused unmodified) before the top claim's own produce steps
run, so a `from` step's bytes are threaded in rather than left to a
producer that may have no rule for them. `pull` makes a claim a staged,
self-contained dependency of a fresh workspace. `sign_root`/`audit_deep`
fold and re-earn the chain a manifest's `components` describe; `crosscheck_deep`
pairs the three-machine test with a deep audit of every leg that is a
directory, so a forged component invisible to a leg's own gate cannot pass
under its name.
"""
import os
import shutil
import tempfile

from . import kernel
from . import _util


_COMPONENTS_FILE = ".reticuli/components.json"


def components(d: str) -> list:
    """The component links staged for `d`: normally inline on the
    manifest, but falling back to residue kept separately from
    `manifest.json` -- so a plain `kernel.seal` reseal (identity moves, a
    pinned input's content changed) leaves attribution readable even
    though it overwrote the manifest down to `{name, root}`."""
    try:
        inline = kernel.read_manifest(d).get("components")
    except kernel.ClaimError:
        inline = None
    if inline is not None:
        return inline
    path = os.path.join(d, _COMPONENTS_FILE)
    if not os.path.isfile(path):
        return []
    return _util.read_json(path) or []


def _dedupe(paths):
    seen = set()
    out = []
    for p in paths:
        real = os.path.realpath(p)
        if real not in seen:
            seen.add(real)
            out.append(p)
    return out


def _store_files(comp_dir: str):
    """Every regular file under `comp_dir`, outside its own nested store,
    as `(relpath, abspath)` pairs."""
    store_abs = os.path.realpath(os.path.join(comp_dir, kernel.STORE))
    out = []
    for dirpath, dirnames, filenames in os.walk(comp_dir):
        real_dirpath = os.path.realpath(dirpath)
        dirnames[:] = [
            dn for dn in dirnames
            if os.path.realpath(os.path.join(dirpath, dn)) != store_abs
        ]
        if real_dirpath == store_abs or real_dirpath.startswith(store_abs + os.sep):
            continue
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            out.append((os.path.relpath(full, comp_dir), full))
    return out


def detect_components(ws: str, paths) -> list:
    """Which of `paths` (relative to `ws`) content-match a byte some claim
    already staged under `ws/.reticuli/sealed/*` carries. A match is a
    content-addressed link: `{"input", "component", "root", "output"}`."""
    base = os.path.join(ws, kernel.STORE, "sealed")
    links = []
    if not os.path.isdir(base):
        return links

    index = {}
    for name in sorted(os.listdir(base)):
        comp_dir = os.path.join(base, name)
        if not os.path.isdir(comp_dir):
            continue
        try:
            manifest = kernel.read_manifest(comp_dir)
        except kernel.ClaimError:
            continue
        for rel, full in _store_files(comp_dir):
            try:
                h = kernel._hash_file(full)
            except kernel.ClaimError:
                continue
            index.setdefault(h, (name, rel, manifest["root"]))

    for p in paths:
        full = os.path.join(ws, p)
        if not os.path.isfile(full):
            continue
        try:
            h = kernel._hash_file(full)
        except kernel.ClaimError:
            continue
        hit = index.get(h)
        if hit:
            name, rel, root = hit
            links.append({"input": p, "component": name, "root": root, "output": rel})
    return links


def seal_with(d: str, *, components=None, proof=None) -> dict:
    """`kernel.seal` plus the manifest residue the kernel itself never
    writes: `components` (links to layered sub-claims) and `proof` (a
    recorded crosscheck)."""
    manifest = kernel.seal(d)
    if components is None:
        path = os.path.join(d, _COMPONENTS_FILE)
        if os.path.isfile(path):
            components = _util.read_json(path) or None
    changed = False
    if components is not None:
        manifest["components"] = components
        _util.write_json(os.path.join(d, _COMPONENTS_FILE), components)
        changed = True
    if proof is not None:
        manifest["proof"] = proof
        changed = True
    if changed:
        _util.write_json(os.path.join(d, kernel.MANIFEST), manifest)
    return manifest


def claims(ws: str) -> list:
    """Every claim staged under `ws/.reticuli/sealed/*`: its name, root,
    and phase -- phase always recomputed from verifiable state
    (`kernel.phase`), never read off a manifest bit."""
    base = os.path.join(ws, kernel.STORE, "sealed")
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            continue
        try:
            manifest = kernel.read_manifest(d)
        except kernel.ClaimError:
            continue
        try:
            phase = kernel.phase(d)
        except kernel.ClaimError:
            phase = None
        out.append({"name": manifest["name"], "root": manifest["root"], "phase": phase})
    return out


def deps(ws: str) -> dict:
    """The dependency graph of every claim staged under `ws`: one node per
    claim, with `depends_on` edges resolved against what is actually
    staged (`ok` / `mismatch` / `unresolved`)."""
    base = os.path.join(ws, kernel.STORE, "sealed")
    nodes = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            d = os.path.join(base, name)
            if not os.path.isdir(d):
                continue
            try:
                manifest = kernel.read_manifest(d)
            except kernel.ClaimError:
                continue
            edges = []
            for link in components(d):
                comp_name = link.get("component")
                comp_dir = os.path.join(base, comp_name) if comp_name else None
                status = "unresolved"
                if comp_dir and os.path.isdir(comp_dir):
                    try:
                        comp_manifest = kernel.read_manifest(comp_dir)
                        status = "ok" if comp_manifest["root"] == link.get("root") else "mismatch"
                    except kernel.ClaimError:
                        status = "unresolved"
                edges.append({"component": comp_name, "status": status})
            nodes.append({"name": manifest["name"], "root": manifest["root"], "depends_on": edges})
    return {"claims": nodes}


def _resolve(link: dict, stores) -> str:
    """Find where the component `link` names actually lives: any of
    `stores`' own `.reticuli/sealed/<name>`, matched by name and
    confirmed by root. Falls back to scanning every staged claim in each
    store for a root match, so a component resolves by its identity
    wherever it lives, not only by the name a nesting happens to use."""
    name = link.get("component")
    want_root = link.get("root")
    for base in stores:
        cand = os.path.join(base, kernel.STORE, "sealed", name)
        if os.path.isdir(cand):
            try:
                m = kernel.read_manifest(cand)
            except kernel.ClaimError:
                m = None
            if m and (want_root is None or m.get("root") == want_root):
                return cand
    for base in stores:
        sealed = os.path.join(base, kernel.STORE, "sealed")
        if not os.path.isdir(sealed):
            continue
        for entry in sorted(os.listdir(sealed)):
            cand = os.path.join(sealed, entry)
            if not os.path.isdir(cand):
                continue
            try:
                m = kernel.read_manifest(cand)
            except kernel.ClaimError:
                continue
            if want_root is not None and m.get("root") == want_root:
                return cand
    return None


def _code_outputs(recipe: dict) -> dict:
    """`{output: from_component}` for every produce step that ships a
    component's code -- the CODE half of a component link."""
    out = {}
    for step in recipe.get("step", []):
        if step.get("kind") == "produce" and step.get("from"):
            out[step.get("output")] = step.get("from")
    return out


def _walk_deep(d: str, inbound: dict, stores, layers: list) -> bool:
    recipe = kernel.load_recipe(d)
    code = _code_outputs(recipe)
    ok = True
    for link in components(d):
        name = link.get("component")
        comp_dir = _resolve(link, stores)
        if comp_dir is None:
            layers.append({"name": name, "root": link.get("root"),
                            "ok": False, "status": "unresolved"})
            ok = False
            continue

        input_name = link.get("input")
        output_name = link.get("output")
        dependent_path = inbound.get(input_name, os.path.join(d, input_name))
        is_code = code.get(input_name) == name
        next_inbound = {}

        if is_code:
            result = kernel.audit(comp_dir, produce_from={output_name: dependent_path})
            comp_ok = result["ok"]
            status = "ok" if comp_ok else "broken"
            bytes_from = [input_name]
            next_inbound[output_name] = dependent_path
        else:
            result = kernel.audit(comp_dir)
            comp_output = os.path.join(comp_dir, output_name)
            content_match = (os.path.isfile(dependent_path) and os.path.isfile(comp_output)
                              and kernel._hash_file(dependent_path) == kernel._hash_file(comp_output))
            comp_ok = result["ok"] and content_match
            if not result["ok"]:
                status = result.get("verdict", "broken")
            elif not content_match:
                status = "attribution mismatch"
            else:
                status = "ok"
            bytes_from = None

        comp_manifest = kernel.read_manifest(comp_dir)
        entry = {"name": name, "root": comp_manifest["root"], "ok": comp_ok, "status": status}
        if bytes_from is not None:
            entry["bytes_from"] = bytes_from
        layers.append(entry)
        if not comp_ok:
            ok = False

        sub_ok = _walk_deep(comp_dir, next_inbound, stores, layers)
        ok = ok and sub_ok
    return ok


def audit_deep(d: str, ws: str = None) -> dict:
    """Re-earn every ancestor a claim's `components` declare, recursively:
    a CODE link (a `from` produce step) re-earns the component's own gate
    on the bytes this claim actually ships; a DATA link (a pinned input
    content-matched to a component's output) re-earns that content match
    against the component's own freshly-audited bytes. A component the
    store cannot resolve is a failed layer (`unresolved`), not an absence."""
    stores = _dedupe([d, ws or d])
    layers = []
    ok = _walk_deep(d, {}, stores, layers)
    return {"ok": ok, "layers": layers}


def sign_root(d: str, ws: str = None) -> str:
    """The signature-chain node for `d`: its own root and build digest,
    folded bottom-up with the sign_root of every declared component.
    Refuses (in band) a declared component the store cannot resolve."""
    verified = kernel.verify(d)
    if not verified["ok"]:
        raise kernel.ClaimError(f"{d!r} does not verify; cannot fold a signature node")
    stores = _dedupe([d, ws or d])
    links = []
    for link in components(d):
        comp_dir = _resolve(link, stores)
        if comp_dir is None:
            raise kernel.ClaimError(
                f"sign_root: declared component {link.get('component')!r} is not resolvable")
        links.append(sign_root(comp_dir, ws))
    digest = kernel.build_digest(d)
    return kernel.sign_node(verified["root"], digest, links)


def _resolve_component_dir(name: str, stores) -> str:
    for base in stores:
        cand = os.path.join(base, kernel.STORE, "sealed", name)
        if os.path.isdir(cand):
            return cand
    return None


def rebuild_chain(d: str, producer: str, into: str, *, ws: str = None, reuse: bool = False) -> dict:
    """Regrow a composed claim's whole chain, leaf first: every declared
    component is itself rebuilt (`reuse=False`) or copied unmodified from
    the store (`reuse=True`) before the top claim's own produce steps
    run, and a `from` step's bytes are threaded in via `produce_from`
    rather than left to a producer with no rule for them. The rebuilt (or
    reused) components are staged under `into`'s own store, so the result
    keeps its provenance and its chain re-earns deep."""
    recipe = kernel.load_recipe(d)
    comp_links = components(d)
    stores = _dedupe([d, ws or d])
    code = _code_outputs(recipe)

    rebuilt_components = []
    produce_from = {}
    leaf_dirs = {}
    tmp_root = tempfile.mkdtemp(prefix=".reticuli-chain-")
    try:
        for link in comp_links:
            name = link.get("component")
            if name in leaf_dirs:
                continue
            comp_dir = _resolve(link, stores) or _resolve_component_dir(name, stores)
            if comp_dir is None:
                raise kernel.ClaimError(f"rebuild_chain: cannot resolve component {name!r}")
            leaf_into = os.path.join(tmp_root, name)
            if reuse:
                shutil.copytree(comp_dir, leaf_into)
            else:
                sub = rebuild_chain(comp_dir, producer, leaf_into, ws=ws, reuse=reuse)
                rebuilt_components.append({"component": name, "root": sub["root"]})
                rebuilt_components.extend(sub.get("rebuilt_components", []))
            leaf_dirs[name] = leaf_into

            input_name = link.get("input")
            output_name = link.get("output")
            if code.get(input_name) == name:
                produce_from[input_name] = os.path.join(leaf_into, output_name)

        result = kernel.rebuild(d, producer, into, produce_from=produce_from or None)

        if comp_links:
            for link in comp_links:
                name = link.get("component")
                dest = os.path.join(into, kernel.STORE, "sealed", name)
                if not os.path.isdir(dest):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copytree(leaf_dirs[name], dest)
            seal_with(into, components=comp_links)

        return {"root": result["root"], "name": result["name"],
                "rebuilt_components": rebuilt_components, "gates": result.get("gates")}
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def _flatten_into(src: str, dest: str) -> None:
    for entry in os.listdir(src):
        if entry == kernel.STORE:
            continue
        s = os.path.join(src, entry)
        t = os.path.join(dest, entry)
        if os.path.isdir(s):
            shutil.copytree(s, t, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(t) or dest, exist_ok=True)
            shutil.copy2(s, t)


def _stage_flat(src_dir: str, sealed_root: str, visited: set) -> str:
    """Copy `src_dir`'s own content (never its nested store) into
    `sealed_root/<name>`, then recurse into its own `.reticuli/sealed/*`
    -- dereferencing any symlink -- staged into the SAME flat
    `sealed_root`, deduped by name. This is what keeps a pulled closure
    disk-compact: a shared ancestor reachable through several nested
    symlink paths is copied exactly once, not once per path."""
    manifest = kernel.read_manifest(src_dir)
    name = manifest["name"]
    dest = os.path.join(sealed_root, name)
    if name in visited:
        return dest
    visited.add(name)

    os.makedirs(dest, exist_ok=True)
    for entry in os.listdir(src_dir):
        if entry == kernel.STORE:
            continue
        s = os.path.join(src_dir, entry)
        t = os.path.join(dest, entry)
        if os.path.isdir(s):
            shutil.copytree(s, t, dirs_exist_ok=True)
        else:
            shutil.copy2(s, t)

    dest_store = os.path.join(dest, kernel.STORE)
    os.makedirs(dest_store, exist_ok=True)
    for fn in (os.path.basename(kernel.MANIFEST), os.path.basename(_COMPONENTS_FILE)):
        p = os.path.join(src_dir, kernel.STORE, fn)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(dest_store, fn))

    nested = os.path.join(src_dir, kernel.STORE, "sealed")
    if os.path.isdir(nested):
        for entry in sorted(os.listdir(nested)):
            _stage_flat(os.path.join(nested, entry), sealed_root, visited)
    return dest


def pull(src: str, ws: str) -> dict:
    """Make the claim at `src` a staged, self-contained dependency of
    `ws`: its whole closure -- itself and every component it declares,
    however deeply or redundantly nested, symlinked ancestors dereferenced
    -- lands flat and deduped under `ws/.reticuli/sealed/`, standing alone
    even after `src` is gone and disk-compact (each dependency's bytes
    appear once, never once per path that reaches them). Its own declared
    files are also merged directly into `ws` for immediate use."""
    os.makedirs(ws, exist_ok=True)
    sealed_root = os.path.join(ws, kernel.STORE, "sealed")
    os.makedirs(sealed_root, exist_ok=True)
    dest = _stage_flat(src, sealed_root, set())
    _flatten_into(dest, ws)
    manifest = kernel.read_manifest(dest)
    return {"materialized": True, "name": manifest["name"], "root": manifest["root"]}


def crosscheck_deep(m1: str, m2: str, m3: str, **kwargs) -> dict:
    """The three-machine test, with every directory leg also deep-audited:
    a component forged in a way its own dependent's gate cannot see still
    fails here, under whichever leg carries it."""
    base = kernel.crosscheck(m1, m2, m3, **kwargs)
    deep = {}
    deep_ok = True
    for label, leg in (("M1", m1), ("M2", m2), ("M3", m3)):
        if os.path.isdir(leg):
            try:
                d = audit_deep(leg)
            except kernel.ClaimError:
                d = {"ok": False, "layers": []}
            deep[label] = d
            if not d["ok"]:
                deep_ok = False
    result = dict(base)
    result["deep"] = deep
    result["satisfied"] = bool(base["satisfied"]) and deep_ok
    return result
