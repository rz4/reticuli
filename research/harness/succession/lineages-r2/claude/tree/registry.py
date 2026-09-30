"""registry: claims meeting claims (spec/layers.md).

A claim store is a workspace directory `ws` with sealed claims living under
`ws/.reticuli/sealed/<name>/`. `detect_components` finds content-addressed
links between a candidate's pinned inputs and another sealed claim's own
pinned outputs; `seal_with` attaches that provenance (and, later, a
recorded proof) to a claim's manifest; `claims`/`deps` read the store back
as a list and a DAG. `rebuild_chain` is the DAG-aware rebuild: it regrows a
composed claim's declared components first (leaf first) and threads their
fresh bytes into the top claim's own rebuild, or -- `reuse=True` -- reuses
an already-sealed component untouched, the incremental-build path.
`audit_deep`/`crosscheck_deep` re-earn a `from`-sourced layer's gate on the
dependent's own shipped bytes, never trusting a carried verdict.
`sign_root` folds the signature chain bottom-up over the same DAG.

Stdlib only.
"""
import os
import shutil
import tempfile

from . import _util, kernel

_SEALED = "sealed"
_STORE_SEALED = os.path.join(_util.STORE, _SEALED)


# ---------------------------------------------------------------------------
# component discovery and attachment
# ---------------------------------------------------------------------------

def _is_sealed_claim(d: str) -> bool:
    return os.path.isfile(os.path.join(d, kernel.MANIFEST))


def detect_components(ws: str, paths: list) -> list:
    """Content-addressed links: for each of `paths` (relative to `ws`),
    find a sealed claim under `ws/.reticuli/sealed/*` whose own pinned
    (non-generated) output happens to carry the same bytes.

    Returns a list of `{"input", "component", "output", "root"}` -- a
    pinned input that content-matches a claim's output is a dependency,
    discovered by hash, never by name.
    """
    sealed_root = os.path.join(ws, _STORE_SEALED)
    links = []
    if not os.path.isdir(sealed_root):
        return links
    for name in sorted(os.listdir(sealed_root)):
        comp_dir = os.path.join(sealed_root, name)
        if not _is_sealed_claim(comp_dir):
            continue
        try:
            parsed = kernel.load_recipe(comp_dir)
        except kernel.ClaimError:
            continue
        for step in parsed.get("step", []):
            if step["class"] in ("generated", "free"):
                continue
            out_path = os.path.join(comp_dir, _util.step_output(step))
            if not os.path.isfile(out_path):
                continue
            out_hash = kernel._hash_file(out_path)
            for path in paths:
                full = os.path.join(ws, path)
                if not os.path.isfile(full):
                    continue
                if kernel._hash_file(full) == out_hash:
                    links.append({
                        "input": path, "component": name,
                        "output": step["output"],
                        "root": kernel.read_manifest(comp_dir)["root"],
                    })
    return links


def _find_component_dir(d: str, name: str) -> str:
    """A component's directory: nested inside `d` (`d/.reticuli/sealed/<name>`,
    a claim that embeds its own dependency copy), else a sibling of `d`
    (`../<name>`, a shared registry store) -- both conventions this layer
    produces, so both must be read back."""
    nested = os.path.join(d, _STORE_SEALED, name)
    if os.path.isdir(nested):
        return nested
    sibling = os.path.join(os.path.dirname(d), name)
    if os.path.isdir(sibling):
        return sibling
    return nested  # the caller decides how to report "missing"


def _resolve_components(d: str, components) -> dict:
    """Normalize a `seal_with(components=...)` argument -- either an
    already-resolved `{name: relpath}` mapping (reused verbatim, e.g. a
    manifest's own `components` handed back in), or a list of link records
    (from `detect_components`, or hand-built the same shape) -- into
    `{name: relpath-from-d}`."""
    if isinstance(components, dict):
        return dict(components)
    resolved = {}
    for link in components:
        name = link["component"]
        comp_dir = _find_component_dir(d, name)
        if not os.path.isdir(comp_dir):
            raise kernel.ClaimError(f"component {name!r} not found for {d!r}")
        resolved[name] = os.path.relpath(comp_dir, d)
    return resolved


def seal_with(d: str, components=None, proof=None) -> dict:
    """Seal (or re-seal) `d`, attaching component provenance and/or a
    recorded proof to the manifest -- the parts `kernel.seal` itself never
    writes, since identity never depends on them.

    Fields not given are carried over from whatever manifest already
    existed, so a re-seal (recording a proof after the fact) does not drop
    provenance a previous call attached.
    """
    try:
        existing = kernel.read_manifest(d)
    except kernel.ClaimError:
        existing = {}
    manifest = kernel.seal(d)
    if components is not None:
        manifest["components"] = _resolve_components(d, components)
    elif "components" in existing:
        manifest["components"] = existing["components"]
    if proof is not None:
        manifest["proof"] = proof
    elif "proof" in existing:
        manifest["proof"] = existing["proof"]
    _util.write_json(os.path.join(d, kernel.MANIFEST), manifest)
    return manifest


# ---------------------------------------------------------------------------
# the claim store: a list, and a DAG
# ---------------------------------------------------------------------------

