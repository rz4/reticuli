"""Rebuild and audit: regrowing generated outputs, and re-earning verdicts.

`rebuild` materializes a fresh, empty room from a claim's recipe and
pinned inputs, runs a producer once -- free of any sandbox, with the
caller's own environment (network and HOME included), and told which
output to write via `RETICULI_OUTPUT`/`RETICULI_OUTPUTS` -- then runs
every gate (scrubbed, sandboxed, bounded) and seals the result.

`audit` trusts no carried verdict: it recomputes identity, then re-runs
every gate cold in a fresh room built from the bytes present, requiring
every pinned byte to reproduce exactly.

Stdlib only.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time

from .core import (
    ClaimError,
    GUIDANCE_KEYS,
    PRODUCER_TIMEOUT,
    STORE,
    USAGE,
    _ENV_OUTPUT,
    _ENV_OUTPUTS,
    _ENV_REQUEST,
    _ENV_USAGE,
    _JAILED,
    _SHELL,
    _hash_file,
    _safe,
)
from . import recipe as _recipe
from . import seal as _seal
from .run import ledger, preflight, run_gate, sandbox_backend

_USAGE_KEYS = frozenset({"usd", "tokens", "calls"})
_PROTECTED_PRODUCER_ENV = frozenset(
    {_ENV_OUTPUT, _ENV_OUTPUTS, _ENV_REQUEST, _ENV_USAGE, _JAILED}
)


# ---- moving bytes between a claim and a judging room -----------------------

def _copy_rel(src_base: str, dst_base: str, rel_path: str) -> None:
    src = _safe(src_base, rel_path)
    dst = _safe(dst_base, rel_path)
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    shutil.copy2(src, dst)


def _materialize(d: str, into: str, parsed: dict, *, include_generated: bool = False,
                  input_from: str = None) -> str:
    """Build a fresh judging room at `into`: the recipe, every pinned
    input, and -- when asked -- whatever generated output already exists
    in `d`. Refuses a target that already holds bytes."""
    if os.path.isdir(into) and os.listdir(into):
        raise ClaimError(f"a judging room must start empty: {into!r}")
    os.makedirs(into, exist_ok=True)

    recipe_src = _recipe.recipe_path(d)
    shutil.copy2(recipe_src, os.path.join(into, os.path.basename(recipe_src)))

    source = input_from or d
    for path in _recipe._inputs(parsed, source):
        _copy_rel(source, into, path)

    if include_generated:
        for output in _recipe.generated_outputs(parsed):
            if os.path.isfile(_safe(d, output)):
                _copy_rel(d, into, output)
    return into


def _compare_pin(produced_path: str, reference_path: str) -> bool:
    """Whether the bytes just produced in a judging room reproduce the
    bytes already pinned at `reference_path`."""
    if not os.path.isfile(produced_path):
        return False
    return _hash_file(produced_path) == _hash_file(reference_path)


def _step_guidance(step: dict):
    """A produce step's hint for a rebuilder, under either spelling
    (`guidance`, older `request`); `None` when the step carries neither."""
    for key in GUIDANCE_KEYS:
        if key in step:
            return step[key]
    return None


# ---- the producer: the caller's own oracle, running free -------------------

def _authorized(name: str) -> bool:
    """Whether a caller-supplied `producer_env` override may set `name` --
    refusing to let it clobber a variable the kernel itself uses to tell
    the producer what to build."""
    return name not in _PROTECTED_PRODUCER_ENV


def _read_usage(room: str) -> dict:
    """A producer's self-reported cost, written at `USAGE` inside the
    room; an absent file means nothing was reported. `seconds` is never
    accepted here -- it is the kernel's own measurement."""
    path = os.path.join(room, USAGE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            usage = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimError(f"malformed usage report at {path!r}: {exc}") from exc
    if not isinstance(usage, dict):
        raise ClaimError(f"malformed usage report at {path!r}: not a JSON object")
    result = {}
    for key, value in usage.items():
        if key not in _USAGE_KEYS:
            raise ClaimError(f"usage report names a forbidden key: {key!r}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ClaimError(f"usage report key {key!r} must be a non-negative number")
        result[key] = value
    return result


def _produce(parsed: dict, room: str, producer: str, *, guidance: bool = True,
             producer_env: dict = None, timeout: float = None) -> dict:
    """Run the producer once, unsandboxed, with the caller's own
    environment -- network and HOME included -- plus the kernel's own
    naming of what to build."""
    outputs = [s["output"] for s in _recipe.produces(parsed)
               if s.get("class", "generated") == "generated" and "from" not in s]
    room_real = os.path.realpath(room)
    os.makedirs(os.path.join(room_real, STORE), exist_ok=True)

    env = dict(os.environ)
    if outputs:
        env[_ENV_OUTPUT] = os.path.join(room_real, outputs[0])
    env[_ENV_OUTPUTS] = json.dumps(outputs)
    env[_ENV_USAGE] = os.path.join(room_real, USAGE)
    if guidance:
        for step in _recipe.produces(parsed):
            text = _step_guidance(step)
            if text is not None:
                env[_ENV_REQUEST] = text
                break
    if producer_env:
        for key, value in producer_env.items():
            if _authorized(key):
                env[key] = value

    proc = subprocess.run(
        [_SHELL, "-c", producer], cwd=room_real, env=env,
        timeout=timeout or PRODUCER_TIMEOUT,
    )
    if proc.returncode != 0:
        raise ClaimError(f"producer exited {proc.returncode}")
    return {"status": "ok"}


# ---- rebuild: regrow until the gates pass, then seal -----------------------

def rebuild(d: str, producer: str, into: str, *, produce_from: str = None,
            input_from: str = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    """Regrow a claim's generated outputs with `producer`, judged in a
    fresh room at `into`, until every gate passes; seals the room and
    returns its manifest plus the jail the gates ran under."""
    parsed = _recipe.load_recipe(d)
    missing = preflight(parsed)
    if missing:
        raise ClaimError(f"environment contract unmet: missing {missing!r}")

    _materialize(d, into, parsed, include_generated=False, input_from=input_from)

    if produce_from:
        for output in _recipe.generated_outputs(parsed):
            if os.path.isfile(_safe(produce_from, output)):
                _copy_rel(produce_from, into, output)

    start = time.time()
    _produce(parsed, into, producer, guidance=guidance, producer_env=producer_env)
    usage = _read_usage(into)
    event = dict(usage)
    event["seconds"] = time.time() - start
    ledger(into, event)

    quarantine = sandbox_backend()
    gate_rows = []
    for step in _recipe.gates(parsed):
        result = run_gate(step["run"], into, parsed)
        gate_rows.append({"output": step["output"], "status": result["status"],
                           "quarantine": result["quarantine"]})
        if result["status"] != "ok":
            raise ClaimError(f"gate {step['output']!r} did not pass: {result['status']}")

    manifest = _seal.seal(into)
    return {"root": manifest["root"], "name": manifest["name"],
            "quarantine": quarantine, "gates": gate_rows}


# ---- audit: re-earn cold, trusting no carried verdict -----------------------

def audit(d: str, *, deep: bool = True) -> dict:
    """Re-earn, cold: recompute identity, then re-run every gate in a
    fresh room built from the bytes present, trusting no carried verdict.
    `ok` holds only when identity holds and every gate reproduces its
    pinned bytes."""
    vr = _seal.verify(d)
    if not vr["ok"]:
        return {"ok": False, "verdict": "mismatch", "root": vr["root"], "gates": []}

    parsed = _recipe.load_recipe(d)
    missing = preflight(parsed)
    if missing:
        gate_rows = [{"output": step["output"], "status": "environment",
                      "quarantine": "none"} for step in _recipe.gates(parsed)]
        return {"ok": False, "verdict": "environment", "root": vr["root"],
                "gates": gate_rows}

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        _materialize(d, room, parsed, include_generated=True)
        gate_rows = []
        ok = True
        for step in _recipe.gates(parsed):
            result = run_gate(step["run"], room, parsed)
            status = result["status"]
            if status == "ok" and step.get("class", "pinned") != "generated":
                produced = _safe(room, step["output"])
                reference = _safe(d, step["output"])
                if not _compare_pin(produced, reference):
                    status = "mismatch"
            gate_rows.append({"output": step["output"], "status": status,
                               "quarantine": result["quarantine"]})
            if status != "ok":
                ok = False
        return {"ok": ok, "verdict": "ok" if ok else "mismatch", "root": vr["root"],
                "gates": gate_rows}
    finally:
        shutil.rmtree(room, ignore_errors=True)


# ---- signature verification (shared ssh mechanism) --------------------------

def _ssh_verify(allowed_signers: str, identity: str, namespace: str,
                 data: bytes, signature_path: str) -> bool:
    """Verify a detached ssh signature (`ssh-keygen -Y verify`) over
    `data`, against `allowed_signers`, in the given signature namespace."""
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", identity,
             "-n", namespace, "-s", signature_path],
            input=data, capture_output=True,
        )
    except OSError:
        return False
    return proc.returncode == 0
