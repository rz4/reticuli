"""Composition — claims become components.

A workspace's claims live in its claim stores, `.reticuli/sealed/<name>/` and
`.reticuli/signed/<name>/`. A pinned input whose bytes match a registered
claim's output is a **dependency**: content-addressed, so it survives copies.
`pull` brings a claim into a workspace as pinned inputs; `deps` draws the DAG.

Duality: `signed` is a claim's view of itself; a pinned input is a dependent's
view of the same claim. A claim carrying a recorded proof is the archetypal
dependency.

This layer uses the kernel's PUBLIC surface only. Two consequences are visible
below: `seal_with` writes the manifest keys the kernel's `seal` does not own
(`components`, `proof`), and `_phase` absorbs the refusal the v2 kernel raises
for a directory that holds no readable claim.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel
from ._util import copy_into, declared_inputs, hash_bytes, step_output, write_json

STORES = ("sealed", "signed")     # v1: the liquid/solid drawers
DEPS = "deps"                     # where a rebuilt or imported claim keeps the
                                  # component claims it was built over


def _phase(d: str) -> str:
    """`kernel.phase`, with an unreadable claim reported as `draft`.

    v1's phase answered "vapor" for any directory that held no claim. The v2
    kernel REFUSES a directory whose recipe or manifest it cannot read — a
    refusal is more honest than a positive an auditor would misread — so
    scanning a claim store has to absorb that refusal here, or one stray entry
    would crash the scan.
    """
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "draft"


def _hash_file(path: str) -> str:
    """sha256 of a file's bytes.

    v1 called `kernel._hf`. The v2 kernel keeps its file hasher private, so the
    layer hashes the bytes itself. This is content comparison, never identity:
    the kernel's hasher stays the authority for what a root is made of.
    """
    with open(path, "rb") as f:
        return hash_bytes(f.read())


def seal_with(claimdir: str, components: list | None = None,
              proof: dict | None = None) -> dict:
    """Seal, and record the manifest residue the kernel's identity does not carry.

    The v2 kernel's `seal` computes the root and writes `{name, root}` and
    nothing else; the optional `components` (the links this claim layers on) and
    `proof` (a recorded crosscheck) are manifest residue this layer owns
    (spec/claim-format.md). v1 passed both to `kernel.seal`. Here they are
    merged onto the manifest the kernel just wrote — and a later bare
    `kernel.seal` keeps them, because the v2 kernel preserves manifest keys it
    does not own.
    """
    manifest = kernel.seal(claimdir)
    if components:
        manifest["components"] = components
    if proof:
        manifest["proof"] = proof
    if components or proof:
        write_json(os.path.join(claimdir, kernel.MANIFEST), manifest)
    return manifest


def claims(ws: str) -> list[dict]:
    """Sealed claims in the workspace's claim stores."""
    ws = os.path.abspath(ws)
    found: list[dict] = []
    for store in STORES:
        base = os.path.join(ws, kernel.STORE, store)
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            claim = os.path.join(base, entry)
            if _phase(claim) == "draft":
                continue
            m = kernel.read_manifest(claim)
            found.append({"name": m["name"], "root": m["root"],
                          "phase": _phase(claim),
                          "store": store,
                          "path": os.path.relpath(claim, ws).replace(os.sep, "/")})
    return found


def _index(ws: str) -> dict:
    """{output_hash: (component, root, output)} over every registered claim."""
    idx: dict[str, tuple[str, str, str]] = {}
    for r in claims(ws):
        claim = os.path.join(ws, r["path"])
        recipe = kernel.load_recipe(claim)
        for step in recipe.get("step", []):
            f = os.path.join(claim, step["output"])
            if os.path.isfile(f):
                idx.setdefault(_hash_file(f), (r["name"], r["root"], step["output"]))
    return idx


def detect_components(ws: str, inputs: list[str]) -> list[dict]:
    """Content-match each pinned input against the registry: the components this
    claim depends on."""
    idx = _index(ws)
    links = []
    for s in inputs:
        f = os.path.join(ws, s)
        if os.path.isfile(f):
            hit = idx.get(_hash_file(f))
            if hit:
                links.append({"input": s, "component": hit[0], "root": hit[1], "output": hit[2]})
    return links


def pull(component: str, into: str = ".") -> dict:
    """Bring a sealed claim into this workspace as a dependency: register it in
    the claim store and materialize its outputs as pinned inputs a gate can read."""
    src = os.path.abspath(component)
    if _phase(src) == "draft":
        raise kernel.ClaimError(f"pull: no claim in {component}")
    m = kernel.read_manifest(src)
    name = m["name"]
    store = _phase(src)               # signed only if the authorization verifies
    dst = os.path.join(os.path.abspath(into), kernel.STORE, store, name)
    if os.path.exists(dst):
        raise kernel.ClaimError(f"pull: '{name}' is already in the registry ({store}/{name})")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(src, dst)
    recipe = kernel.load_recipe(src)
    materialized = []
    for step in recipe.get("step", []):
        f = os.path.join(src, step["output"])
        if os.path.isfile(f):
            copy_into(f, os.path.join(os.path.abspath(into), step["output"]))
            materialized.append(step["output"])
    return {"component": name, "root": m["root"], "store": store,
            "registered": os.path.relpath(dst, os.path.abspath(into)).replace(os.sep, "/"),
            "materialized": materialized}


