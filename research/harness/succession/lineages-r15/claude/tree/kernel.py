"""The kernel's public surface (v2 names, `spec/kernel-api.md`).

Identity, sealing, verification, rebuilding, auditing, signing, and the
three-machine test -- assembled from the `_kernel` layer's modules. Most
symbols here delegate directly to a `_kernel` module; a few (`rebuild`,
`audit`'s shape, `phase`, `sign_node`, `record_proof`, `sandbox`, `cost`)
are composed here because no single lower module owns the whole pinned
contract.

Stdlib only; this module never touches the network.
"""
import hashlib
import json
import os
import shutil
import stat
import time
import tomllib

from ._kernel import attest as _attest
from ._kernel import build as _build
from ._kernel import core as _core
from ._kernel import crosscheck as _cc
from ._kernel import identity as _identity
from ._kernel import recipe as _recipe
from ._kernel import run as _run
from ._kernel import seal as _seal
from ._kernel.core import ClaimError

# -- Constants (`spec/kernel-api.md`) -------------------------------------

NAMESPACE = _core.NAMESPACE
DIGEST = _core.DIGEST
FORMAT = _core.FORMAT
STORE = _core.STORE
MANIFEST = _core.MANIFEST
RECIPE = _core.RECIPE
LEGACY_RECIPE = _core.LEGACY_RECIPE
LEDGER = _core.LEDGER
SIGN_DIR = _core.SIGN_DIR
SIGN_NAMESPACE = _core.SIGN_NAMESPACE
_JAILED = _core._JAILED

RECORD_NAMESPACE = _attest.RECORD_NAMESPACE
RECORD_FORMAT = _attest.RECORD_FORMAT


def _reraise_claim_error(fn):
    """A hostile or missing file must refuse as `ClaimError`, never leak a
    raw `OSError`/parse exception past this surface.
    """
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ClaimError:
            raise
        except (OSError, ValueError) as e:
            raise ClaimError(str(e)) from e
    return wrapped


# -- Direct delegations ----------------------------------------------------

def _validate_envelope(envelope) -> None:
    if not isinstance(envelope, dict) or not envelope:
        raise ClaimError("[claim] envelope must be a non-empty table")
    for unit, ceiling in envelope.items():
        if unit not in _core.COST_UNITS:
            raise ClaimError(f"[claim] envelope has an unknown unit {unit!r}")
        if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
            raise ClaimError(f"[claim] envelope.{unit} must be a positive number")


def _validate(d: str, doc) -> None:
    """`recipe._validate`, with one change this kernel needs: a GENERATED
    output's path escape/symlink safety is deferred to the point its bytes
    are actually touched (materialize/audit), not checked at parse time --
    a generated output is never hashed, so its path need not even resolve
    for the claim to seal (`spec/claim-format.md`'s confinement note).
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("claim"), dict):
        raise ClaimError("a recipe needs a [claim] table")
    claim = doc["claim"]

    name = claim.get("name")
    if not isinstance(name, str) or isinstance(name, bool):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")
    if fmt > _core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {_core.FORMAT}); upgrade reticuli to read it")

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ClaimError("[claim] inputs must be a list of strings")
    for p in inputs:
        _core._safe(d, p)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        _core._safe(d, manifest)

    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str):
            raise ClaimError("[claim] environment must be a string")
        _core._safe(d, environment)

    if "envelope" in claim:
        _validate_envelope(claim["envelope"])

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("each step must be a table")
        kind = step.get("kind")
        if kind not in _core.KINDS:
            raise ClaimError(f"step kind must be one of {sorted(_core.KINDS)}, got {kind!r}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"a {kind!r} step needs a string output")
        generated = kind == "produce" and step.get("class", "generated") in ("generated", "free")
        if not generated:
            _core._safe(d, output)
        if kind == "gate":
            run_cmd = step.get("run")
            if not isinstance(run_cmd, str) or not run_cmd:
                raise ClaimError("a gate step needs a string 'run' command")


@_reraise_claim_error
def load_recipe(d: str) -> dict:
    """Parse and validate the recipe in claim directory `d`
    (`spec/claim-format.md`)."""
    path = _recipe.recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    try:
        _validate(d, doc)
    except ClaimError:
        raise
    except Exception as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    return doc


read_manifest = _reraise_claim_error(_seal.read_manifest)
build_digest = _reraise_claim_error(_identity.build_digest)


root = _reraise_claim_error(_cc.root)


@_reraise_claim_error
def seal(d: str) -> dict:
    """Freeze claim directory `d`: compute the root, write the manifest
    (`spec/claim-format.md`)."""
    doc = load_recipe(d)
    name = doc["claim"]["name"]
    parts = _cc._parts(doc, d)
    r = root(doc, d)
    manifest = {"name": name, "root": r, "parts": parts}
    os.makedirs(os.path.join(d, _core.STORE), exist_ok=True)
    _core._write_json(os.path.join(d, _core.MANIFEST), manifest)
    return manifest


@_reraise_claim_error
def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare it with the
    sealed manifest -- identity only, no gate is executed
    (`spec/verification.md`). A claim whose identity cannot even be
    recomputed (an escaping/missing input, a corrupt recipe) refuses with
    a reason; a claim that recomputes cleanly but to a DIFFERENT root
    reports `ok: False` -- that is the ordinary, nameable fact a sealed
    claim can drift to, not a refusal.
    """
    manifest = read_manifest(d)
    doc = load_recipe(d)
    recomputed = root(doc, d)
    ok = recomputed == manifest["root"]
    result = {"ok": ok, "name": manifest["name"], "root": manifest["root"],
              "recomputed": recomputed}
    if not ok:
        try:
            result["changed"] = _seal._changed_parts(d)
        except ClaimError:
            pass
    return result


