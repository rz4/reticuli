"""The registry: claims meeting claims.

A claim store, content-addressed component links, a DAG-aware rebuild, and the
composed audit. The rule the whole layer serves: **gates compose, verdicts
never carry.** A dependent that ships a component's code must have that code
re-earned by the component's OWN gate, on the shipped bytes -- the dependent's
gate is blind to a forgery by construction.
"""
import os
import shutil
import tempfile

from . import kernel
from ._util import copy_into, hash_bytes, read_json, safe_path

#: Where a claim keeps the claims it depends on.
SEALED = ".reticuli/sealed"
DEPS = ".reticuli/deps"


# --------------------------------------------------------------------------
# resolving a component

def _stores(*places) -> list:
    """Every directory that may hold a sealed claim, in order of nearness."""
    dirs = []
    for place in places:
        if not place:
            continue
        for relative in (SEALED, DEPS):
            where = os.path.join(place, relative)
            if os.path.isdir(where) and where not in dirs:
                dirs.append(where)
    return dirs


def _recomputed(where: str):
    try:
        return kernel.verify(where)["recomputed"]
    except kernel.ClaimError:
        return None


def _resolve(name: str, root: str, dirs: list):
    """A component resolves by ROOT, wherever it lives in the store.

    The name is tried first because it is O(1) and almost always right; the
    scan exists because the self-claim chain stages every layer FLAT in the
    top claim's shared store, and two independently written walkers each
    resolved by physical nesting and reported the next layer unresolved.
    """
    for where in dirs:
        candidate = os.path.join(where, name)
        if os.path.isdir(candidate) and _recomputed(candidate) == root:
            return candidate
    for where in dirs:
        for entry in sorted(os.listdir(where)):
            candidate = os.path.join(where, entry)
            if os.path.isdir(candidate) and _recomputed(candidate) == root:
                return candidate
    return None


def _links(claim: str) -> list:
    try:
        manifest = kernel.read_manifest(claim)
    except kernel.ClaimError:
        return []
    links = manifest.get("components") or []
    return [link for link in links if isinstance(link, dict)]


def _grouped(links: list) -> list:
    """One group per (component, root): a component is judged exactly once."""
    order, groups = [], {}
    for link in links:
        key = (link.get("component"), link.get("root"))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(link)
    return [(key, groups[key]) for key in order]


def _from_steps(claim: str) -> dict:
    try:
        parsed = kernel.load_recipe(claim)
    except kernel.ClaimError:
        return {}
    return {step["output"]: step.get("from")
            for step in kernel.produces(parsed) if step.get("output")}


# --------------------------------------------------------------------------
# the store

def claims(ws: str) -> list:
    """Every claim in a workspace's store."""
    drawer = os.path.join(ws, SEALED)
    found = []
    for name in sorted(os.listdir(drawer) if os.path.isdir(drawer) else []):
        where = os.path.join(drawer, name)
        if not os.path.isdir(where):
            continue
        try:
            manifest = kernel.read_manifest(where)
        except kernel.ClaimError:
            continue
        try:
            phase = kernel.phase(where)
        except kernel.ClaimError:
            phase = "broken"
        found.append({"name": manifest["name"], "root": manifest["root"],
                      "phase": phase, "path": where,
                      "components": len(manifest.get("components") or [])})
    return found


def detect_components(ws: str, inputs) -> list:
    """A pinned input that content-matches a stored claim's output IS a link.

    Content-addressed, so the link is a fact about bytes rather than a note
    about where a file came from -- and the composed audit re-earns it.
    """
    catalogue = []
    for entry in claims(ws):
        try:
            parsed = kernel.load_recipe(entry["path"])
        except kernel.ClaimError:
            continue
        outputs = {}
        for step in kernel.load_recipe(entry["path"]).get("step") or []:
            output = step.get("output")
            path = safe_path(entry["path"], output or "")
            if output and path and os.path.isfile(path):
                with open(path, "rb") as handle:
                    outputs[output] = hash_bytes(handle.read())
        catalogue.append((entry, outputs))
    links = []
    for declared in inputs or []:
        path = safe_path(ws, declared)
        if not path or not os.path.isfile(path):
            continue
        with open(path, "rb") as handle:
            digest = hash_bytes(handle.read())
        for entry, outputs in catalogue:
            for output, other in sorted(outputs.items()):
                if other == digest:
                    links.append({"input": declared,
                                  "component": entry["name"],
                                  "root": entry["root"], "output": output})
                    break
    return links


