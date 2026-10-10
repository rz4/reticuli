"""registry: claims meet claims (spec/layers.md "exchange").

A workspace keeps sealed claims flat under `<ws>/.reticuli/sealed/<name>`.
This module adds, over the kernel: content-addressed component detection
(`detect_components`), the claim store view (`claims`, `deps`), DAG-aware
rebuild (`rebuild_chain`) and pull (`pull`), the bottom-anchored signature
chain (`sign_root`), and the deep audit that walks a composed claim's whole
ancestry, resolving components by root wherever they live in the store,
never by physical nesting (`audit_deep`, `crosscheck_deep`).

A claim's declared "components" survive a raw `kernel.seal()` call (which
only ever writes `{name, root}`): this module keeps its own residue file,
`.reticuli/links.json`, beside the manifest, and patches both whenever it
has a components/proof value to record.
"""
import os
import shutil
import tempfile

from reticuli import _util, kernel

LINKS_FILE = "links.json"


# -- the home workspace: a claim at <ws>/.reticuli/sealed/<name> belongs to
# ws; anything else is its own home (its own nested .reticuli/sealed). ------

def _home(d: str) -> str:
    d = os.path.normpath(d)
    parent = os.path.dirname(d)
    grand = os.path.dirname(parent)
    if os.path.basename(parent) == "sealed" and os.path.basename(grand) == _util.STORE:
        return os.path.dirname(grand)
    return d


# -- the side-file: components/proof survive a raw kernel.seal() call ------

def _side_path(d: str) -> str:
    return os.path.join(d, _util.STORE, LINKS_FILE)


def _read_side(d: str) -> dict:
    p = _side_path(d)
    if os.path.isfile(p):
        try:
            return _util.read_json(p)
        except (OSError, ValueError):
            return {}
    return {}


def _write_side(d: str, obj: dict) -> None:
    _util.write_json(_side_path(d), obj)


def components_of(d: str) -> list:
    """`d`'s declared component links, from the side-file if present, else
    from the manifest -- so they survive a raw `kernel.seal()` reseal."""
    side = _read_side(d)
    if "components" in side:
        return side["components"] or []
    try:
        m = kernel.read_manifest(d)
    except kernel.ClaimError:
        return []
    return m.get("components") or []


def seal_with(d: str, components=None, proof=None) -> dict:
    """Seal `d`, then record `components` and/or `proof` as residue beside
    the manifest -- both in the manifest itself (for readers who only know
    `kernel.read_manifest`) and in `.reticuli/links.json` (which survives a
    later plain `kernel.seal()` call on the same claim)."""
    manifest = kernel.seal(d)
    side = _read_side(d)
    changed = False
    if components is not None:
        side["components"] = components
        changed = True
    if proof is not None:
        side["proof"] = proof
        changed = True
    if changed:
        _write_side(d, side)
        patched = dict(manifest)
        patched.update(side)
        _util.write_json(os.path.join(d, kernel.MANIFEST), patched)
    return manifest


# -- resolving declared components to paths, by root -----------------------

def _root_index(base: str) -> dict:
    """root -> claim directory, for every claim anywhere under `base`
    (any nesting depth, any store folder name, symlinked or not) -- never
    only where a particular component happens to physically nest. Follows
    symlinks but dedups by real path, so a flat store of symlinks to a
    shared ancestor set is visited once, not once per path that reaches it
    (the growth-envelope bound this is measured against)."""
    index = {}
    visited_real = set()

    def walk(path):
        real = os.path.realpath(path)
        if real in visited_real:
            return
        visited_real.add(real)
        if path != base:
            manifest_path = os.path.join(path, _util.STORE, "manifest.json")
            if os.path.isfile(manifest_path):
                try:
                    m = kernel.read_manifest(path)
                    index.setdefault(m["root"], path)
                except kernel.ClaimError:
                    pass
        try:
            entries = os.listdir(path)
        except OSError:
            return
        for entry in entries:
            full = os.path.join(path, entry)
            if os.path.isdir(full):
                walk(full)

    if os.path.isdir(base):
        walk(base)
    return index


