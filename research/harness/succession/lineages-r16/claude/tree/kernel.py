"""The kernel: the assembled public surface over `reticuli._kernel`.

Every name here is a thin re-export of a `_kernel` primitive, except where
the primitive's own module cannot see what the surface needs without
creating an import cycle, or where the behavior is a composition this
module alone owns:

- `load_recipe` adds the `[claim] envelope` shape check (a positive number
  per declared unit) that `_kernel.recipe` -- read by every layer, not just
  the public surface -- does not carry.
- `rebuild` resolves `into` to an absolute path (so a producer's reported
  usage path, and the room a caller is handed, never depend on the
  caller's cwd), snapshots pinned bytes and the recipe immediately before
  and after the producer runs (a producer may regrow the generated outputs;
  it may not rewrite the question), and ledgers the gate/environment/
  producer residue `spec/verification.md` promises beyond the producer's
  own cost report.
- `phase` is the draft/sealed/signed lifecycle: a trusted signature
  (`RETICULI_SIGNERS`), over a stored packet whose bytes still hash to the
  digest the signature covers, naming the root and build digest present
  right now, coupled to a recorded proof.
- `sign_node`, `record_proof`, `independence`, `sandbox` compose primitives
  from more than one `_kernel` module.

`audit`, `crosscheck`, `mutation_score`, `gate_deciders`, and `vacuous_gates`
live in `_kernel.crosscheck` (they need each other, and `crosscheck` needs
`audit`); this module only re-exports them.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

from ._kernel import attest as _attest
from ._kernel import build as _build
from ._kernel import core as _core
from ._kernel import crosscheck as _crosscheck
from ._kernel import identity as _identity
from ._kernel import recipe as _recipe
from ._kernel import run as _run
from ._kernel import seal as _seal

# ------------------------------------------------------------------ errors
ClaimError = _core.ClaimError

# --------------------------------------------------------------- constants
NAMESPACE = _core.NAMESPACE
DIGEST = _core.DIGEST
FORMAT = _core.FORMAT
STORE = _core.STORE
MANIFEST = _core.MANIFEST
RECIPE = _core.RECIPE
LEGACY_RECIPE = _core.LEGACY_RECIPE
LEDGER = _core.LEDGER
USAGE = _core.USAGE
MUTATION_RESIDUE = _core.MUTATION_RESIDUE
SIGN_DIR = _core.SIGN_DIR
SIGN_NAMESPACE = _core.SIGN_NAMESPACE
_JAILED = _core._JAILED

RECORD_NAMESPACE = _attest.RECORD_NAMESPACE
RECORD_FORMAT = 2

# ------------------------------------------------------------ pure re-exports
root = _identity.root
build_digest = _identity.build_digest
seal = _seal.seal
preflight = _run.preflight
cost = _run.cost
ledger = _run.ledger
ledger_events = _run.ledger_events
_hash_file = _core._hash_file

gate_deciders = _crosscheck.gate_deciders
vacuous_gates = _crosscheck.vacuous_gates
mutation_score = _crosscheck.mutation_score
audit = _crosscheck.audit
crosscheck = _crosscheck.crosscheck

record_canonical = _attest.record_canonical
record_digest = _attest.record_digest
record_signer = _attest.record_signer


# -------------------------------------------------------------- record format
_RECORD_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})


def record_validate(doc) -> None:
    """Refuse, in band, any document that is not a well-formed record.

    A corrected `_kernel.attest.record_validate`: that primitive only
    understands format 1 and has no notion of the version-2 `claim`
    member at all (`spec/record.md`), so every version-2 record -- the
    transport a declared tolerance/envelope/mutation_floor needs to cross
    -- is refused outright as "newer than this kernel understands".
    Patched onto `_kernel.attest.record_validate` so `record_read` --
    which calls it by its own module-global name -- inherits the fix.
    """
    if not isinstance(doc, dict):
        raise ClaimError("a record must be a JSON object")

    version = doc.get("record")
    if version not in (1, 2):
        raise ClaimError(
            f"record format {version!r} is newer than this kernel understands "
            f"(format {RECORD_FORMAT}); upgrade reticuli to read it")

    members = set(doc)
    allowed = set(_attest._RECORD_MEMBERS)
    required = set(_attest._RECORD_REQUIRED)
    if version == 2:
        allowed.add("claim")
        required.add("claim")
    elif "claim" in members:
        raise ClaimError("record 'claim' is not valid at version 1")

    unknown = members - allowed
    if unknown:
        raise ClaimError(f"refused unknown record member(s): {sorted(unknown)!r}")
    missing = required - members
    if missing:
        raise ClaimError(f"record is missing required member(s): {sorted(missing)!r}")

    if not isinstance(doc.get("name"), str):
        raise ClaimError("record 'name' must be a string")

    for key in ("root", "build_digest"):
        value = doc.get(key)
        if not isinstance(value, str) or not _attest._RECORD_HEX.match(value):
            raise ClaimError(f"record {key!r} must be 64 lowercase hex characters")

    when = doc.get("when")
    if not isinstance(when, str) or not _attest._RECORD_WHEN.match(when):
        raise ClaimError("record 'when' must be 'YYYY-MM-DDTHH:MM:SSZ'")

    environment = doc.get("environment")
    if not isinstance(environment, dict) or set(environment) != _attest._RECORD_ENVIRONMENT:
        raise ClaimError("record 'environment' needs exactly platform/machine/runtime")
    for key in _attest._RECORD_ENVIRONMENT:
        if not isinstance(environment.get(key), str):
            raise ClaimError(f"record environment {key!r} must be a string")

    gates = doc.get("gates")
    if not isinstance(gates, list):
        raise ClaimError("record 'gates' must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != _attest._RECORD_GATE:
            raise ClaimError(f"malformed gate entry: {gate!r:.60}")
        if not isinstance(gate.get("output"), str):
            raise ClaimError("gate 'output' must be a string")
        if gate.get("status") not in _attest._RECORD_STATUSES:
            raise ClaimError(f"refused gate status: {gate.get('status')!r}")
        if gate.get("sandbox") not in _attest._RECORD_SANDBOXES:
            raise ClaimError(f"refused gate sandbox: {gate.get('sandbox')!r}")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("record 'tool' must be a string")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict):
            raise ClaimError("record 'cost' must be an object")
        for key, value in cost.items():
            if key not in _attest.COST_KEYS:
                raise ClaimError(f"refused cost key: {key!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ClaimError(f"record cost {key!r} must be a non-negative number")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict) or set(producer) - _attest._RECORD_PRODUCER:
            raise ClaimError("record 'producer' holds only vendor/model/blind/cutoff")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise ClaimError("record producer 'blind' must be a boolean")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise ClaimError(f"record producer {key!r} must be a string")

    if version == 2:
        claim = doc.get("claim")
        if not isinstance(claim, dict):
            raise ClaimError("record 'claim' must be an object")
        unknown_claim = set(claim) - _RECORD_CLAIM_KEYS
        if unknown_claim:
            raise ClaimError(f"refused unknown claim obligation(s): {sorted(unknown_claim)!r}")
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                v = claim[key]
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                    raise ClaimError(f"record claim {key!r} must be a non-negative number")
        if "envelope" in claim:
            env = claim["envelope"]
            if not isinstance(env, dict) or not env:
                raise ClaimError("record claim 'envelope' must be a non-empty object")
            for unit, ceiling in env.items():
                if unit not in _attest.COST_KEYS:
                    raise ClaimError(f"record claim envelope names an unknown unit: {unit!r}")
                if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                    raise ClaimError(f"record claim envelope {unit!r} must be a positive number")


_attest.record_validate = record_validate


def record_read(path: str) -> dict:
    """Parse and validate a record file; refusals, never a raw crash.

    A corrected `_kernel.attest.record_read`: that primitive parses the
    JSON and validates its shape but never checks that the file IS its
    canonical bytes (`spec/record.md`: "the file is its canonical bytes or
    it is not a record") -- so a merely reformatted (re-indented) record,
    whose signature no longer covers what is on disk, reads back as valid.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read record {path!r}: {e}") from e
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ClaimError(f"malformed record {path!r}: {e}") from e
    record_validate(doc)
    if raw != _attest.record_canonical(doc):
        raise ClaimError(f"record {path!r} is not its own canonical bytes")
    return doc


_attest.record_read = record_read


# ------------------------------------------------------------------ run_gate
def run_gate(cmd: str, d: str, recipe) -> dict:
    """Run one gate command in `d`: scrubbed env, sandboxed, bounded.

    A corrected `_kernel.run.run_gate`: that primitive applies a real
    sandbox by setting `RETICULI_JAILED=1`, but the execution contract
    (`checks/kernel_check.py`'s `_apply_battery`) requires the SENDING half
    to name the backend it applied, so a gate that is itself a claim
    runner can tell it must inherit rather than nest. Patched onto
    `_kernel.run.run_gate` below so every caller -- `rebuild`, and
    `_kernel.crosscheck`'s `audit`/`mutation_score` -- gets the fix.
    """
    backend = _run.sandbox_backend()
    timeout = _run.gate_timeout(recipe)
    env = _run._scrub_env()
    d_real = os.path.realpath(d)

    if backend in ("seatbelt", "bubblewrap"):
        run_store = os.path.join(d, STORE, "run")
        os.makedirs(run_store, exist_ok=True)
        scratch = tempfile.mkdtemp(dir=run_store)
        home = os.path.join(scratch, "home")
        tmp = os.path.join(scratch, "tmp")
        os.makedirs(home, exist_ok=True)
        os.makedirs(tmp, exist_ok=True)
        home_real = os.path.realpath(home)
        tmp_real = os.path.realpath(tmp)
        env["HOME"] = home_real
        env["TMPDIR"] = tmp_real
        env[_JAILED] = backend
        argv = _run._sandbox_argv(backend, cmd, d_real, home_real, tmp_real)
    else:
        argv = ["/bin/sh", "-c", cmd]

    result = _run._run(argv, d, env, timeout)
    return {"status": result["status"], "quarantine": backend,
            "returncode": result.get("returncode")}


_run.run_gate = run_gate


# --------------------------------------------------------------- read_manifest
def read_manifest(d: str) -> dict:
    """Read `d`'s manifest back: `{name, root}` (plus optional residue).

    A corrected `_kernel.seal.read_manifest`: that primitive catches a
    malformed-JSON manifest but not one that is not even valid UTF-8 --
    `json.load` lets a raw `UnicodeDecodeError` escape uncaught, so a
    hostile manifest crashes the caller instead of refusing in band
    (`spec/verification.md`: "a verifier facing a damaged claim refuses in
    band"). Patched onto `_kernel.seal.read_manifest` so `verify` and
    `phase` -- which call it by its own module-global name -- inherit the
    fix too.
    """
    path = os.path.join(d, MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except OSError as e:
        raise ClaimError(f"cannot read manifest {path!r}: {e}") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ClaimError(f"malformed manifest {path!r}: {e}") from e
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)):
        raise ClaimError(f"malformed manifest {path!r}: missing name/root")
    return manifest