preflight = _run.preflight
ledger = _run.ledger
ledger_events = _run.ledger_events

record_canonical = _attest.record_canonical
record_digest = _attest.record_digest
record_validate = _attest.record_validate
@_reraise_claim_error
def record_read(path: str) -> dict:
    """Parse and validate the record at `path` (`spec/record.md`): the
    file must be exactly its own canonical bytes, or it is not a record --
    a reformatted (pretty-printed, re-keyed) file is refused even if its
    parsed content would otherwise validate.
    """
    doc = _attest.record_read(path)
    with open(path, "rb") as f:
        raw = f.read()
    if raw != _attest.record_canonical(doc):
        raise ClaimError(f"record {path!r} is not its own canonical bytes")
    return doc
record_signer = _attest.record_signer

run_gate = _cc.run_gate
cost = _cc.cost
independence = _cc.independence
audit = _reraise_claim_error(_cc.audit)
vacuous_gates = _cc.vacuous_gates
gate_deciders = _cc.gate_deciders
mutation_score = _reraise_claim_error(_cc.mutation_score)
crosscheck = _reraise_claim_error(_cc.crosscheck)

_hash_file = _core._hash_file


# -- sandbox: a functional probe expressed as "run this and tell me the
# jail", so a caller can learn the backend without a throwaway claim. ----


def sandbox(cmd: str, workspace: str):
    """Run `cmd` in `workspace` under whatever confinement this host
    offers; returns `(status, quarantine)`.
    """
    result = run_gate(cmd, workspace)
    return (result["status"], result["quarantine"])


# -- rebuild: regrow the generated outputs, then re-earn the gates. ------


def rebuild(d: str, producer: str, into: str, produce_from=None, input_from=None,
            guidance: bool = True, producer_env=None, vendor=None, model=None) -> dict:
    """Regrow claim `d`'s generated outputs into fresh directory `into` by
    driving `producer` there, then re-run the gates until they pass; a
    ledger entry is appended and `into` is sealed (`spec/kernel-api.md`).
    """
    doc = load_recipe(d)

    if os.path.exists(into) and os.listdir(into):
        raise ClaimError(f"rebuild target is not empty: {into!r}")
    os.makedirs(into, exist_ok=True)

    missing = _run.preflight(doc)
    if missing:
        raise ClaimError(f"environment failure: missing requirements {missing}")
    venv_bin = _cc.furnish(doc, d)

    _build._materialize(doc, d, into, include_generated=False)

    if input_from:
        for rel, src_path in input_from.items():
            target = _core._safe(into, rel)
            os.makedirs(os.path.dirname(target) or into, exist_ok=True)
            if os.path.isdir(src_path):
                shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(src_path, target)
            else:
                shutil.copy2(src_path, target)

    generated = _recipe.generated_outputs(doc)
    supplied = set()
    if produce_from:
        for rel, src_path in produce_from.items():
            target = _core._safe(into, rel)
            os.makedirs(os.path.dirname(target) or into, exist_ok=True)
            shutil.copy2(src_path, target)
            supplied.add(rel)
            _run.ledger(into, {"event": "reuse", "output": rel})

    guarded = [_core.RECIPE if os.path.isfile(_core._safe(into, _core.RECIPE))
               else _core.LEGACY_RECIPE]
    guarded += _recipe._inputs(into, doc)
    before = {p: _core._hash_file(_core._safe(into, p)) for p in guarded
              if os.path.isfile(_core._safe(into, p))}

    outputs = [o for o in generated if o not in supplied]
    started = time.time()
    prod = _build._produce(doc, into, producer, outputs,
                           guidance=guidance, producer_env=producer_env)
    elapsed = time.time() - started
    if prod["returncode"] != 0:
        raise ClaimError(
            f"producer failed (exit {prod['returncode']}): {prod['stderr'][-500:]}")

    after = {p: _core._hash_file(_core._safe(into, p)) for p in before
             if os.path.isfile(_core._safe(into, p))}
    if before != after or set(before) != set(after):
        raise ClaimError("the producer rewrote a pinned input or the recipe")

    backend = "none"
    for step in _recipe.gates(doc):
        gate = run_gate(step["run"], into, doc, venv_bin=venv_bin)
        backend = gate["quarantine"]
        _run.ledger(into, {"event": "gate", "output": step["output"],
                           "status": gate["status"], "quarantine": backend})
        if gate["status"] != "ok":
            raise ClaimError(
                f"gate {step['output']!r} did not pass during rebuild: {gate['status']}")

    usage = _build._read_usage(prod.get("usage_path"))
    entry = {"kind": "producer", "seconds": elapsed, "calls": usage.get("calls", 1)}
    for key in ("usd", "tokens"):
        if key in usage:
            entry[key] = usage[key]
    if vendor is None:
        vendor = os.environ.get(_core._ENV_VENDOR)
    if model is None:
        model = os.environ.get(_core._ENV_MODEL)
    if vendor is not None:
        entry["vendor"] = vendor
    if model is not None:
        entry["model"] = model
    _run.ledger(into, entry)

    probe = _run.sandbox()
    _run.ledger(into, {"event": "environment", "python": probe["runtime"],
                       "platform": probe["platform"], "quarantine": probe["backend"]})

    seal(into)
    return {"root": root(doc, into), "quarantine": backend}


