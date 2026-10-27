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
from ._util import (
    copy_into,
    declared_inputs,
    hash_bytes,
    now,
    step_output,
    write_json,
)

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


def copy_claim(src: str, dst: str) -> None:
    """Copy a claim with one local copy of each reachable dependency.

    Copying nested stores recursively unfolds shared ancestors (including
    directory symlinks) into a tree. Resolve the closure before copying, then
    flatten it into a private store so the result survives removal of src.
    """
    src = os.path.abspath(src)
    dependencies = chain(src)
    missing = [c["name"] for c in dependencies if c["path"] is None]
    if missing:
        raise kernel.ClaimError(f"copy: unresolved components: {', '.join(missing)}")

    def shallow(source: str, target: str) -> None:
        metadata = os.path.join(os.path.abspath(source), kernel.STORE)

        def ignore(directory, names):
            if os.path.abspath(directory) == metadata:
                return set(names).intersection((*STORES, DEPS))
            return ()

        shutil.copytree(source, target, ignore=ignore)

    shallow(src, dst)
    for component in dependencies:
        # Roots, rather than names, avoid collisions between named versions.
        target = os.path.join(dst, kernel.STORE, DEPS, component["root"])
        shallow(component["path"], target)


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
    copy_claim(src, dst)
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


def _drawer(claimdir: str, name: str) -> str | None:
    """The registered copy of component `name` in this claim's own drawer."""
    for store in STORES:
        d = os.path.join(claimdir, kernel.STORE, store, name)
        if os.path.isfile(os.path.join(d, kernel.MANIFEST)):
            return d
    return None


def _link_fresh(claimdir: str, link: dict, member: dict) -> bool:
    """Does this dependent's view of a sibling component agree with the
    sibling as it stands now? Three things must hold: the link names the
    sibling's current root, the drawer holds a copy at that root, and the
    copy's own component links match the sibling's — a root-preserving
    reseal of the sibling changes its LINKS without moving its root, and a
    drawer copy frozen on the old links carries a stale closure that only a
    deep audit would trip over."""
    if link["root"] != member["root"]:
        return False
    drawer = _drawer(claimdir, link["component"])
    if drawer is None:
        return False
    try:
        dm = kernel.read_manifest(drawer)
    except kernel.ClaimError:
        return False
    return (dm.get("root") == member["root"]
            and (dm.get("components") or []) ==
                (member["manifest"].get("components") or []))


def collection(ws: str = ".") -> dict:
    """The sibling layout: a directory whose immediate subdirectories are
    sealed claims — the shape a layered campaign leaves on disk. Members are
    keyed by claim NAME (the manifest's, not the directory's), and each
    dependent's links are judged against the members as they stand:

        current     the link and the drawer copy agree with the sibling
        stale       the sibling has moved on (new root, or new links under
                    the same root) — a no-argument `ret pull` repairs this
        external    not a sibling; this claim's own drawer resolves it
        unresolved  not a sibling, and the drawer does not hold it either

    This is the pure view; `ret pull` with no claim named is the repair."""
    ws = os.path.abspath(ws)
    members: dict[str, dict] = {}
    for entry in sorted(os.listdir(ws)):
        d = os.path.join(ws, entry)
        if entry.startswith(".") or not os.path.isdir(d) or _phase(d) == "draft":
            continue
        m = kernel.read_manifest(d)
        if m["name"] in members:
            raise kernel.ClaimError(
                f"collection: two sibling claims are both named {m['name']!r}: "
                f"{os.path.basename(members[m['name']]['dir'])} and {entry}")
        members[m["name"]] = {"name": m["name"], "dir": d, "root": m["root"],
                              "phase": _phase(d), "proof": bool(m.get("proof")),
                              "links": [], "manifest": m}
    for mem in members.values():
        for link in mem["manifest"].get("components") or []:
            name = link["component"]
            if name in members:
                status = ("current" if _link_fresh(mem["dir"], link, members[name])
                          else "stale")
            else:
                drawer = _drawer(mem["dir"], name)
                try:
                    held = (drawer is not None and
                            kernel.read_manifest(drawer)["root"] == link["root"])
                except kernel.ClaimError:
                    held = False
                status = "external" if held else "unresolved"
            mem["links"].append({"component": name, "root": link["root"],
                                 "status": status})
    # dependency order, leaves first — the order is a property of the graph,
    # never of a script someone has to keep by hand
    order: list[str] = []
    done: set[str] = set()

    def visit(name: str, trail: tuple) -> None:
        if name in done:
            return
        if name in trail:
            cycle = trail[trail.index(name):] + (name,)
            raise kernel.ClaimError(
                "collection: the composition has a cycle: " + " -> ".join(cycle))
        for link in members[name]["links"]:
            if link["component"] in members:
                visit(link["component"], trail + (name,))
        done.add(name)
        order.append(name)

    for name in sorted(members):
        visit(name, ())
    rows = []
    for name in order:
        row = {k: v for k, v in members[name].items() if k != "manifest"}
        row["dir"] = os.path.relpath(row["dir"], ws).replace(os.sep, "/")
        rows.append(row)
    return {"workspace": ws, "members": rows,
            "stale": sum(1 for r in rows for x in r["links"]
                         if x["status"] == "stale"),
            "unresolved": sum(1 for r in rows for x in r["links"]
                              if x["status"] == "unresolved")}