def _registry_of(claim: str) -> str:
    """The workspace whose claim stores hold this claim's components. A
    self-hosting claim hosts them in its *own* store (repo root:
    .reticuli/sealed/<component>); a claim sitting in a store
    (<ws>/.reticuli/<store>/<name>) finds them three directories up."""
    p = os.path.abspath(claim)
    for store in STORES:
        if os.path.isdir(os.path.join(p, kernel.STORE, store)):
            return p
    ws = os.path.dirname(os.path.dirname(os.path.dirname(p)))
    return ws if os.path.isdir(os.path.join(ws, kernel.STORE)) else os.path.dirname(p)


def rebuild_chain(claim: str, producer: str, into: str, ws: str | None = None) -> dict:
    """DAG-aware rebuild: recursively regenerate a claim *and its component
    dependencies*, bottom-up. Each component is rebuilt from its own recipe and
    its output threaded up as this claim's input — so the whole chain reproduces
    from the leaves, not just one layer. This is the layered self-host: rebuild
    the kernel, thread it into the CLI, and so on.
    """
    claim = os.path.abspath(claim)
    into = os.path.abspath(into)
    ws = os.path.abspath(ws) if ws else _registry_of(claim)
    manifest = kernel.read_manifest(claim)
    inputs = set(declared_inputs(kernel.load_recipe(claim)))
    by_root = {r["root"]: os.path.join(ws, r["path"]) for r in claims(ws)}

    input_from: dict[str, str] = {}
    produce_from: dict[str, str] = {}
    rebuilt = []
    # group links by component — one component may supply several outputs, but is
    # rebuilt exactly once (into deps/<name>) and its outputs threaded up
    groups: dict[tuple, list] = {}
    for link in manifest.get("components", []):
        groups.setdefault((link["component"], link["root"]), []).append(link)

    # v1 rebuilt each component straight into `into/.reticuli/deps/<name>` and
    # passed exist_ok to realize. The v2 kernel's `rebuild` refuses a target that
    # already holds bytes and takes no exist_ok, so components are rebuilt in a
    # staging area, threaded from there, and moved into place once the dependent
    # is built. Where they end up is unchanged.
    staging = tempfile.mkdtemp(prefix="reticuli-deps-")
    moves: list[tuple[str, str]] = []
    try:
        for (name, root), links in groups.items():
            comp = by_root.get(root)
            if comp is None:
                raise kernel.ClaimError(
                    f"rebuild_chain: component {name}@{root[:12]}… not in registry")
            home = os.path.join(into, kernel.STORE, DEPS, name)
            # v1: a dep already sealed at the expected root is reused, so an
            # interrupted rebuild never re-pays for completed layers (crosscheck /
            # audit still validates everything at the end). NOTE: the v2 kernel's
            # `rebuild` refuses any target that already holds bytes, so a target
            # carrying half a chain is refused outright and this reuse no longer
            # fires on a resumed run. It is kept as the reuse rule, not deleted,
            # because nothing above it should encode that limitation.
            if (_phase(home) != "draft"
                    and kernel.read_manifest(home)["root"] == root):
                built, sub = home, {"root": root}
            else:
                built = os.path.join(staging, name)
                sub = rebuild_chain(comp, producer, built, ws)   # recurse: leaf first
                moves.append((built, home))
            rebuilt.append({"component": name, "root": sub["root"]})
            for link in links:
                src = os.path.join(built, link["output"])
                # a link into a pinned input is data; into a produce step it is
                # generated code
                (input_from if link["input"] in inputs
                 else produce_from)[link["input"]] = src

        result = kernel.rebuild(claim, producer, into, produce_from=produce_from,
                                input_from=input_from)
        for built, home in moves:
            os.makedirs(os.path.dirname(home), exist_ok=True)
            shutil.move(built, home)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # carry the provenance forward: rebuild seals a bare {name, root}, but a redo
    # of a composed claim must keep the links it was rebuilt from (same root —
    # components are manifest residue, outside the claim) so its structure is not
    # lost. Without this a rebuilt claim's component tree is a stump.
    if manifest.get("components"):
        seal_with(into, components=manifest["components"])
    result["rebuilt_components"] = rebuilt
    return result