def _resolve_components(path: str, index: dict) -> list:
    """`[(name, root, links, resolved_path), ...]` for `path`'s own
    declared components, grouped by (name, root); refuses a declared
    component the index cannot resolve."""
    grouped = {}
    for link in components_of(path):
        grouped.setdefault((link["component"], link["root"]), []).append(link)
    out = []
    for (name, root), group in grouped.items():
        resolved = index.get(root)
        if resolved is None:
            raise kernel.ClaimError(f"missing declared component {name!r} (root {root})")
        out.append((name, root, group, resolved))
    return out


def _is_from_step(parsed: dict, output: str, component_name: str) -> bool:
    """Whether `parsed` has a produce step shipping `output` from
    `component_name` (the CODE species of a component link)."""
    for step in parsed.get("step", []) or []:
        if step.get("kind") == "produce" and step.get("output") == output \
                and step.get("from") == component_name:
            return True
    return False


def _files_equal(a: str, b: str) -> bool:
    try:
        return kernel._hash_file(a) == kernel._hash_file(b)
    except kernel.ClaimError:
        return False


# -- a shallow claim copy: the claim's own content, never its nested ======
# -- component store (avoids exponential blowup over a shared-ancestor DAG) -

def _copy_store_shallow(src_store: str, dst_store: str) -> None:
    os.makedirs(dst_store, exist_ok=True)
    for entry in sorted(os.listdir(src_store)):
        if entry in ("sealed", "deps"):
            continue
        _util.copy_into(os.path.join(src_store, entry), os.path.join(dst_store, entry))


def _copy_claim_flat(src: str, dst: str) -> None:
    os.makedirs(dst, exist_ok=True)
    for entry in sorted(os.listdir(src)):
        s = os.path.join(src, entry)
        t = os.path.join(dst, entry)
        if entry == ".reticuli":
            _copy_store_shallow(s, t)
        else:
            _util.copy_into(s, t)


# -- content-addressed component detection ----------------------------------