_seal.read_manifest = read_manifest


# ------------------------------------------------------------- preflight fix
def _version_tuple(s) -> tuple:
    """A dotted version string as a tuple of ints -- correcting
    `_kernel.run._version_tuple`, which cannot parse a version string
    carrying a name prefix (`--version` output like `"Python 3.13.2"`):
    it only strips a non-digit TAIL, so a leading word makes the whole
    tuple empty and a present `requires` version is misreported as
    missing. This instead finds the first run of digits-and-dots anywhere
    in the string. Patched onto `_kernel.run._version_tuple` so
    `preflight` -- which calls it by its own module-global name --
    inherits the fix.
    """
    m = re.search(r"\d+(?:\.\d+)*", str(s))
    if not m:
        return ()
    return tuple(int(p) for p in m.group(0).split("."))


_run._version_tuple = _version_tuple


# -------------------------------------------------------------------- verify
def verify(d: str) -> dict:
    """Identity + the claim's name (`_kernel.seal.verify` carries only
    `ok`/`root`/`recomputed`; the name is needed wherever a caller wants to
    know WHAT verified, e.g. a record's `name` member)."""
    result = dict(_seal.verify(d))
    result["name"] = read_manifest(d)["name"]
    return result


# ------------------------------------------------------------- furnish fix
def furnish(recipe, d: str) -> dict:
    """Build (or reuse) a private venv for `[claim] environment`, if declared.

    A corrected `_kernel.run.furnish`: that primitive invokes `pip install
    -r <path>` with no `cwd`, so a requirements file naming a wheel by a
    RELATIVE path (`./probe-1.0-py3-none-any.whl`, as `spec/claim-format.md`
    describes) resolves against the caller's cwd rather than the lock
    file's own directory -- pip reports the wheel missing even though it
    sits right beside the lock file. This runs pip with `cwd` set to the
    lock file's directory.
    """
    claim = (recipe or {}).get("claim", {}) if recipe else {}
    req_file = claim.get("environment")
    if not req_file:
        return {"status": "ok", "bin": None}
    path = os.path.join(d, req_file)
    if not os.path.isfile(path):
        return {"status": "environment", "bin": None,
                "error": f"missing environment file {req_file!r}"}
    digest = _core._hash_file(path)
    cache = os.path.join(_run._env_cache_dir(),
                          f"{digest}-{sys.implementation.name}-{sys.platform}")
    bin_dir = os.path.join(cache, "bin")
    if os.path.isdir(bin_dir):
        return {"status": "ok", "bin": bin_dir}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    try:
        subprocess.run([sys.executable, "-m", "venv", cache], check=True,
                        timeout=_core.FURNISH_TIMEOUT, capture_output=True)
        pip = os.path.join(bin_dir, "pip")
        subprocess.run([pip, "install", "--require-hashes", "--only-binary=:all:",
                        "-r", path], check=True, timeout=_core.FURNISH_TIMEOUT,
                        capture_output=True, cwd=os.path.dirname(path))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        return {"status": "environment", "bin": None, "error": str(e)}
    return {"status": "ok", "bin": bin_dir}