def seal_with(claim: str, components=None, proof=None) -> dict:
    """Seal, recording the component links (and a proof) as manifest residue."""
    residue = {}
    if components is not None:
        residue["components"] = components
    if proof is not None:
        residue["proof"] = proof
    return kernel.seal(claim, **residue)


def deps(ws: str) -> dict:
    """The dependency DAG as the store can see it."""
    rows = []
    for entry in claims(ws):
        dirs = _stores(entry["path"], ws)
        edges = []
        for (name, root), group in _grouped(_links(entry["path"])):
            resolved = _resolve(name, root, dirs)
            edges.append({"component": name, "root": root,
                          "inputs": [l.get("input") for l in group],
                          "status": "ok" if resolved else "unresolved",
                          "path": resolved})
        rows.append({"name": entry["name"], "root": entry["root"],
                     "phase": entry["phase"], "depends_on": edges})
    return {"claims": rows, "workspace": ws}


# --------------------------------------------------------------------------
# the composed audit

def _judge_layer(current: str, bytes_root: str, name: str, root: str,
                 group: list, dirs: list, strict: bool = True) -> dict:
    resolved = _resolve(name, root, dirs)
    inputs = [link.get("input") for link in group]
    if resolved is None:
        return {"name": name, "root": root, "ok": False,
                "status": "unresolved", "bytes_from": inputs, "path": None,
                "gates": []}
    from_steps = _from_steps(current)
    produce_from, forged = {}, []
    for link in group:
        declared = link.get("input")
        output = link.get("output") or declared
        source = safe_path(bytes_root, declared) if bytes_root else None
        if not source or not os.path.isfile(source):
            source = safe_path(current, declared)
        if not source or not os.path.isfile(source):
            forged.append(declared)
            continue
        if from_steps.get(declared):
            produce_from[output] = source
            continue
        theirs = safe_path(resolved, output)
        if not theirs or not os.path.isfile(theirs):
            forged.append(declared)
            continue
        with open(source, "rb") as mine, open(theirs, "rb") as other:
            if mine.read() != other.read():
                forged.append(declared)
    if forged:
        return {"name": name, "root": root, "ok": False,
                "status": f"forged attribution: {', '.join(sorted(forged))}",
                "bytes_from": inputs, "path": resolved, "gates": []}
    judged = kernel.audit(resolved, produce_from=produce_from or None,
                          strict=strict)
    return {"name": name, "root": root, "ok": bool(judged["ok"]),
            "status": judged["verdict"], "bytes_from": inputs,
            "path": resolved, "gates": judged["gates"]}


def _walk(current: str, bytes_root: str, ws, layers: list, seen: set,
          strict: bool = True) -> None:
    dirs = _stores(current, bytes_root, ws)
    for (name, root), group in _grouped(_links(current)):
        key = (name, root)
        if key in seen:
            continue
        seen.add(key)
        row = _judge_layer(current, bytes_root, name, root, group, dirs,
                           strict=strict)
        layers.append(row)
        if row["path"]:
            _walk(row["path"], bytes_root, ws, layers, seen, strict=strict)


def audit_deep(claim: str, ws: str | None = None, strict: bool = True,
               mutants: int | None = None) -> dict:
    """Re-earn this claim's own gates AND every component's, however deep.

    A composed verdict keeps `kernel.audit`'s shape, because the top claim's
    own gates compose too.
    """
    result = dict(kernel.audit(claim, strict=strict, mutants=mutants))
    layers: list = []
    _walk(claim, claim, ws, layers, set(), strict=strict)
    result["layers"] = layers
    broken = [row for row in layers if not row["ok"]]
    result["ok"] = bool(result["ok"]) and not broken
    if broken and result.get("verdict") == "earned":
        result["verdict"] = "composed"
    result["composed"] = True
    return result


# --------------------------------------------------------------------------
# the signature chain over the DAG