def detect_components(ws: str, inputs: list) -> list:
    """A pinned input that content-matches a sealed claim's file in `ws`'s
    store is a dependency: `[{"input", "component", "root", "output"}, ...]`."""
    results = []
    sealed_root = os.path.join(ws, _util.STORE, "sealed")
    if not os.path.isdir(sealed_root):
        return results
    for inp in inputs:
        inp_path = os.path.join(ws, inp)
        if not os.path.isfile(inp_path):
            continue
        with open(inp_path, "rb") as f:
            inp_hash = _util.hash_bytes(f.read())
        for name in sorted(os.listdir(sealed_root)):
            claim_dir = os.path.join(sealed_root, name)
            if not os.path.isdir(claim_dir):
                continue
            try:
                manifest = kernel.read_manifest(claim_dir)
            except kernel.ClaimError:
                continue
            matched = None
            for fname in sorted(os.listdir(claim_dir)):
                if fname == ".reticuli":
                    continue
                fpath = os.path.join(claim_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                with open(fpath, "rb") as f:
                    if _util.hash_bytes(f.read()) == inp_hash:
                        matched = fname
                        break
            if matched:
                results.append({"input": inp, "component": manifest["name"],
                                 "root": manifest["root"], "output": matched})
                break
    return results


# -- the claim store view: claims(ws), deps(ws) -----------------------------

def claims(ws: str) -> list:
    """Every claim in `ws`'s store: `{"name", "root", "phase"}`. Phase is
    always read from the verifiable state (`kernel.phase`), never from a
    manifest bit -- an injected `proof` cannot forge "signed" here."""
    sealed_root = os.path.join(ws, _util.STORE, "sealed")
    out = []
    if not os.path.isdir(sealed_root):
        return out
    for name in sorted(os.listdir(sealed_root)):
        claim_dir = os.path.join(sealed_root, name)
        if not os.path.isdir(claim_dir):
            continue
        try:
            manifest = kernel.read_manifest(claim_dir)
        except kernel.ClaimError:
            continue
        out.append({"name": manifest["name"], "root": manifest["root"],
                     "phase": kernel.phase(claim_dir)})
    return out


def deps(ws: str) -> dict:
    """The DAG view: `{"claims": [{"name", "depends_on": [...]}]}`."""
    sealed_root = os.path.join(ws, _util.STORE, "sealed")
    index = _root_index(ws)
    out = []
    if os.path.isdir(sealed_root):
        for name in sorted(os.listdir(sealed_root)):
            claim_dir = os.path.join(sealed_root, name)
            if not os.path.isdir(claim_dir):
                continue
            try:
                manifest = kernel.read_manifest(claim_dir)
            except kernel.ClaimError:
                continue
            depends_on = []
            for link in components_of(claim_dir):
                resolved = index.get(link["root"])
                status = "ok" if resolved else "unresolved"
                depends_on.append({"component": link["component"], "root": link["root"],
                                    "status": status})
            out.append({"name": manifest["name"], "depends_on": depends_on})
    return {"claims": out}


# -- the deep audit: walks the whole ancestry, resolving by root -----------

def audit_deep(d: str, ws=None) -> dict:
    """Re-earn every ancestor's own verdicts, on the bytes the DEPENDENT
    actually ships (CODE species: a `from` step) or re-earn a declared
    content match (DATA species: a plain pinned input) -- flattened across
    the whole chain, never stopping at the first link, and never fooled by
    which physical directory a component happens to be nested under."""
    base = ws or _home(d)
    index = _root_index(base)
    layers = []
    cache = {}

    def record_layer(path, overrides):
        manifest = kernel.read_manifest(path)
        if overrides:
            tmp = tempfile.mkdtemp(prefix="reg-deep-")
            try:
                _copy_claim_flat(path, tmp)
                for outp, src in overrides.items():
                    dst = os.path.join(tmp, outp)
                    parent = os.path.dirname(dst)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    shutil.copy2(src, dst)
                a = kernel.audit(tmp)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        else:
            a = kernel.audit(path)
        if a["ok"]:
            status = "ok"
        elif "verdict" in a:
            status = a["verdict"]
        elif a.get("environment"):
            status = "environment"
        else:
            bad = {g["status"] for g in a.get("gates", []) if g["status"] != "ok"}
            status = next(iter(bad), "failed")
        entry = {"name": manifest["name"], "root": manifest["root"], "ok": a["ok"],
                  "status": status}
        if overrides:
            entry["bytes_from"] = sorted(overrides)
        layers.append(entry)
        return a["ok"]

    def recurse(path, overrides, top=False):
        if top:
            ok_self = kernel.audit(path)["ok"]
        else:
            ok_self = record_layer(path, overrides)
        parsed = kernel.load_recipe(path)
        grouped = {}
        for link in components_of(path):
            grouped.setdefault((link["component"], link["root"]), []).append(link)
        ok_all = ok_self
        for (comp_name, comp_root), group in grouped.items():
            resolved = index.get(comp_root)
            if resolved is None:
                layers.append({"name": comp_name, "root": comp_root, "ok": False,
                                "status": "unresolved"})
                ok_all = False
                continue
            child_overrides = {}
            mismatch = False
            for link in group:
                inp, outp = link["input"], link["output"]
                src = overrides.get(inp) if overrides else None
                actual_path = src or os.path.join(path, inp)
                if _is_from_step(parsed, outp, comp_name):
                    child_overrides[outp] = actual_path
                else:
                    comp_file = os.path.join(resolved, outp)
                    if not _files_equal(actual_path, comp_file):
                        mismatch = True
            if mismatch:
                layers.append({"name": comp_name, "root": comp_root, "ok": False,
                                "status": "attribution_mismatch"})
                ok_all = False
                continue
            cache_key = (comp_name, comp_root, tuple(sorted(child_overrides.items())))
            if cache_key in cache:
                ok_all = ok_all and cache[cache_key]
                continue
            child_ok = recurse(resolved, child_overrides)
            cache[cache_key] = child_ok
            ok_all = ok_all and child_ok
        return ok_all

    ok = recurse(d, {}, top=True)
    return {"ok": ok, "layers": layers}


def crosscheck_deep(m1: str, m2: str, m3: str, mutants=None) -> dict:
    """Like `kernel.crosscheck`, except every directory leg's verdict is
    `audit_deep`'s, not the shallow `kernel.audit`'s -- a forged layer a
    shallow crosscheck cannot see still fails this one."""
    base = kernel.crosscheck(m1, m2, m3, mutants=mutants)
    audited = {}
    for key, leg in (("M1", m1), ("M2", m2), ("M3", m3)):
        audited[key] = audit_deep(leg)["ok"] if os.path.isdir(leg) else base["audited"][key]
    rejected = [r for r in base["rejected"] if not r.startswith("audit:")]
    for key, ok in audited.items():
        if not ok:
            rejected.append(f"audit:{key}")
    if rejected:
        verdict = "reject"
    elif base["incomplete"]:
        verdict = "incomplete"
    else:
        verdict = "accept"
    out = dict(base)
    out["audited"] = audited
    out["rejected"] = rejected
    out["verdict"] = verdict
    out["satisfied"] = verdict == "accept"
    return out


# -- DAG-aware rebuild: leaves first, components threaded or reused --------

def rebuild_chain(d: str, producer: str, into: str, ws=None, reuse: bool = False) -> dict:
    """Regrow `d`'s whole chain (leaf components first) or, with
    `reuse=True`, regrow only `d`'s own layer, threading its ALREADY
    SEALED components in untouched -- the incremental build."""
    base = ws or _home(d)
    index = _root_index(base)
    rebuilt = []
    temp_dirs = []

    def build_layer(path, dest):
        parsed = kernel.load_recipe(path)
        comps = _resolve_components(path, index)
        produce_from = {}
        child_paths = {}
        for name, root, group, resolved in comps:
            if reuse:
                child_path = resolved
            else:
                scratch = tempfile.mkdtemp(prefix="reg-chain-")
                temp_dirs.append(scratch)
                child_path = build_layer(resolved, scratch)
                rebuilt.append({"component": name, "root": root})
            child_paths[name] = child_path
            for link in group:
                outp = link["output"]
                if _is_from_step(parsed, outp, name):
                    produce_from[outp] = os.path.join(child_path, outp)
        kernel.rebuild(path, producer, dest, produce_from=produce_from or None)
        for name, root, group, resolved in comps:
            comp_dest = os.path.join(dest, _util.STORE, "sealed", name)
            if not os.path.isdir(comp_dest):
                _util.copy_into(child_paths[name], comp_dest)
        if comps:
            seal_with(dest, components=components_of(path))
        return dest

    try:
        build_layer(d, into)
    finally:
        for t in temp_dirs:
            shutil.rmtree(t, ignore_errors=True)
    manifest = kernel.read_manifest(into)
    return {"root": manifest["root"], "rebuilt_components": rebuilt}


# -- pull: a claim becomes a standalone, disk-compact dependency -----------

def pull(src: str, into: str) -> dict:
    """Materialize `src` flat at `into`, plus its whole resolvable closure
    (deduplicated by root) under `into/.reticuli/sealed/<name>` -- the
    pulled claim stands alone and stays disk-compact."""
    manifest = kernel.read_manifest(src)
    base = _home(src)
    index = _root_index(base)
    os.makedirs(into, exist_ok=True)
    _copy_claim_flat(src, into)
    sealed_root = os.path.join(into, _util.STORE, "sealed")
    os.makedirs(sealed_root, exist_ok=True)
    visited = set()

    def place(path):
        m = kernel.read_manifest(path)
        if m["root"] in visited:
            return
        visited.add(m["root"])
        dest = os.path.join(sealed_root, m["name"])
        if not os.path.isdir(dest):
            _copy_claim_flat(path, dest)
        for name, root, group, resolved in _resolve_components(path, index):
            place(resolved)

    place(src)
    return {"materialized": True, "root": manifest["root"], "name": manifest["name"]}


# -- the bottom-anchored signature chain ------------------------------------

def sign_root(d: str, ws=None) -> str:
    """One signature-chain node per claim, folding every declared
    component's own node bottom-up (`kernel.sign_node`); refuses a
    declared component the store cannot resolve."""
    base = ws or _home(d)
    index = _root_index(base)
    links = [sign_root(resolved, base) for _n, _r, _g, resolved in _resolve_components(d, index)]
    r = kernel.verify(d)["root"]
    digest = kernel.build_digest(d)
    return kernel.sign_node(r, digest, links)