def _stores(*bases: str) -> list[str]:
    """Every sealed claim reachable from these stores: the sealed/signed stores,
    plus `deps` (where a rebuilt or imported claim keeps the component claims it
    was built over)."""
    out: list[str] = []
    for base in bases:
        for store in STORES + (DEPS,):
            box = os.path.join(base, kernel.STORE, store)
            if os.path.isdir(box):
                for entry in sorted(os.listdir(box)):
                    claim = os.path.join(box, entry)
                    if os.path.isdir(claim) and _phase(claim) != "draft":
                        out.append(claim)
    return out


def resolve(root: str, claim: str, ws: str | None = None) -> str | None:
    """Find the sealed claim with this root: in the claim's own store first
    (deps travel with an export), then the workspace registry."""
    claim = os.path.abspath(claim)
    ws = os.path.abspath(ws) if ws else _registry_of(claim)
    for found in _stores(claim, ws):
        try:
            if kernel.read_manifest(found)["root"] == root:
                return found
        except kernel.ClaimError:
            continue
    return None


def chain(claim: str, ws: str | None = None) -> list[dict]:
    """The component chain, leaf-ward: [{name, root, path|None}] for every
    component this claim (transitively) layers on, each once."""
    claim = os.path.abspath(claim)
    seen: set[str] = set()
    out: list[dict] = []

    def walk(d: str) -> None:
        m = kernel.read_manifest(d)
        for link in m.get("components", []):
            if link["root"] in seen:
                continue
            seen.add(link["root"])
            comp = resolve(link["root"], claim, ws)
            out.append({"name": link["component"], "root": link["root"], "path": comp})
            if comp:
                walk(comp)

    walk(claim)
    return out


def _layers(claim: str, ws: str | None = None) -> tuple[list[dict], bool]:
    """Re-earn every component's verdict against the bytes THIS claim ships.

    Each component in the chain runs ITS OWN gates over the dependent's
    generated bytes: the component's recipe and inputs (its claim) in a fresh
    workspace, the dependent's generated bytes standing in for the component's
    produce outputs, the pinned verdict required to reproduce the component's
    sealed bytes. A layer whose claim cannot be found is a failed layer — an
    unresolvable component is not an audited one.
    """
    claim = os.path.abspath(claim)
    layers: list[dict] = []
    ok = True
    for c in chain(claim, ws):
        if c["path"] is None:
            layers.append({"name": c["name"], "root": c["root"], "ok": False,
                          "status": "unresolved", "gates": [], "environment": []})
            ok = False
            continue
        recipe = kernel.load_recipe(c["path"])
        supplied = {step_output(s): os.path.join(claim, step_output(s))
                    for s in recipe.get("step", []) if s["kind"] == "produce"
                    and os.path.isfile(os.path.join(claim, step_output(s)))}
        try:
            a = kernel.audit(c["path"], produce_from=supplied)
            # the v2 kernel's audit reports no name of its own, so the layer
            # names the layer from the component link it walked
            layer = {"name": c["name"], "root": c["root"], "ok": a["ok"],
                    "status": "earned" if a["ok"] else
                    ("environment" if a["environment"] else "carried or broken"),
                    "gates": a["gates"], "environment": a["environment"],
                    "bytes_from": sorted(supplied)}
        except kernel.ClaimError as e:
            layer = {"name": c["name"], "root": c["root"], "ok": False,
                    "status": f"refused: {e}", "gates": [], "environment": []}
        layers.append(layer)
        ok = ok and layer["ok"]
    return layers, ok


def audit_deep(claim: str, ws: str | None = None) -> dict:
    """Composed audit — gates compose, verdicts never carry. This claim's own
    gates run first (kernel.audit); then every component in the chain re-earns
    its verdict on the bytes this claim ships (`_layers`). The result keeps
    kernel.audit's shape and adds `layers`."""
    claim = os.path.abspath(claim)
    top = kernel.audit(claim)
    layers, layers_ok = _layers(claim, ws)
    return {**top, "ok": bool(top["ok"] and layers_ok), "layers": layers}


def crosscheck_deep(m1: str, m2: str, m3: str, **kw) -> dict:
    """The invariant over composed claims: every machine's whole chain re-earns
    its verdicts.

    v1 handed `kernel.three_machine` a deep `auditor` to swap in. The v2 kernel's
    `crosscheck` takes no auditor, so the deep verdict is composed OVER the
    kernel's instead of inside it: the kernel's crosscheck (which already audits
    each machine shallowly) AND every machine's component chain re-earning its
    own verdicts. Same invariant, and the kernel stays the authority on the rest
    of it — identity, byte-reuse, the cost envelope, the mutation floor.
    """
    result = kernel.crosscheck(m1, m2, m3, **kw)
    audited = dict(result["audited"])
    layers: dict[str, list] = {}
    for label, machine in (("M1", m1), ("M2", m2), ("M3", m3)):
        rows, ok = _layers(machine)
        layers[label] = rows
        audited[label] = bool(audited.get(label)) and ok
    result["audited"] = audited
    result["layers"] = layers
    result["satisfied"] = bool(result["satisfied"] and all(audited.values()))
    return result