def sign_root(claim: str, ws: str | None = None) -> str:
    """Signed identity, folded bottom-up: the floor is the significant digit."""
    checked = kernel.verify(claim)
    dirs = _stores(claim, ws)
    links = []
    for (name, root), _group in _grouped(_links(claim)):
        resolved = _resolve(name, root, dirs)
        if resolved is None:
            raise kernel.ClaimError(
                f"a chain root over an incomplete DAG is not a chain root: "
                f"the declared component {name!r} ({root[:16]}...) is not in "
                f"the registry")
        links.append(sign_root(resolved, ws))
    return kernel.sign_node(checked["root"], kernel.build_digest(claim), links)


def structure(claim: str, ws: str | None = None) -> dict:
    """The claim and everything beneath it, as a tree a reader can walk."""
    checked = kernel.verify(claim)
    try:
        phase = kernel.phase(claim)
    except kernel.ClaimError:
        phase = "broken"
    dirs = _stores(claim, ws)
    children = []
    for (name, root), group in _grouped(_links(claim)):
        resolved = _resolve(name, root, dirs)
        children.append({
            "component": name, "root": root,
            "inputs": [link.get("input") for link in group],
            "status": "ok" if resolved else "unresolved",
            "tree": structure(resolved, ws) if resolved else None})
    return {"name": checked["name"], "root": checked["root"],
            "ok": checked["ok"], "phase": phase, "components": children,
            "layers": len(children)}


# --------------------------------------------------------------------------
# rebuilding a chain

def rebuild_chain(claim: str, producer: str, into: str,
                  ws: str | None = None, reuse: bool = False,
                  guidance: bool = True, producer_env=None) -> dict:
    """Reproduce from the leaves: a component is rebuilt before its dependent.

    With `reuse`, the sealed component is threaded in instead -- the layered
    build for large software: seal a component once, build on it without
    repaying to reproduce it.
    """
    links = _links(claim)
    from_steps = _from_steps(claim)
    dirs = _stores(claim, ws)
    produce_from, input_from, rebuilt = {}, {}, []
    scratch = tempfile.mkdtemp(prefix="reticuli-chain-")
    try:
        for (name, root), group in _grouped(links):
            resolved = _resolve(name, root, dirs)
            if resolved is None:
                raise kernel.ClaimError(
                    f"cannot rebuild the chain: component {name!r} is not in "
                    f"the registry")
            if reuse:
                source = resolved
            else:
                source = os.path.join(scratch, name)
                rebuild_chain(resolved, producer, source, ws=ws, reuse=reuse,
                              guidance=guidance, producer_env=producer_env)
                rebuilt.append({"component": name, "root": root,
                                "path": source})
            for link in group:
                declared = link.get("input")
                output = link.get("output") or declared
                origin = os.path.join(source, output)
                if from_steps.get(declared):
                    produce_from[declared] = origin
                else:
                    input_from[declared] = origin
        result = kernel.rebuild(claim, producer, into,
                                produce_from=produce_from or None,
                                input_from=input_from or None,
                                guidance=guidance,
                                producer_env=producer_env)
        if links:
            seal_with(result["into"], components=links)
            for (name, root), _group in _grouped(links):
                resolved = _resolve(name, root, dirs)
                if resolved is None:
                    continue
                drawer = os.path.join(result["into"], SEALED, name)
                if not os.path.exists(drawer):
                    _copy_claim(resolved, drawer)
        result["rebuilt_components"] = rebuilt
        return result
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# --------------------------------------------------------------------------
# pulling a claim, and its closure, into a workspace

def _copy_claim(source: str, target: str) -> None:
    """Copy one claim's own bytes -- never its store of other claims.

    Copying the store too is what turns a shared ancestor into 2^(k-1) copies
    of the deepest layer; the closure is laid down FLAT instead, so each
    dependency's bytes appear O(1) times.
    """
    os.makedirs(target, exist_ok=True)
    for base, dirs, files in os.walk(source, followlinks=False):
        relative = os.path.relpath(base, source)
        parts = [] if relative == "." else relative.split(os.sep)
        if parts[:2] in ([".reticuli", "sealed"], [".reticuli", "deps"]):
            dirs[:] = []
            continue
        for name in files:
            copy_into(os.path.join(base, name),
                      os.path.join(target, relative, name)
                      if relative != "." else os.path.join(target, name))