_run.furnish = furnish


# --------------------------------------------------------------- load_recipe
def load_recipe(d: str) -> dict:
    """Parse and validate `d`'s recipe, including the envelope shape the
    lower layer does not check: a non-empty table, known units, each a
    positive number."""
    recipe = _recipe.load_recipe(d)
    claim = recipe.get("claim", {})
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("[claim] envelope must be a non-empty table")
        for unit, ceiling in envelope.items():
            if unit not in _core.COST_UNITS:
                raise ClaimError(f"[claim] envelope names an unknown unit: {unit!r}")
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                raise ClaimError(f"[claim] envelope {unit!r} must be a positive number")
    return recipe


# -------------------------------------------------------------------- sandbox
def sandbox(cmd: str, d: str):
    """A functional probe of the host sandbox: run `cmd` in `d` and report
    `(outcome, backend)` -- `sandbox(...)[1]` names the confinement that
    actually applied."""
    outcome = _run.run_gate(cmd, d, None)
    return (outcome, outcome["quarantine"])


# --------------------------------------------------------------- independence
def independence(d: str) -> dict:
    """The producer declared for `d`'s own redo (vendor/model/blind), from
    its own ledger -- never enforced, only ever reported."""
    info = _crosscheck._producer_declaration(d) or {}
    return {"vendor": info.get("vendor"), "model": info.get("model"),
            "blind": info.get("blind")}


