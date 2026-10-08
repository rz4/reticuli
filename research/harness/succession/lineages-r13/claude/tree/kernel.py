"""The kernel's public surface: identity, verification, rebuilding, and the
three-machine test (spec/kernel-api.md).

This module composes the `_kernel` primitives -- `core`, `recipe`,
`identity`, `seal`, `run`, `build`, `attest`, `crosscheck` -- into the ~21
pinned names the acceptance check exercises. It is the one place above the
kernel that is safe to import from; nothing above should reach into
`reticuli._kernel` directly (spec/layers.md).
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import tomllib

from ._kernel import attest
from ._kernel import build as build_mod
from ._kernel import core
from ._kernel import crosscheck as crosscheck_mod
from ._kernel import identity
from ._kernel import recipe as recipe_mod
from ._kernel import run as run_mod
from ._kernel import seal as seal_mod

# ------------------------------------------------------------- constants --

ClaimError = core.ClaimError

RECIPE = core.RECIPE
STORE = core.STORE
MANIFEST = core.MANIFEST
LEDGER = core.LEDGER
NAMESPACE = core.NAMESPACE
SIGN_DIR = core.SIGN_DIR
SIGN_NAMESPACE = core.SIGN_NAMESPACE
_JAILED = core._JAILED

RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = attest.RECORD_FORMAT


def _guard(fn):
    """Wrap a primitive so that a raw filesystem/parse exception over
    untrusted, recipe-declared bytes (a missing pinned input, for one)
    becomes a `ClaimError` -- a refusal with a reason, never a crash."""
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except core.ClaimError:
            raise
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise core.ClaimError(f"{fn.__name__} refuses: {exc}") from exc
    wrapped.__name__ = getattr(fn, "__name__", "kernel_fn")
    return wrapped


# ------------------------------------------------------------- identity --

def _validate_claim_table(claim: dict) -> None:
    """Pins `recipe_mod.load_recipe` leaves open: `[claim] envelope` is a
    non-empty table of positive numbers, one per cost unit; `tolerance` a
    positive number; `mutation_floor` a non-negative one."""
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise core.ClaimError("[claim] envelope must be a non-empty table")
        for unit, ceiling in envelope.items():
            if unit not in core.COST_KEYS:
                raise core.ClaimError(f"[claim] envelope names an unknown unit: {unit!r}")
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                raise core.ClaimError(f"[claim] envelope.{unit} must be a positive number")
    if "tolerance" in claim:
        value = claim["tolerance"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise core.ClaimError("[claim] tolerance must be a positive number")
    if "mutation_floor" in claim:
        value = claim["mutation_floor"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise core.ClaimError("[claim] mutation_floor must be a non-negative number")


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe at `d`; refusals are `ClaimError`."""
    parsed = recipe_mod.load_recipe(d)
    _validate_claim_table(parsed.get("claim", {}) or {})
    return parsed


read_manifest = seal_mod.read_manifest
root = _guard(identity.root)
build_digest = _guard(identity.build_digest)
_hash_file = core._hash_file


def seal(d: str) -> dict:
    """Freeze a workspace into a claim: compute the root, write the
    manifest. Never refuses on a generated output's own path shape -- that
    freedom is the equivalence class."""
    try:
        parsed = crosscheck_mod.load_recipe_for_identity(d)
        parts = crosscheck_mod.parts_for_identity(parsed, d)
        r = identity._hash_str(identity._canonical_json(parts))
        manifest = {"name": parsed["claim"]["name"], "root": r, "parts": parts}
        manifest_path = os.path.join(d, core.MANIFEST)
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        core._write_json(manifest_path, manifest)
        return manifest
    except core.ClaimError:
        raise
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise core.ClaimError(f"seal refuses: {exc}") from exc


