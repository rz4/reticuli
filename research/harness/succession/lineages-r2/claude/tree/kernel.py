"""reticuli.kernel: the public kernel surface (spec/kernel-api.md).

A thin facade over `_kernel/*`: identity and sealing (`_kernel.identity`,
`_kernel.seal`), gate execution and cost (`_kernel.run`), the deep audit,
records, and the three-machine test (`_kernel.crosscheck`), plus the two
verbs that only make sense at this layer -- `rebuild` (regrow generated
outputs from a producer until the gates pass) and `sign` (a human signs the
root; represented here as `sign_node`, the signature-chain primitive, and
`phase`, which reads whether a trusted, undrifted signature exists).

Stdlib only, never the network.
"""
import hashlib
import json
import os
import platform
import stat
import sys
import time

from ._kernel import build, core, identity, run
from ._kernel import crosscheck as _crosscheck
from ._kernel import recipe as _recipe
from ._kernel import seal as _seal
from ._kernel.core import ClaimError

# --- constants (spec/kernel-api.md) ----------------------------------------
NAMESPACE = core.NAMESPACE
DIGEST = core.DIGEST
FORMAT = core.FORMAT
STORE = core.STORE
MANIFEST = core.MANIFEST
RECIPE = core.RECIPE
LEGACY_RECIPE = core.LEGACY_RECIPE
LEDGER = core.LEDGER
SIGN_DIR = core.SIGN_DIR
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = _crosscheck.RECORD_NAMESPACE
RECORD_FORMAT = _crosscheck.RECORD_FORMAT
_JAILED = core._JAILED

# --- pass-through primitives -------------------------------------------------
_hash_file = core._hash_file
load_recipe = _crosscheck.load_recipe
run_gate = _crosscheck.run_gate
preflight = run.preflight
cost = run.cost
build_digest = identity.build_digest

# --- crosscheck-layer verbs --------------------------------------------------
crosscheck = _crosscheck.crosscheck
record_proof = _crosscheck.record_proof
audit = _crosscheck.audit
mutation_score = _crosscheck.mutation_score
vacuous_gates = _crosscheck.vacuous_gates
gate_deciders = _crosscheck.gate_deciders
independence = _crosscheck.independence
record_validate = _crosscheck.record_validate
record_canonical = _crosscheck.record_canonical
record_digest = _crosscheck.record_digest
record_read = _crosscheck.record_read
record_signer = _crosscheck.record_signer


def read_manifest(d: str) -> dict:
    """Read and validate `.reticuli/manifest.json`, guarded against bytes
    that are not valid UTF-8 -- `_kernel.seal.read_manifest` catches a
    missing file and invalid JSON but not invalid encoding, which a
    corrupted manifest can just as easily be."""
    try:
        return _seal.read_manifest(d)
    except UnicodeDecodeError as e:
        raise ClaimError(f"manifest at {d!r} is not valid UTF-8: {e}") from e


def root(parsed: dict, d: str) -> str:
    """The claim's identity (spec/identity.md), guarded against filesystem
    aliasing (hardlinks, FIFOs, other special files) that `_kernel.identity`
    does not itself refuse."""
    return _crosscheck.safe_root(parsed, d)


def seal(d: str) -> dict:
    """Freeze `d`: compute the root, write `.reticuli/manifest.json`.
    Returns the manifest written: `{"name": ..., "root": ...}`.
    """
    parsed = _crosscheck.load_recipe(d)
    name = parsed["claim"]["name"]
    computed_root = _crosscheck.safe_root(parsed, d)
    manifest = {"name": name, "root": computed_root}
    store = os.path.join(d, core.STORE)
    os.makedirs(store, exist_ok=True)
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    return manifest


def verify(d: str) -> dict:
    """Recompute the root from the bytes present; compare with the sealed
    one. Identity only -- no gate is executed."""
    manifest = read_manifest(d)
    parsed = _crosscheck.load_recipe(d)
    recomputed = _crosscheck.safe_root(parsed, d)
    return {"ok": recomputed == manifest["root"], "root": manifest["root"],
            "recomputed": recomputed, "name": manifest["name"]}


def sandbox(cmd: str, d: str = None) -> tuple:
    """A functional probe of the host sandbox (v1: `jail`): run `cmd` under
    whatever confinement applies in `d`, returning `(run_result, backend)`."""
    d = d or os.getcwd()
    result = _crosscheck.run_gate(cmd, d)
    return (result, result["quarantine"])