# ------------------------------------------------------------------- rebuild
def _pinned_snapshot(recipe: dict, into: str) -> dict:
    """Every pinned byte a producer must not rewrite: the recipe file and
    the claim's declared inputs and already-`pinned`-class outputs."""
    snap = {}
    try:
        with open(_recipe.recipe_path(into), "rb") as f:
            snap["__recipe__"] = hashlib.sha256(f.read()).hexdigest()
    except (ClaimError, OSError):
        snap["__recipe__"] = None
    for path in _recipe._inputs(recipe, into):
        try:
            snap[("input", path)] = _core._hash_file(_core._safe(into, path))
        except ClaimError:
            snap[("input", path)] = None
    for step in _recipe._steps(recipe):
        if step["kind"] == "produce" and step.get("class", "generated") == "pinned":
            path = _core._safe(into, step["output"])
            if os.path.isfile(path):
                try:
                    snap[("pinned", step["output"])] = _core._hash_file(path)
                except ClaimError:
                    snap[("pinned", step["output"])] = None
    return snap


def rebuild(d: str, producer, into: str, *, produce_from: dict = None,
            input_from: dict = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    """Regrow `d`'s generated outputs into a fresh room at `into`, via
    `producer`, until every gate passes there; seal the room and ledger its
    cost, gate/environment residue, and any declared producer
    (`spec/verification.md`, `spec/kernel-api.md`).
    """
    into = os.path.abspath(into)
    recipe = load_recipe(d)
    missing = _run.preflight(recipe)
    if missing:
        raise ClaimError(f"environment: missing requirements on this host: {missing!r}")

    _build._materialize(recipe, d, into, include_generated=False, input_from=input_from)

    for output, source in (produce_from or {}).items():
        _core._copy_into(source, _core._safe(into, output))
        _run.ledger(into, {"event": "reuse", "output": output})

    before = _pinned_snapshot(recipe, into)

    usage = {}
    if producer is not None:
        usage = _build._produce(recipe, into, producer, guidance=guidance,
                                 producer_env=producer_env)

    after = _pinned_snapshot(recipe, into)
    if before != after:
        raise ClaimError("a producer must not rewrite pinned bytes or the recipe")

    results = []
    for step in _recipe.gates(recipe):
        output = step["output"]
        outcome = _run.run_gate(step["run"], into, recipe)
        status = "ok" if outcome["status"] == "ok" else outcome["status"]
        results.append({"output": output, "status": status,
                         "quarantine": outcome["quarantine"]})
        _run.ledger(into, {"event": "gate", "output": output,
                            "status": status, "quarantine": outcome["quarantine"]})

    if not all(g["status"] == "ok" for g in results):
        raise ClaimError(f"rebuild did not earn its gates: {results!r}")

    manifest = _seal.seal(into)

    if producer is not None:
        entry = dict(usage)
        entry.setdefault("event", "oracle")
        if "calls" not in entry:
            entry["calls"] = 1
        _run.ledger(into, entry)

    backend = results[0]["quarantine"] if results else _run.sandbox_backend()
    _run.ledger(into, {
        "event": "environment",
        "python": f"{sys.implementation.name} {sys.version.split()[0]}",
        "platform": sys.platform,
        "quarantine": backend,
    })

    vendor = os.environ.get(_core._ENV_VENDOR)
    model = os.environ.get(_core._ENV_MODEL)
    if vendor or model:
        decl = {"event": "producer", "blind": True}
        if vendor:
            decl["vendor"] = vendor
        if model:
            decl["model"] = model
        _run.ledger(into, decl)

    return {
        "root": manifest["root"],
        "name": manifest["name"],
        "build_digest": _identity.build_digest(into),
        "gates": results,
        "quarantine": backend,
    }


# --------------------------------------------------------------------- phase
def _is_signed(d: str) -> bool:
    signers_path = os.environ.get(_core._ENV_SIGNERS)
    if not signers_path or not os.path.isfile(signers_path):
        return False
    manifest = read_manifest(d)
    if not manifest.get("proof"):
        return False
    live_root = manifest["root"]
    try:
        live_digest = build_digest(d)
    except ClaimError:
        return False
    sign_dir = os.path.join(d, SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return False
    for fname in sorted(os.listdir(sign_dir)):
        if not fname.endswith(".sign.json"):
            continue
        stmt_path = os.path.join(sign_dir, fname)
        sig_path = stmt_path + ".sig"
        if not os.path.isfile(sig_path):
            continue
        try:
            with open(stmt_path, "rb") as f:
                raw = f.read()
            stmt = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue
        identity_name = stmt.get("identity")
        packet_digest = stmt.get("packet_digest")
        if not isinstance(identity_name, str) or not isinstance(packet_digest, str):
            continue
        with open(sig_path, "rb") as f:
            signature = f.read()
        if not _build._ssh_verify(signers_path, identity_name, SIGN_NAMESPACE, raw, signature):
            continue
        base = fname[: -len(".sign.json")]
        packet_path = os.path.join(sign_dir, base + ".packet.json")
        if not os.path.isfile(packet_path):
            continue
        with open(packet_path, "rb") as f:
            packet_bytes = f.read()
        if hashlib.sha256(packet_bytes).hexdigest() != packet_digest:
            continue
        try:
            packet = json.loads(packet_bytes)
        except json.JSONDecodeError:
            continue
        if packet.get("root") != live_root or packet.get("build_digest") != live_digest:
            continue
        if not packet.get("proof"):
            continue
        return True
    return False


def phase(d: str) -> str:
    """`draft` / `sealed` / `signed` (`spec/verification.md`)."""
    if not os.path.isfile(os.path.join(d, MANIFEST)):
        load_recipe(d)
        return "draft"
    v = verify(d)
    if not v["ok"]:
        return "sealed"
    return "signed" if _is_signed(d) else "sealed"


# ----------------------------------------------------------------- sign_node
def sign_node(root: str, build_digest: str, links) -> str:
    """One signature-chain node: the root, the build digest, and the SET of
    signatures beneath it (enumeration order is not identity)."""
    payload = {"root": root, "build_digest": build_digest, "links": sorted(links)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# --------------------------------------------------------------- record_proof
def record_proof(m1: str, m2: str, m3: str) -> dict:
    """Run the crosscheck; on a pass, seal the proof onto M1 as residue.

    M1 must be a directory. A record leg's digest and signer identity land
    in the proof only once its signature verifies against
    `RETICULI_SIGNERS`; a frozen leg with no reachable anchor refuses
    rather than recording an unproven trail (`spec/record.md`).
    """
    result = _crosscheck.crosscheck(m1, m2, m3)
    if result["verdict"] != "accept":
        return {"proof_recorded": False}
    if not os.path.isdir(m1):
        raise ClaimError("record_proof requires a directory M1")

    anchor = os.environ.get(_core._ENV_SIGNERS)
    records = []
    for label, path in (("M2", m2), ("M3", m3)):
        if os.path.isdir(path):
            continue
        if not anchor or not os.path.isfile(anchor):
            raise ClaimError(
                f"record_proof: frozen leg {label} has no trust anchor "
                "(RETICULI_SIGNERS)")
        signer = _attest.record_signer(path, anchor)
        doc = _attest.record_read(path)
        records.append({"leg": label, "digest": _attest.record_digest(doc),
                         "signer": signer})

    manifest = read_manifest(m1)
    manifest["proof"] = {"kind": "crosscheck", "m2": m2, "m3": m3, "records": records}
    _core._write_json(os.path.join(m1, MANIFEST), manifest)
    return {"proof_recorded": True}