# -- sign_node: the bottom-anchored signature-chain fold. -----------------


def sign_node(node_root: str, digest: str, links) -> str:
    """Fold a layer's root, its build digest, and the (unordered) set of
    signatures beneath it into one node value.
    """
    payload = {"root": node_root, "digest": digest, "links": sorted(links)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# -- phase: draft / sealed / signed. --------------------------------------


def _signed(d: str, manifest: dict) -> bool:
    anchor = os.environ.get(_core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):
        return False
    sign_dir = os.path.join(d, _core.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return False
    proof = manifest.get("proof")
    if not proof:
        return False
    try:
        current_root = root(load_recipe(d), d)
        current_bd = build_digest(d)
    except ClaimError:
        return False

    for name in sorted(os.listdir(sign_dir)):
        if not name.endswith(".sign.json"):
            continue
        spath = os.path.join(sign_dir, name)
        sig_path = spath + ".sig"
        if not os.path.isfile(sig_path):
            continue
        try:
            with open(spath, "r", encoding="utf-8") as f:
                statement = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        identity_name = statement.get("identity")
        if not identity_name:
            continue
        with open(spath, "rb") as f:
            data = f.read()
        if not _build._ssh_verify(anchor, identity_name, _core.SIGN_NAMESPACE,
                                   sig_path, data):
            continue
        if not _build._authorized(identity_name, anchor):
            continue

        packet_name = name[: -len(".sign.json")] + ".packet.json"
        ppath = os.path.join(sign_dir, packet_name)
        if not os.path.isfile(ppath):
            continue
        try:
            with open(ppath, "r", encoding="utf-8") as f:
                packet = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        pdig = hashlib.sha256(json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()
        if pdig != statement.get("packet_digest"):
            continue
        if packet.get("root") != current_root or packet.get("build_digest") != current_bd:
            continue
        if not packet.get("proof"):
            continue
        return True
    return False


def phase(d: str) -> str:
    """`draft` (no manifest yet), `sealed` (root computed), or `signed`
    (a trusted signature over a coherent, proof-bearing packet on
    undrifted bytes) (`spec/verification.md`).
    """
    if not os.path.isfile(os.path.join(d, _core.MANIFEST)):
        return "draft"
    v = verify(d)
    if not v["ok"]:
        raise ClaimError(f"claim does not verify: {v.get('reason', 'root mismatch')}")
    manifest = read_manifest(d)
    return "signed" if _signed(d, manifest) else "sealed"


# -- record_proof: run the crosscheck, and on a pass, seal the proof onto
# M1 as residue. Record legs must verify against the caller's anchor. ----


def record_proof(m1: str, m2: str, m3: str) -> dict:
    """Run the three-machine test; on a pass, record the proof onto M1's
    manifest as residue. M1 must be a directory. A record leg must verify
    against `RETICULI_SIGNERS`, or the proof refuses outright.
    """
    if not os.path.isdir(m1):
        raise ClaimError("a recorded proof can only land on a claim directory")

    anchor = os.environ.get(_core._ENV_SIGNERS)
    records = []
    for leg in (m2, m3):
        if os.path.isdir(leg):
            continue
        doc = record_read(leg)
        signer = record_signer(leg, anchor) if anchor else None
        if not signer:
            raise ClaimError(f"record leg {leg!r} does not verify against the anchor")
        records.append({"digest": record_digest(doc), "signer": signer})

    result = crosscheck(m1, m2, m3)
    if not result["satisfied"]:
        return {"proof_recorded": False, "crosscheck": result}

    manifest = read_manifest(m1)
    proof = {"kind": "crosscheck", "verdict": result["verdict"], "roots": result["roots"]}
    if records:
        proof["records"] = records
    manifest["proof"] = proof
    _core._write_json(os.path.join(m1, _core.MANIFEST), manifest)
    return {"proof_recorded": True, "crosscheck": result}