def sign_node(root_value: str, digest: str, links) -> str:
    """The signature-chain node computation: folds a layer's root, its build
    digest, and the *set* of signatures beneath it -- enumeration order of
    `links` is not identity."""
    payload = {"root": root_value, "build_digest": digest, "links": sorted(set(links))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _is_signed(d: str) -> bool:
    """Whether a trusted, undrifted `SIGN_NAMESPACE` signature exists over
    the claim's current root and build digest, coupled to a recorded proof."""
    signers = os.environ.get(core._ENV_SIGNERS)
    if not signers or not os.path.isfile(signers):
        return False
    sign_dir = os.path.join(d, core.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return False
    try:
        parsed = _crosscheck.load_recipe(d)
        current_root = _crosscheck.safe_root(parsed, d)
        current_digest = identity.build_digest(d)
    except (OSError, ClaimError):
        return False

    for name in sorted(os.listdir(sign_dir)):
        if not name.endswith(".sign.json"):
            continue
        prefix = name[: -len(".sign.json")]
        stmt_path = os.path.join(sign_dir, name)
        sig_path = stmt_path + ".sig"
        packet_path = os.path.join(sign_dir, f"{prefix}.packet.json")
        if not os.path.isfile(sig_path) or not os.path.isfile(packet_path):
            continue
        try:
            with open(stmt_path, "rb") as f:
                stmt_bytes = f.read()
            statement = json.loads(stmt_bytes)
            with open(packet_path, "rb") as f:
                packet_bytes = f.read()
            packet = json.loads(packet_bytes)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(statement, dict) or not isinstance(packet, dict):
            continue
        identity_name = statement.get("identity")
        if not isinstance(identity_name, str):
            continue
        if not build._ssh_verify(signers, identity_name, core.SIGN_NAMESPACE, sig_path, stmt_bytes):
            continue
        packet_digest = hashlib.sha256(packet_bytes).hexdigest()
        if statement.get("packet_digest") != packet_digest:
            continue
        if not statement.get("proof_recorded"):
            continue
        if packet.get("root") != current_root:
            continue
        if packet.get("build_digest") != current_digest:
            continue
        return True
    return False


def phase(d: str) -> str:
    """`draft` / `sealed` / `signed` (v1: vapor/liquid/solid).

    `phase` agrees with `verify` on validity: a claim `verify` refuses
    (a corrupt manifest or recipe, an escaping or missing input) is refused
    here too, never answered with a positive "sealed".
    """
    manifest_path = os.path.join(d, core.MANIFEST)
    if not os.path.isfile(manifest_path):
        _crosscheck.load_recipe(d)
        return "draft"
    v = verify(d)
    if not v["ok"]:
        raise ClaimError(
            f"claim at {d!r} does not verify: sealed root {v['root']} != "
            f"recomputed {v['recomputed']}"
        )
    return "signed" if _is_signed(d) else "sealed"


# ---------------------------------------------------------------------------
# rebuild: regrow generated outputs from a producer until the gates pass
# ---------------------------------------------------------------------------

def _snapshot(into: str, recipe_dest: str, parsed: dict) -> dict:
    snap = {"recipe": core._hash_file(recipe_dest)}
    for path in _recipe._inputs(parsed):
        snap[f"input:{path}"] = core._hash_file(os.path.join(into, path))
    return snap


def _produce_step(step: dict, room: str, producer: str, parsed: dict, bin_dir) -> dict:
    """Invoke `producer` for one `produce` step, the same way `build._produce`
    does, but with `RETICULI_USAGE` resolved to an ABSOLUTE path -- so a
    relative `into` does not double itself under the producer's own cwd."""
    guidance = build._step_guidance(step)
    extra_env = {
        core._ENV_CLAIM: parsed["claim"]["name"],
        core._ENV_OUTPUT: step["output"],
        core._ENV_OUTPUTS: "\n".join(_recipe.generated_outputs(parsed)),
        core._ENV_USAGE: os.path.join(room, core.USAGE),
    }
    if guidance is not None:
        extra_env[core._ENV_REQUEST] = guidance
    return _crosscheck._with_path(bin_dir, build._run_producer, producer, room,
                                   extra_env, core.PRODUCER_TIMEOUT)


def rebuild(d: str, producer: str, into: str, *, produce_from: dict = None,
            input_from: dict = None) -> dict:
    """Regrow generated outputs (via `producer`) until the gates pass; the
    redo's ledger is appended as residue (spec/kernel-api.md).

    `into` must not exist, or must be an empty directory -- a target already
    holding bytes (a claim or a stray file) is refused, not resumed into.
    `produce_from` supplies specific generated outputs from elsewhere
    (component-reuse, ledgered); `input_from` threads a fresh pinned input in
    place of the source claim's own copy (a deliberate, allowed substitution
    distinct from a producer rewriting pinned bytes on its own, which is
    always refused).
    """
    into_abs = os.path.abspath(into)
    if os.path.isdir(into_abs):
        if os.listdir(into_abs):
            raise ClaimError(f"rebuild target already holds bytes: {into!r}")
    elif os.path.exists(into_abs):
        raise ClaimError(f"rebuild target is not a directory: {into!r}")
    else:
        os.makedirs(into_abs, exist_ok=True)
    os.makedirs(os.path.join(into_abs, core.STORE), exist_ok=True)

    parsed = _crosscheck.load_recipe(d)

    missing = run.preflight(parsed)
    if missing:
        raise ClaimError(f"environment: missing {', '.join(missing)}")
    furnished = _crosscheck.furnish(d, parsed)
    if not furnished["ok"]:
        raise ClaimError(f"environment: cannot furnish claim: {furnished.get('reason')}")
    bin_dir = furnished.get("bin")

    input_from = input_from or {}
    for path in _recipe._inputs(parsed):
        src = input_from.get(path, os.path.join(d, path))
        core._copy_into(src, os.path.join(into_abs, path))

    fmt = parsed["claim"].get("format", 1)
    src_recipe_path = _recipe.recipe_path(d)
    if fmt >= 3:
        recipe_dest = os.path.join(into_abs, core.RECIPE)
        with open(recipe_dest, "w", encoding="utf-8") as f:
            f.write(build._dump_recipe_toml(identity._preimage_recipe(parsed)))
    else:
        recipe_dest = os.path.join(into_abs, os.path.basename(src_recipe_path))
        with open(src_recipe_path, "rb") as f:
            raw_recipe = f.read()
        with open(recipe_dest, "wb") as f:
            f.write(raw_recipe)

    produce_from = produce_from or {}
    for output, src in produce_from.items():
        dest = core._safe(into_abs, output)
        core._copy_into(src, dest)
        run.ledger(into_abs, {"event": "reuse", "output": output})

    before = _snapshot(into_abs, recipe_dest, parsed)

    vendor = os.environ.get(core._ENV_VENDOR)
    model = os.environ.get(core._ENV_MODEL)

    for step in _recipe.produces(parsed):
        if "from" in step or step["output"] in produce_from:
            continue
        started = time.monotonic()
        result = _produce_step(step, into_abs, producer, parsed, bin_dir)
        elapsed = time.monotonic() - started
        if result["status"] != "ok":
            raise ClaimError(
                f"producer failed for {step['output']!r}: {result['status']}: "
                f"{(result['stderr'] or result['stdout'])[-500:]}"
            )
        entry = {"event": "oracle", "seconds": elapsed}
        entry.update(build._read_usage(into_abs))
        entry.setdefault("calls", 1)
        if vendor is not None or model is not None:
            entry["vendor"] = vendor
            entry["model"] = model
            entry["blind"] = True
        run.ledger(into_abs, entry)

    after = _snapshot(into_abs, recipe_dest, parsed)
    if before != after:
        raise ClaimError(
            "a producer rewrote pinned bytes -- the recipe or a declared "
            "input changed after materialization"
        )

    for step in _recipe.gates(parsed):
        result = _crosscheck._with_path(bin_dir, _crosscheck.run_gate, step["run"], into_abs, parsed)
        run.ledger(into_abs, {"event": "gate", "output": step["output"],
                              "quarantine": result["quarantine"]})
        if result["status"] != "ok":
            raise ClaimError(f"gate {step['output']!r} did not pass: {result['status']}")

    run.ledger(into_abs, {
        "event": "environment",
        "python": platform.python_version(),
        "platform": sys.platform,
        "quarantine": run.sandbox_backend(),
    })

    return seal(into_abs)