def claims(ws: str) -> list:
    """Every sealed claim under `ws/.reticuli/sealed/*`."""
    sealed_root = os.path.join(ws, _STORE_SEALED)
    out = []
    if not os.path.isdir(sealed_root):
        return out
    for name in sorted(os.listdir(sealed_root)):
        comp_dir = os.path.join(sealed_root, name)
        if not _is_sealed_claim(comp_dir):
            continue
        manifest = kernel.read_manifest(comp_dir)
        out.append({"name": manifest["name"], "root": manifest["root"],
                    "phase": kernel.phase(comp_dir), "path": comp_dir})
    return out


def deps(ws: str) -> dict:
    """The claim store as a DAG: each claim's declared components, and
    whether each still resolves and verifies."""
    result = []
    for c in claims(ws):
        manifest = kernel.read_manifest(c["path"])
        components = manifest.get("components") or {}
        depends_on = []
        for name, rel in components.items():
            target = os.path.join(c["path"], rel)
            status = "missing"
            if os.path.isdir(target):
                try:
                    status = "ok" if kernel.verify(target)["ok"] else "broken"
                except kernel.ClaimError:
                    status = "broken"
            depends_on.append({"component": name, "status": status})
        result.append({"name": c["name"], "depends_on": depends_on})
    return {"claims": result}


def pull(d: str, into: str) -> dict:
    """Materialize a claim's current declared content -- recipe, inputs,
    every present output -- flat into a fresh directory `into`, and seal
    it there: a claim becomes a dependency of a fresh workspace."""
    parsed = kernel.load_recipe(d)
    rname = _util.recipe_name(d)
    os.makedirs(into, exist_ok=True)
    _util.copy_into(os.path.join(d, rname), os.path.join(into, rname))
    for inp in _util.declared_inputs(d):
        _util.copy_into(os.path.join(d, inp), os.path.join(into, inp))
    for step in parsed.get("step", []):
        src = os.path.join(d, _util.step_output(step))
        if os.path.isfile(src):
            _util.copy_into(src, os.path.join(into, step["output"]))
    manifest = kernel.seal(into)
    return {"materialized": True, **manifest}


# ---------------------------------------------------------------------------
# the DAG-aware rebuild
# ---------------------------------------------------------------------------

def _copy_claim_criteria(src: str, dest: str) -> None:
    """A component's travel content: its recipe, its pinned inputs, and its
    non-generated outputs -- never its generated bytes (GATES COMPOSE,
    VERDICTS NEVER CARRY)."""
    os.makedirs(dest, exist_ok=True)
    parsed = kernel.load_recipe(src)
    rname = _util.recipe_name(src)
    _util.copy_into(os.path.join(src, rname), os.path.join(dest, rname))
    for inp in _util.declared_inputs(src):
        _util.copy_into(os.path.join(src, inp), os.path.join(dest, inp))
    for step in parsed.get("step", []):
        if step["class"] in ("generated", "free"):
            continue
        p = os.path.join(src, step["output"])
        if os.path.isfile(p):
            _util.copy_into(p, os.path.join(dest, step["output"]))


def _resolve_declared_components(d: str, ws=None) -> dict:
    manifest = kernel.read_manifest(d)
    components = manifest.get("components") or {}
    out = {}
    for name, rel in components.items():
        comp_dir = os.path.join(d, rel)
        if not os.path.isdir(comp_dir) and ws is not None:
            alt = os.path.join(ws, _STORE_SEALED, name)
            if os.path.isdir(alt):
                comp_dir = alt
        if not os.path.isdir(comp_dir):
            raise kernel.ClaimError(f"declared component {name!r} is missing: {comp_dir!r}")
        out[name] = comp_dir
    return out