def _closure(claim: str, ws: str | None, seen: dict) -> dict:
    """Every claim beneath this one, keyed by (name, root): O(1) per member."""
    dirs = _stores(claim, ws)
    for (name, root), _group in _grouped(_links(claim)):
        if (name, root) in seen:
            continue
        resolved = _resolve(name, root, dirs)
        if resolved is None:
            continue
        seen[(name, root)] = resolved
        _closure(resolved, ws, seen)
    return seen


def pull(claim: str, ws: str) -> dict:
    """Add another claim as a dependency: it lands, and it stands alone."""
    checked = kernel.verify(claim)
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"will not pull a broken claim: {claim} does not verify")
    drawer = os.path.join(ws, SEALED)
    os.makedirs(drawer, exist_ok=True)
    members = _closure(claim, None, {})
    for (name, _root), where in sorted(members.items(),
                                       key=lambda item: item[0][0]):
        target = os.path.join(drawer, name)
        if not os.path.isdir(target):
            _copy_claim(where, target)
    landing = os.path.join(drawer, checked["name"])
    if not os.path.isdir(landing):
        _copy_claim(claim, landing)
    try:
        manifest = kernel.read_manifest(claim)
        if manifest.get("components"):
            seal_with(landing, components=manifest["components"])
    except kernel.ClaimError:
        pass

    parsed = kernel.load_recipe(claim)
    materialized = []
    for step in parsed.get("step") or []:
        output = step.get("output")
        source = safe_path(claim, output or "")
        if not output or not source or not os.path.isfile(source):
            continue
        copy_into(source, os.path.join(ws, output))
        materialized.append(output)
    return {"pulled": checked["name"], "root": checked["root"],
            "materialized": materialized,
            "closure": sorted(name for name, _ in members)}


# --------------------------------------------------------------------------
# the deep crosscheck

def crosscheck_deep(m1: str, m2: str, m3: str, ws: str | None = None,
                    **kwargs) -> dict:
    """The three-machine test, with every leg's whole chain re-earned.

    A shallow crosscheck is fooled by a forged layer -- the dependent's gate
    cannot see it. This one is not.
    """
    result = dict(kernel.crosscheck(m1, m2, m3, **kwargs))
    audited = dict(result["audited"])
    rejected = list(result["rejected"])
    for name, leg in (("M1", m1), ("M2", m2), ("M3", m3)):
        if not os.path.isdir(leg):
            continue
        deep = audit_deep(leg, ws)
        if not deep["ok"] and audited.get(name):
            audited[name] = False
            rejected.append(f"{name} did not re-earn its composed verdicts")
        elif not deep["ok"]:
            audited[name] = False
    result["audited"] = audited
    result["rejected"] = rejected
    result["verdict"] = ("reject" if rejected
                         else ("incomplete" if result["incomplete"]
                               else "accept"))
    result["satisfied"] = result["verdict"] == "accept"
    result["composed"] = True
    return result


def record_proof_deep(m1: str, m2: str, m3: str, ws: str | None = None,
                      **kwargs) -> dict:
    """Run the deep crosscheck and, on a pass, record the proof on M1."""
    if not os.path.isdir(m1):
        raise kernel.ClaimError(
            "a recorded proof lands on M1's manifest, so M1 must be a claim "
            "directory, never a frozen record")
    outcome = crosscheck_deep(m1, m2, m3, ws=ws, **kwargs)
    if not outcome["satisfied"]:
        return {"proof_recorded": False, "crosscheck": outcome}
    manifest = kernel.read_manifest(m1)
    proof = {"kind": "crosscheck_deep", "when": kernel._now(),
             "m2": outcome["roots"]["M2"], "m3": outcome["roots"]["M3"],
             "verdict": outcome["verdict"]}
    seal_with(m1, components=manifest.get("components"), proof=proof)
    return {"proof_recorded": True, "crosscheck": outcome, "proof": proof}


def rebuild_claim(claim: str, producer: str, into: str, **kwargs) -> dict:
    """The one-layer rebuild, kept expressed beside the chain form."""
    return kernel.rebuild(claim, producer, into, **kwargs)