def _root_covered(claimdir: str) -> set[str]:
    """Paths inside this claim's root: declared inputs (listed, or via the
    inputs manifest), the environment lock, and every non-generated step
    output. Recompose consults this before touching anything — a refresh
    may only write OUTSIDE it. Over-approximation is the safe direction:
    the caller refuses on overlap, and the post-reseal root comparison is
    the backstop either way."""
    recipe = kernel.load_recipe(claimdir)
    claim = recipe.get("claim") or {}
    covered = set(declared_inputs(recipe))
    manifest_file = claim.get("inputs_manifest")
    if manifest_file:
        covered.add(manifest_file)
        try:
            with open(os.path.join(claimdir, manifest_file),
                      encoding="utf-8") as f:
                for line in f:
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        covered.add(parts[1].strip())
        except OSError:
            pass
    if claim.get("environment"):
        covered.add(claim["environment"])
    for step in recipe.get("step", []):
        if step.get("output") and step.get("class") not in ("generated", "free"):
            covered.add(step["output"])
    return covered


def recompose(ws: str = ".") -> dict:
    """`ret pull` with no claim named: re-walk every wire in the collection.

    pack moves roots, deliberately, one claim at a time; recompose never
    moves one — it restores the composition's bookkeeping to agree with
    roots that already moved. Bottom-up over the sibling claims, each
    dependent whose view of a component went stale gets the component
    re-pulled into its drawer and is resealed warm (pack_declared: the
    gates re-earn, so nothing false rides in). Component-supplied files
    are generated — outside the dependent's root — so a refresh is
    root-preserving; the one exception, a dependent that PINS a supplied
    file, is refused by a pre-check and left for a deliberate `ret pack`.

    Staleness is judged live at each member's turn, not from a snapshot:
    refreshing one layer is exactly what makes the next layer's frozen
    drawer copy stale. A gate that rejects the refreshed bytes stops the
    walk there — the composition genuinely broke, and the first refusing
    layer names where; the failed dependent's identity is untouched (only
    generated bytes and drawer residue moved), with the refusal on record.
    Recorded proofs on refreshed claims keep their roots but predate the
    new component bytes; the report says so rather than re-earning them."""
    from . import pack as pack_mod  # pack imports registry lazily; mirror it
    col = collection(ws)
    ws = col["workspace"]
    if not col["members"]:
        raise kernel.ClaimError(
            f"pull: no sealed claims under {ws} — name a claim to pull it, "
            "or run this in the directory that holds the composition")
    by_name = {m["name"]: m for m in col["members"]}
    results: list[dict] = []
    proofs_predate: list[str] = []
    ok = True
    for mem in col["members"]:                      # already leaves-first
        claimdir = os.path.join(ws, mem["dir"])
        manifest = kernel.read_manifest(claimdir)   # live, not the snapshot
        stale: list[str] = []
        for link in manifest.get("components") or []:
            name = link["component"]
            if name not in by_name:
                continue
            cm = kernel.read_manifest(os.path.join(ws, by_name[name]["dir"]))
            comp_now = {"root": cm["root"], "manifest": cm}
            if (name not in stale
                    and not _link_fresh(claimdir, link, comp_now)):
                stale.append(name)
        row = {"name": mem["name"], "dir": mem["dir"], "root": mem["root"],
               "refreshed": stale,
               "unresolved": [x["component"] for x in mem["links"]
                              if x["status"] == "unresolved"]}
        if not stale:
            row["action"] = "held"
            results.append(row)
            continue
        # pre-check: a refresh may only write outside this claim's root
        covered = _root_covered(claimdir)
        blocked = None
        for name in stale:
            comp_dir = os.path.join(ws, by_name[name]["dir"])
            for step in kernel.load_recipe(comp_dir).get("step", []):
                out = step.get("output")
                if not out or out not in covered:
                    continue
                src = os.path.join(comp_dir, out)
                dst = os.path.join(claimdir, out)
                if os.path.isfile(src) and not (
                        os.path.isfile(dst)
                        and _hash_file(src) == _hash_file(dst)):
                    blocked = (out, name)
                    break
            if blocked:
                break
        if blocked:
            out, name = blocked
            row["action"] = "refused"
            row["reason"] = (f"{out} is inside this claim's root and {name} "
                             f"now supplies different bytes — refreshing would "
                             f"move the root; update it deliberately: "
                             f"ret pack {mem['dir']}")
            results.append(row)
            continue
        for name in stale:
            for store in STORES:
                shutil.rmtree(os.path.join(claimdir, kernel.STORE, store, name),
                              ignore_errors=True)
            # the pulls replace same-named files in place; `copy_into`
            # invalidates the bytecode cache beside each one, or a gate
            # importing the module would judge the bytes that used to be
            # there (this verb's own test is where that was found)
            pull(os.path.join(ws, by_name[name]["dir"]), claimdir)
        try:
            sealed = pack_mod.pack_declared(claimdir)
        except kernel.ClaimError as e:
            row["action"] = "failed"
            row["reason"] = str(e)
            results.append(row)
            ok = False
            break
        row["new_root"] = sealed["root"]
        if sealed["root"] != mem["root"]:
            # past the pre-check this should be impossible; if it happens
            # anyway, say so and stop — moved roots are pack's territory
            row["action"] = "moved"
            results.append(row)
            ok = False
            break
        row["action"] = "refreshed"
        if mem["proof"]:
            proofs_predate.append(mem["name"])
        results.append(row)
    return {"workspace": ws, "claims": results, "ok": ok,
            "held": sum(r["action"] == "held" for r in results),
            "refreshed_count": sum(r["action"] == "refreshed" for r in results),
            "proofs_predate": proofs_predate}


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