def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare it with the
    sealed manifest -- identity only, no gate is executed."""
    try:
        return crosscheck_mod.verify_for_identity(d)
    except core.ClaimError:
        raise
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise core.ClaimError(f"verify refuses: {exc}") from exc

ledger = run_mod.ledger
ledger_events = run_mod.ledger_events
cost = run_mod.cost


def run_gate(cmd: str, d: str, recipe) -> dict:
    """One gate: scrubbed env, sandboxed, bounded -- `_kernel/run.py`'s own
    `run_gate`, with the SENDING half of the execution contract fixed: a
    kernel that APPLIES a sandbox must tell the wrapped process WHICH
    backend (`RETICULI_JAILED` = the backend name), not merely that one was
    applied, or a gate that is itself a claim runner cannot tell inherit
    from nest."""
    timeout = run_mod.gate_timeout(recipe)
    backend = run_mod.sandbox_backend()
    real = os.path.realpath(d)
    real_jail = backend in ("seatbelt", "bubblewrap")

    home = tmp = None
    if real_jail:
        room = os.path.join(real, core.STORE, "room")
        home = os.path.join(room, "home")
        tmp = os.path.join(room, "tmp")
        os.makedirs(home, exist_ok=True)
        os.makedirs(tmp, exist_ok=True)

    env = run_mod._scrub_env(home, tmp)
    if real_jail:
        env[core._JAILED] = backend

    argv = run_mod._sandbox_argv(backend, [core._SHELL, "-c", cmd], real, home, tmp)
    code, out, err, timed_out = run_mod._run(argv, real, env, timeout)

    if timed_out:
        status = "timeout"
    elif code == 0:
        status = "ok"
    else:
        status = "failed"

    return {"status": status, "quarantine": backend,
            "stdout": out.decode("utf-8", "replace"), "stderr": err.decode("utf-8", "replace")}

record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_validate = crosscheck_mod.record_validate
record_read = crosscheck_mod.record_read
record_signer = crosscheck_mod.record_signer

crosscheck = crosscheck_mod.crosscheck
record_proof = crosscheck_mod.record_proof
mutation_score = crosscheck_mod.mutation_score
vacuous_gates = crosscheck_mod.vacuous_gates
gate_deciders = crosscheck_mod.gate_deciders
sign_node = crosscheck_mod.sign_node
independence = crosscheck_mod.independence


def preflight(recipe) -> list:
    """The environment contract: which of the claim's `requires` entries
    are missing on this host."""
    return run_mod.preflight(recipe)["missing"]


def sandbox(cmd: str, d: str) -> tuple:
    """A functional probe: run `cmd` sandboxed in `d`, report (status, the
    backend it ran under)."""
    result = run_mod.run_gate(cmd, d, {})
    return (result["status"], result["quarantine"])


# --------------------------------------------------------------- phase --

def _verify_signature(path: str, signature: str, anchor: str, namespace: str) -> bool:
    """A detached ssh signature over `path`'s bytes, verified against every
    principal the anchor says could have made it, in `namespace`."""
    if not (os.path.isfile(path) and os.path.isfile(signature) and os.path.isfile(anchor)):
        return False
    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", anchor, "-s", signature],
            capture_output=True, timeout=30, text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    principals = [line.split()[0] for line in found.stdout.splitlines() if line.strip()]
    if not principals:
        return False
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return False
    for principal in principals:
        try:
            verified = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", principal,
                 "-n", namespace, "-s", signature],
                input=data, capture_output=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if verified.returncode == 0:
            return True
    return False


def _find_packet(sign_dir: str, digest: str):
    for name in sorted(os.listdir(sign_dir)):
        if not name.endswith(".packet.json"):
            continue
        path = os.path.join(sign_dir, name)
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            continue
        if hashlib.sha256(raw).hexdigest() != digest:
            continue
        try:
            return json.loads(raw)
        except ValueError:
            continue
    return None


def _signed(d: str, manifest: dict) -> bool:
    """Trusted (an anchored signer) and proven (a recorded proof) and
    coherent (the stored packet matches both the signature and the current
    bytes) -- signed is authorized and proven together, never either alone."""
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):
        return False
    sign_dir = os.path.join(d, core.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return False

    current_root = manifest["root"]
    try:
        current_digest = identity.build_digest(d)
    except (OSError, UnicodeDecodeError, ValueError, core.ClaimError):
        return False

    for name in sorted(os.listdir(sign_dir)):
        if not name.endswith(".sign.json"):
            continue
        stmt_path = os.path.join(sign_dir, name)
        sig_path = stmt_path + ".sig"
        if not os.path.isfile(sig_path):
            continue
        if not _verify_signature(stmt_path, sig_path, anchor, core.SIGN_NAMESPACE):
            continue
        try:
            with open(stmt_path, encoding="utf-8") as f:
                stmt = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(stmt, dict) or stmt.get("root") != current_root:
            continue
        packet = _find_packet(sign_dir, stmt.get("packet_digest"))
        if packet is None or not packet.get("proof"):
            continue
        if packet.get("root") != current_root or packet.get("build_digest") != current_digest:
            continue
        return True
    return False


def phase(d: str) -> str:
    """`"draft"` / `"sealed"` / `"signed"` -- agreeing with `verify` on
    validity: a claim verify refuses, phase refuses too."""
    recipe = recipe_mod.load_recipe(d)
    manifest_path = os.path.join(d, core.MANIFEST)
    if not os.path.isfile(manifest_path):
        return "draft"
    verified = verify(d)
    if not verified["ok"]:
        raise core.ClaimError(f"claim at {d!r} does not verify against its sealed root")
    manifest = read_manifest(d)
    if not manifest.get("proof"):
        return "sealed"
    return "signed" if _signed(d, manifest) else "sealed"


# ------------------------------------------------------------- rebuild --

def _pinned_snapshot(into: str, recipe: dict) -> dict:
    snap = {}
    for path in recipe_mod._inputs(recipe, into):
        snap[path] = core._hash_file(core._safe(into, path))
    with open(recipe_mod.recipe_path(into), "rb") as f:
        snap["__recipe__"] = hashlib.sha256(f.read()).hexdigest()
    return snap


def rebuild(d: str, producer=None, into: str = None, *, produce_from=None,
            input_from=None, guidance: bool = True, producer_env: dict = None) -> dict:
    """Regrow a claim's generated outputs into a fresh room: a producer (a
    shell command), or component-supplied bytes (`produce_from`), then every
    gate, then seal. Refuses -- never a bare failure dict -- on anything
    that keeps the claim from holding: a hostile recipe, a missing
    requirement, a timed-out or failing gate, or a producer that rewrote
    what it was never authorized to touch."""
    recipe = recipe_mod.load_recipe(d)

    if os.path.exists(into) and os.listdir(into):
        raise core.ClaimError(f"refuses a non-empty rebuild target: {into!r}")
    os.makedirs(into, exist_ok=True)
    into_real = os.path.realpath(into)

    auth = crosscheck_mod.authorize(d, recipe)
    if not auth["ok"]:
        raise core.ClaimError(f"rebuild refused (environment): {auth['reason']}")

    build_mod._materialize(d, into, recipe, include_generated=False)
    if input_from:
        for path, src in input_from.items():
            core._copy_into(src, core._safe(into, path))

    snapshot = _pinned_snapshot(into, recipe)

    outputs = recipe_mod.generated_outputs(recipe)
    usage_path = os.path.join(into_real, core.STORE, "usage.json")
    os.makedirs(os.path.dirname(usage_path), exist_ok=True)

    reuse_outputs = None
    if produce_from is not None:
        copied = []
        if isinstance(produce_from, dict):
            for output, src in produce_from.items():
                if os.path.isfile(src):
                    core._copy_into(src, os.path.join(into, output))
                    copied.append(output)
        else:
            for output in outputs:
                src = core._safe(produce_from, output)
                if os.path.isfile(src):
                    core._copy_into(src, os.path.join(into, output))
                    copied.append(output)
        reuse_outputs = copied
    else:
        started = time.monotonic()
        prod_result = build_mod._produce(producer, into, recipe, outputs, usage_path,
                                         guidance=guidance, producer_env=producer_env)
        if prod_result["status"] != "ok":
            detail = prod_result.get("stderr") or prod_result.get("stdout") or ""
            raise core.ClaimError(
                f"rebuild refused ({prod_result['status']}): {detail[-300:]}")
        elapsed = time.monotonic() - started
        raw_usage = build_mod._read_usage(usage_path)
        usage = dict(raw_usage)
        usage["seconds"] = elapsed
        if "calls" not in usage:
            usage["calls"] = 1
        run_mod.ledger(into, usage)

    if _pinned_snapshot(into, recipe) != snapshot:
        raise core.ClaimError(
            "rebuild refused: the producer rewrote a pinned input or the recipe itself")

    gates = []
    ok = True
    quarantine = "none"
    for step in recipe_mod.gates(recipe):
        result = run_gate(step["run"], into, recipe)
        quarantine = result["quarantine"]
        gates.append({"output": step["output"], "status": result["status"],
                      "quarantine": result["quarantine"]})
        run_mod.ledger(into, {"event": "gate", "output": step["output"],
                               "status": result["status"], "quarantine": result["quarantine"]})
        if result["status"] != "ok":
            ok = False
    if not ok:
        raise core.ClaimError(f"rebuild refused: a gate did not pass: {gates!r}")

    host = core._judging_host()
    run_mod.ledger(into, {"event": "environment", "python": platform.python_version(),
                           "platform": host["platform"], "machine": host["machine"],
                           "quarantine": quarantine})
    if reuse_outputs is not None:
        for output in reuse_outputs:
            run_mod.ledger(into, {"event": "reuse", "output": output})

    vendor = os.environ.get(core._ENV_VENDOR)
    model = os.environ.get(core._ENV_MODEL)
    if vendor or model:
        run_mod.ledger(into, {"event": "producer", "vendor": vendor, "model": model, "blind": True})

    manifest = seal(into)
    return {"root": manifest["root"], "status": "ok", "gates": gates, "quarantine": quarantine}


# --------------------------------------------------------------- audit --

def audit(d: str, produce_from=None, shallow: bool = False) -> dict:
    """Re-earn a sealed claim's gates cold: identity must hold, the host
    must be able to test it, and every gate reruns in a fresh room against
    the bytes present (or, with `produce_from`, substituted bytes) --
    composing what a dependent ships against the component's own check."""
    recipe = recipe_mod.load_recipe(d)
    gate_steps = recipe_mod.gates(recipe)

    try:
        verified = crosscheck_mod.verify_for_identity(d)
    except core.ClaimError:
        raise
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise core.ClaimError(f"audit refuses: {exc}") from exc

    if not verified["ok"]:
        return {"ok": False, "verdict": "mismatch", "root": verified["root"],
                "recomputed": verified["recomputed"],
                "gates": [{"output": s["output"], "status": "mismatch", "quarantine": None}
                          for s in gate_steps],
                "environment": []}

    auth = crosscheck_mod.authorize(d, recipe)
    if not auth["ok"]:
        missing = run_mod.preflight(recipe)["missing"]
        return {"ok": False, "verdict": "environment", "reason": auth["reason"],
                "root": verified["root"],
                "gates": [{"output": s["output"], "status": "environment", "quarantine": None}
                          for s in gate_steps],
                "environment": missing}

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    old_path = os.environ.get("PATH")
    try:
        build_mod._materialize(d, room, recipe, include_generated=True)
        if produce_from:
            for output, src in produce_from.items():
                core._copy_into(src, core._safe(room, output))
        if auth.get("venv"):
            os.environ["PATH"] = os.path.join(auth["venv"], "bin") + os.pathsep + (old_path or "")

        gates = []
        ok = True
        for step in gate_steps:
            result = run_mod.run_gate(step["run"], room, recipe)
            if result["status"] != "ok":
                status = result["status"]
                ok = False
            elif build_mod._compare_pin(d, room, step["output"]):
                status = "ok"
            else:
                status = "mismatch"
                ok = False
            gates.append({"output": step["output"], "status": status,
                          "quarantine": result["quarantine"]})
        return {"ok": ok, "verdict": "accept" if ok else "reject",
                "root": verified["root"], "gates": gates, "environment": []}
    finally:
        if auth.get("venv"):
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path
        shutil.rmtree(room, ignore_errors=True)