def record_proof_deep(m1: str, m2: str, m3: str, **kw) -> dict:
    """Run the deep crosscheck and, on a pass, seal the proof onto M1 as residue."""
    result = crosscheck_deep(m1, m2, m3, **kw)
    result["proof_recorded"] = False
    if result["satisfied"]:
        seal_with(m1, proof={"kind": "crosscheck", "m2": result["roots"]["M2"],
                             "m3": result["roots"]["M3"]},
                  components=kernel.read_manifest(m1).get("components") or None)
        result["proof_recorded"] = True
    return result


def sign_root(claim: str, ws: str | None = None) -> str:
    """The chain root: fold this claim's signature node over its components',
    bottom-up (leaf first), via kernel.sign_node. Signed identity binds the whole
    DAG — the kernel's node is the genesis, and a change at any layer moves its
    node and every node above it, never one below. This composes the invariant's
    fold; it does not sign — authorization is the signing ceremony's job
    (attest.sign)."""
    claim = os.path.abspath(claim)
    ws = os.path.abspath(ws) if ws else _registry_of(claim)
    m = kernel.read_manifest(claim)
    by_root = {r["root"]: os.path.join(ws, r["path"]) for r in claims(ws)}
    comp_roots = {link["root"] for link in m.get("components", [])}
    missing = sorted(cr for cr in comp_roots if cr not in by_root)
    if missing:
        # a chain root over an incomplete DAG is not a chain root: a declared
        # component that cannot be resolved refuses the fold, never elides
        raise kernel.ClaimError(
            "sign_root: declared component(s) not in the registry: "
            + ", ".join(cr[:12] + "…" for cr in missing))
    below = [sign_root(by_root[cr], ws) for cr in sorted(comp_roots)]
    return kernel.sign_node(m["root"], kernel.build_digest(claim), below)


def structure(claim: str, ws: str | None = None) -> dict:
    """The claim lens: the chain of layers, leaf-ward. Each layer shows its
    pinned inputs (the claim), its own generated stratum, the files its
    component supplies, and its pinned verdicts — the repository's structure as
    the claim sees it."""
    claim = os.path.abspath(claim)
    ws = os.path.abspath(ws) if ws else _registry_of(claim)
    by_root = {r["root"]: os.path.join(ws, r["path"]) for r in claims(ws)}

    def node(d: str) -> dict:
        m = kernel.read_manifest(d)
        recipe = kernel.load_recipe(d)
        steps = recipe.get("step", [])
        supplied = {f for s in steps if s["kind"] == "produce" and "from" in s
                    for f in [step_output(s)]}
        groups: dict[tuple, list] = {}
        for link in m.get("components", []):
            groups.setdefault((link["component"], link["root"]), []).append(link["input"])
        n = {"name": m["name"], "root": m["root"],
             "phase": _phase(d),
             "inputs": declared_inputs(recipe),
             "generated": [step_output(s) for s in steps if s["kind"] == "produce"
                           and s.get("class") == "generated"
                           and step_output(s) not in supplied],
             "pinned": [step_output(s) for s in steps
                        if s.get("class", "pinned") != "generated"],
             "components": []}
        for (name, root), files in groups.items():
            comp = by_root.get(root)
            n["components"].append({"component": name, "root": root,
                                    "files": sorted(set(files)),
                                    "layer": node(comp) if comp else None})
        return n

    return {"workspace": ws, "claim": node(claim)}


def deps(ws: str) -> dict:
    """The component DAG: each claim's `components` provenance, with broken links
    (upstream no longer in the registry) flagged. Includes the workspace's own
    top-level claim — a self-hosting claim layers on its store, but isn't in it."""
    ws = os.path.abspath(ws)
    found = claims(ws)
    if _phase(ws) != "draft":
        m = kernel.read_manifest(ws)
        if m["root"] not in {r["root"] for r in found}:
            found = [{"name": m["name"], "root": m["root"], "store": ".", "path": ".",
                      "phase": _phase(ws)}] + found
    roots = {r["root"] for r in found}
    nodes = []
    for r in found:
        m = kernel.read_manifest(ws if r["path"] == "." else os.path.join(ws, r["path"]))
        edges = [{"input": link["input"], "component": link["component"],
                  "root": link["root"], "status": "ok" if link["root"] in roots else "missing"}
                 for link in m.get("components", [])]
        nodes.append({"name": r["name"], "root": r["root"], "phase": r["phase"],
                      "depends_on": edges})
    return {"workspace": ws, "claims": nodes}