def rebuild_chain(claim: str, producer: str, into: str, ws: str | None = None,
                  producer_env=None, reuse: bool = False, guidance: bool = True) -> dict:
    """DAG-aware rebuild: regenerate a claim, threading its component
    dependencies up as inputs. Two modes:

    - regenerate (`reuse=False`, the `--recursive` path): each component is
      itself rebuilt from its own recipe, bottom-up, so the whole chain
      reproduces from the leaves. The full-trust redo.
    - reuse (`reuse=True`, the incremental path): each component is taken from
      its already-sealed bytes and threaded up unchanged; only *this* layer is
      regrown. This is the layered build for large software — seal the kernel
      once, then build on it without paying to reproduce it every time. The
      producer is never asked for a layer already sealed.
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
            if reuse:
                # incremental build: trust the sealed component as it stands and
                # regrow only this layer. Its bytes are threaded up unchanged and
                # the producer is never asked to reproduce a sealed layer.
                built = os.path.join(staging, name)
                copy_claim(comp, built)
                sub = {"root": root}
                moves.append((built, home))
            elif (_phase(home) != "draft"
                    and kernel.read_manifest(home)["root"] == root):
                built, sub = home, {"root": root}
            else:
                built = os.path.join(staging, name)
                sub = rebuild_chain(comp, producer, built, ws,   # recurse: leaf first
                                    reuse=reuse, guidance=guidance,
                                    producer_env=producer_env)
                moves.append((built, home))
            rebuilt.append({"component": name, "root": sub["root"]})
            for link in links:
                src = os.path.join(built, link["output"])
                # a link into a pinned input is data; into a produce step it is
                # generated code
                (input_from if link["input"] in inputs
                 else produce_from)[link["input"]] = src

        result = kernel.rebuild(claim, producer, into, produce_from=produce_from,
                                input_from=input_from, guidance=guidance,
                                producer_env=producer_env)
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


def _layers(claim: str, ws: str | None = None,
            strict: bool = False, auditor=None) -> tuple[list[dict], bool]:
    """Re-earn every component's verdict against the bytes THIS claim ships.

    Each component in the chain runs ITS OWN gates over the dependent's
    generated bytes: the component's recipe and inputs (its claim) in a fresh
    workspace, the dependent's generated bytes standing in for the component's
    produce outputs, the pinned verdict required to reproduce the component's
    sealed bytes. A layer whose claim cannot be found is a failed layer — an
    unresolvable component is not an audited one.

    `auditor` is how a component is re-earned, `kernel.audit` by default.  A
    caller from above the kernel may inject a reuse-aware auditor (one that
    skips a component already earned on this machine and reports it `reused`
    rather than `earned`); this layer stays reuse-agnostic so the exchange
    layer never reaches up to the measure layer that owns the cache.
    """
    run = auditor or kernel.audit
    claim = os.path.abspath(claim)
    # The DATA half of a component link: a pinned INPUT attributed to a
    # component (detect_components' shape — no produce step carries it) is
    # content-matched at seal time and must be RE-EARNED here, or a forged
    # input rides the manifest's attribution through every verb (measured
    # 2026-10-09: verify, audit, audit_deep, and the deps view all endorsed
    # it, and sign_root folds the attribution into signed identity). The
    # code half below (produce_from injection) has been pinned since the
    # transitivity fixture; this is its mirror.
    own_recipe = kernel.load_recipe(claim)
    produced = {step_output(s) for s in own_recipe.get("step", [])
                if s["kind"] == "produce"}
    data_links: dict[str, list] = {}
    for link in (kernel.read_manifest(claim).get("components") or []):
        if link.get("input") and link["input"] not in produced:
            data_links.setdefault(link["root"], []).append(link)
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
            a = run(c["path"], produce_from=supplied, strict=strict)
            # the v2 kernel's audit reports no name of its own, so the layer
            # names the layer from the component link it walked
            reused = a.get("reused")
            layer = {"name": c["name"], "root": c["root"], "ok": a["ok"],
                    "status": ("reused" if reused else "earned") if a["ok"] else
                    ("environment" if a["environment"] else "carried or broken"),
                    "gates": a["gates"], "environment": a["environment"],
                    "bytes_from": sorted(supplied)}
            if reused:
                layer["reused"] = reused
        except kernel.ClaimError as e:
            layer = {"name": c["name"], "root": c["root"], "ok": False,
                    "status": f"refused: {e}", "gates": [], "environment": []}
        for link in data_links.get(c["root"], ()):
            shipped = os.path.join(claim, link["input"])
            earned = os.path.join(c["path"], link["output"])
            if not (os.path.isfile(shipped) and os.path.isfile(earned)
                    and _hash_file(shipped) == _hash_file(earned)):
                layer["ok"] = False
                layer["status"] = f"attribution broken: {link['input']}"
        layers.append(layer)
        ok = ok and layer["ok"]
    return layers, ok


def audit_deep(claim: str, ws: str | None = None, progress=None,
               strict: bool = False, auditor=None) -> dict:
    """Composed audit — gates compose, verdicts never carry. This claim's own
    gates run first (kernel.audit); then every component in the chain re-earns
    its verdict on the bytes this claim ships (`_layers`). The result keeps
    kernel.audit's shape and adds `layers`.

    `auditor` re-earns each component (`kernel.audit` by default); a caller
    may inject a reuse-aware one so a composed audit pays only for the layers
    that changed. The top claim's own gates always run cold here — only the
    components consult the injected auditor."""
    claim = os.path.abspath(claim)
    top = kernel.audit(claim, progress=progress, strict=strict)
    layers, layers_ok = _layers(claim, ws, strict=strict, auditor=auditor)
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
    """Run the deep crosscheck and, on a pass, seal the proof onto M1 as residue.

    The proof carries what the kernel's own `record_proof` carries, because a
    composed claim's evidence is not a lesser kind: the root it covers, the
    build digests of the two other legs, and WHICH ORACLE the redo used. This
    layer owns `proof` as manifest residue (see `seal_with`) and so writes the
    dict itself rather than calling the kernel's recorder, which would re-run
    all three legs; the shape follows the kernel's deliberately.

    Before this, the deep path wrote `{kind, m2, m3}` with ROOTS in the digest
    fields and no producer at all -- so every proof the first campaign
    recorded (ten composed claims, all of them) stated neither what it
    compared nor whose search it survived. Readers of those older proofs still
    work: `views._proof_current` matches the claim's root against any of
    `root`, `m2`, `m3`, and in a passing crosscheck all three legs share it.
    """
    result = crosscheck_deep(m1, m2, m3, **kw)
    result["proof_recorded"] = False
    if result["satisfied"]:
        seal_proof(m1, [result])
        result["proof_recorded"] = True
    return result


#: How a producer's model was learned, strongest first. `observed` was read
#: back from the producer's own record of what it ran; `requested` is the name
#: we passed and the producer could have substituted; `declared` came from the
#: caller's environment; `unrecorded` is silence.
_PROVENANCE = ("observed", "requested", "declared", "unrecorded")


def _provenance_rank(declaration) -> int:
    source = (declaration or {}).get("model_source") or "unrecorded"
    return _PROVENANCE.index(source) if source in _PROVENANCE else len(_PROVENANCE)


def strongest_declaration(declarations):
    """The declaration a reader should trust most, by HOW its model is known.

    Not the first and not the last. `producer` used to be whichever rebuild
    happened to be listed last, so the same four realizations recorded
    different provenance depending on argument order -- a positional accident
    that silently decided whether the proof said `observed` or `requested`.
    Ranking by provenance makes the field deterministic and always picks the
    better-evidenced of the available answers.
    """
    known = [d for d in declarations if d]
    if not known:
        return None
    return min(known, key=_provenance_rank)


def seal_proof(m1: str, results) -> dict:
    """Write ONE proof covering EVERY independent rebuild that was tested.

    A crosscheck over several rebuilds tests each of them, and before this
    each one sealed its own proof over the last -- so a claim reconstructed
    by two independent producer families could only say so about one of them.
    That is precisely the claim a cross-family rebuild is run to establish:
    it is the control for whether an agreement comes from the boundary or
    from a prior the producers happen to share. The verdict knew; the record
    did not.

    `producers` and `rebuilds` carry every leg. `producer` and `m3` remain as
    the single-rebuild shape readers already parse, with `producer` now
    chosen by provenance rather than by position.
    """
    first = results[0]
    declarations = [r.get("producer") or {} for r in results]
    rebuilds = [{"digest": r["digests"]["M3"] or "",
                 "producer": r.get("producer"),
                 "independence": r["independence"]} for r in results]
    proof = {"kind": "crosscheck",
             "root": first["roots"]["M1"],
             "m2": first["digests"]["M2"] or "",
             "m3": first["digests"]["M3"] or "",
             "independence": first["independence"],
             "producer": strongest_declaration(declarations),
             "producers": declarations,
             "rebuilds": rebuilds,
             "recorded": now(),
             "layers": sorted(c["name"] for c in chain(m1))}
    seal_with(m1, proof=proof,
              components=kernel.read_manifest(m1).get("components") or None)
    return proof


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