def rebuild_chain(d: str, producer: str, into: str, *, ws: str = None,
                   reuse: bool = False) -> dict:
    """Regrow `d` into `into`, DAG-aware: every declared component is
    resolved first (leaf first) -- rebuilt fresh unless `reuse`, in which
    case its already-sealed bytes are threaded in untouched, the
    incremental-build path for large software. A `from`-sourced produce
    step is supplied the component's own output directly; a content-
    addressed pinned input is refreshed from the component's matching
    pinned output the same way. The result carries its own component
    provenance forward, nested under `into/.reticuli/sealed/<name>`.
    """
    into_abs = os.path.abspath(into)
    parsed = kernel.load_recipe(d)
    comp_dirs = _resolve_declared_components(d, ws)

    rebuilt_components = []
    comp_targets = {}
    for name, comp_dir in comp_dirs.items():
        if reuse:
            comp_targets[name] = comp_dir
            continue
        comp_target = tempfile.mkdtemp(prefix=f"component-{name}-",
                                        dir=os.path.dirname(into_abs))
        shutil.rmtree(comp_target)
        sub = rebuild_chain(comp_dir, producer, comp_target, ws=ws, reuse=False)
        comp_targets[name] = comp_target
        rebuilt_components.extend(sub.get("rebuilt_components", []))
        rebuilt_components.append({"component": name, "root": sub["root"]})

    produce_from = {}
    for step in parsed.get("step", []):
        if step["kind"] == "produce" and "from" in step:
            comp_target = comp_targets.get(step["from"])
            if comp_target is None:
                raise kernel.ClaimError(
                    f"produce step 'from' names an unresolved component: {step['from']!r}")
            produce_from[step["output"]] = os.path.join(comp_target, step["output"])

    input_from = {}
    declared = _util.declared_inputs(d)
    for name, comp_target in comp_targets.items():
        comp_parsed = kernel.load_recipe(comp_dirs[name])
        for step in comp_parsed.get("step", []):
            if step["class"] in ("generated", "free"):
                continue
            comp_out = os.path.join(comp_target, step["output"])
            if not os.path.isfile(comp_out):
                continue
            comp_hash = kernel._hash_file(comp_out)
            for inp in declared:
                if inp in input_from:
                    continue
                inp_path = os.path.join(d, inp)
                if os.path.isfile(inp_path) and kernel._hash_file(inp_path) == comp_hash:
                    input_from[inp] = comp_out

    result = kernel.rebuild(d, producer, into_abs, produce_from=produce_from,
                            input_from=input_from)

    new_components = {}
    for name, comp_target in comp_targets.items():
        dest = os.path.join(into_abs, _STORE_SEALED, name)
        _copy_claim_criteria(comp_target, dest)
        kernel.seal(dest)
        new_components[name] = os.path.relpath(dest, into_abs)
    if new_components:
        seal_with(into_abs, components=new_components)
        _util.backfill_components(into_abs)

    return {**result, "rebuilt_components": rebuilt_components}


# ---------------------------------------------------------------------------
# deep audit and crosscheck: re-earning a `from`-sourced layer's gate on
# the dependent's own shipped bytes
# ---------------------------------------------------------------------------

def audit_deep(d: str) -> dict:
    """For every `from`-sourced produce step, re-run the named component's
    OWN gate against the CURRENT shipped bytes of `d` (not the component's
    own stored copy) -- a forgery the dependent's own gate cannot see fails
    here (spec/verification.md)."""
    parsed = kernel.load_recipe(d)
    from_map = {}
    for step in parsed.get("step", []):
        if step["kind"] == "produce" and "from" in step:
            from_map.setdefault(step["from"], []).append(step["output"])

    if not from_map:
        return {"ok": True, "layers": []}

    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    components = manifest.get("components") or {}

    ok = True
    layers = []
    for name, outputs in from_map.items():
        rel = components.get(name)
        comp_dir = os.path.join(d, rel) if rel else None
        if comp_dir is None or not os.path.isdir(comp_dir):
            layers.append({"name": name, "bytes_from": outputs,
                           "ok": False, "status": "unresolved"})
            ok = False
            continue
        try:
            comp_manifest = kernel.read_manifest(comp_dir)
        except kernel.ClaimError:
            layers.append({"name": name, "bytes_from": outputs,
                           "ok": False, "status": "unresolved"})
            ok = False
            continue
        produce_from = {out: os.path.join(d, out) for out in outputs
                        if os.path.isfile(os.path.join(d, out))}
        result = kernel.audit(comp_dir, produce_from=produce_from)
        layer_ok = result["ok"]
        ok = ok and layer_ok
        layers.append({"name": name, "root": comp_manifest["root"],
                       "bytes_from": outputs, "ok": layer_ok,
                       "status": "audited" if layer_ok else "broken"})
    return {"ok": ok, "layers": layers}


def crosscheck_deep(m1: str, m2: str, m3: str, **kwargs) -> dict:
    """`kernel.crosscheck`, plus a deep audit of every leg: a `from`-sourced
    layer must re-earn its own gate on each leg's shipped bytes, not merely
    pass the dependent's own (blind) gate."""
    base = kernel.crosscheck(m1, m2, m3, **kwargs)
    deep = {"M1": audit_deep(m1), "M2": audit_deep(m2), "M3": audit_deep(m3)}
    deep_ok = all(v["ok"] for v in deep.values())
    return {**base, "satisfied": base["satisfied"] and deep_ok, "deep_audit": deep}


# ---------------------------------------------------------------------------
# the signature chain: folds bottom-up over the component DAG
# ---------------------------------------------------------------------------

def sign_root(d: str, ws: str = None) -> str:
    """The signature-chain node for `d`, folding every declared component's
    own node beneath it (spec/kernel-api.md's `sign_node`) -- a change at
    one layer moves its node and every node above, never one below."""
    manifest = kernel.read_manifest(d)
    root_value = manifest["root"]
    digest_value = kernel.build_digest(d)
    components = manifest.get("components") or {}
    links = []
    for name, rel in components.items():
        comp_dir = os.path.join(d, rel)
        if not os.path.isdir(comp_dir) and ws is not None:
            alt = os.path.join(ws, _STORE_SEALED, name)
            if os.path.isdir(alt):
                comp_dir = alt
        if not os.path.isdir(comp_dir):
            raise kernel.ClaimError(f"declared component {name!r} is missing: {comp_dir!r}")
        links.append(sign_root(comp_dir, ws))
    return kernel.sign_node(root_value, digest_value, links)
