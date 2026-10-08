"""Building: materialize a room, run a producer or re-earn gates, seal the result.

`rebuild` regrows a claim's generated outputs: a fresh room is materialized
from the claim's pinned bytes, a producer writes the generated outputs (free
of the gate's sandbox, scrubbed but keeping the caller's own HOME), every
gate then runs sandboxed as always, and a clean room seals to its root.

`audit` re-earns a sealed claim's gates cold: identity must hold first, a
fresh room gets the claim's present bytes (generated outputs included,
trusted as given -- nothing here regrows them), each gate reruns, and its
pinned verdict must reproduce byte-for-byte; a carried verdict that does not
reproduce is a mismatch, not a pass.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time

from . import core
from . import identity
from . import recipe as recipe_mod
from . import run as run_mod
from . import seal as seal_mod

sandbox_backend = run_mod.sandbox_backend


# ------------------------------------------------------------------- toml --

def _toml_string(s: str) -> str:
    """A TOML basic string literal for `s`."""
    out = ['"']
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _toml_key(k: str) -> str:
    if k and all(c.isalnum() or c in "_-" for c in k):
        return k
    return _toml_string(k)


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return _toml_string(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        return "{ " + ", ".join(
            f"{_toml_key(k2)} = {_toml_value(v2)}" for k2, v2 in v.items()
        ) + " }"
    raise core.ClaimError(f"cannot serialize {v!r} into the room's recipe")


def _recipe_to_toml(doc: dict) -> str:
    """The preimage recipe, written as TOML: a document the room's own gates
    (and anything else that reads its recipe) can parse, not the canonical
    JSON a preimage uses to compute a root."""
    lines = ["[claim]"]
    for k, v in doc.get("claim", {}).items():
        lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    for step in doc.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for k, v in step.items():
            lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    lines.append("")
    return "\n".join(lines)


# -------------------------------------------------------------- guidance --

def _step_guidance(step: dict):
    """A produce step's guidance text under either spelling, or `None`."""
    for key in core.GUIDANCE_KEYS:
        text = step.get(key)
        if isinstance(text, str):
            return text
    return None


# ----------------------------------------------------------------- authz --

def _authorized(d: str, recipe: dict) -> dict:
    """Whether this host may run the claim's gates and producer: every
    `requires` entry present, and a declared `environment` furnished."""
    pf = run_mod.preflight(recipe)
    if not pf["ok"]:
        return {"ok": False, "reason": f"missing requirements: {pf['missing']}"}
    fu = run_mod.furnish(d, recipe)
    if fu["status"] != "ok":
        return {"ok": False, "reason": fu.get("reason", "environment not furnished")}
    return {"ok": True, "venv": fu.get("venv")}


def _ssh_verify(path: str, signature: str, signers: str, namespace: str) -> bool:
    """Verify a detached ssh signature (`ssh-keygen -Y verify`) over a
    file's bytes, against an allowed-signers file, in a namespace."""
    if not (os.path.isfile(path) and os.path.isfile(signature) and os.path.isfile(signers)):
        return False
    try:
        with open(path, "rb") as f:
            data = f.read()
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", "*",
             "-n", namespace, "-s", signature],
            input=data, capture_output=True, timeout=30,
        )
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ------------------------------------------------------------- materialize --

def _materialize(d: str, into: str, recipe: dict, include_generated: bool = False) -> None:
    """A fresh room for `d`'s claim: its own recipe (byte-for-byte at format
    1-2; the guidance-stripped, format-4-ordered preimage as TOML at format
    3+), every pinned input, every non-generated produce-step output, and --
    when asked -- the generated outputs present now."""
    os.makedirs(into, exist_ok=True)

    fmt = identity._claim_format(recipe)
    if fmt >= 3:
        text = _recipe_to_toml(identity._preimage_recipe(recipe))
        with open(os.path.join(into, core.RECIPE), "w", encoding="utf-8") as f:
            f.write(text)
    else:
        src_path = recipe_mod.recipe_path(d)
        with open(src_path, "rb") as f:
            data = f.read()
        with open(os.path.join(into, os.path.basename(src_path)), "wb") as f:
            f.write(data)

    for path in recipe_mod._inputs(recipe, d):
        core._copy_into(core._safe(d, path), os.path.join(into, path))

    for step in recipe_mod.produces(recipe):
        if step.get("class", "generated") == "generated":
            continue
        src = core._safe(d, step["output"])
        if not os.path.exists(src):
            continue
        sig, signers = step.get("signature"), step.get("signers")
        if sig and signers:
            verified = _ssh_verify(
                src, core._safe(d, sig), core._safe(d, signers), core.NAMESPACE)
            if not verified:
                raise core.ClaimError(
                    f"refuses an unauthorized pinned output: {step['output']!r}")
        core._copy_into(src, os.path.join(into, step["output"]))

    if include_generated:
        for output in recipe_mod.generated_outputs(recipe):
            src = core._safe(d, output)
            if os.path.exists(src):
                core._copy_into(src, os.path.join(into, output))


def _compare_pin(d: str, room: str, output: str) -> bool:
    """Whether a gate's freshly produced output in `room` reproduces the
    bytes already pinned for it in `d`."""
    try:
        return core._hash_file(os.path.join(d, output)) == \
            core._hash_file(os.path.join(room, output))
    except core.ClaimError:
        return False


# -------------------------------------------------------------- producer --

def _read_usage(path: str) -> dict:
    """A producer's self-reported usage: `usd`/`tokens`/`calls` only --
    `seconds` is never accepted from a usage payload, only measured."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(obj, dict):
        return {}
    usage = {}
    for key in ("usd", "tokens", "calls"):
        value = obj.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            usage[key] = value
    return usage


def _produce(cmd: str, room: str, recipe: dict, outputs: list, usage_path: str,
             guidance: bool = True, producer_env=None) -> dict:
    """Run the producer: scrubbed but unsandboxed, the caller's own HOME,
    told every output and which one to write, and (unless withheld) handed
    the recipe's guidance."""
    real = os.path.realpath(room)
    env = run_mod._scrub_env()
    env[core._ENV_CLAIM] = real
    env[core._ENV_OUTPUTS] = json.dumps(outputs)
    if outputs:
        env[core._ENV_OUTPUT] = os.path.join(real, outputs[0])
    env[core._ENV_USAGE] = usage_path
    if guidance:
        texts = [t for t in (_step_guidance(s) for s in recipe_mod.produces(recipe)) if t]
        if texts:
            env[core._ENV_REQUEST] = "\n".join(texts)
    if producer_env:
        for k, v in producer_env.items():
            env[str(k)] = str(v)

    argv = [core._SHELL, "-c", cmd]
    code, out, err, timed_out = run_mod._run(argv, real, env, core.PRODUCER_TIMEOUT)
    if timed_out:
        status = "timeout"
    elif code == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "stdout": out.decode("utf-8", "replace"),
            "stderr": err.decode("utf-8", "replace")}


# --------------------------------------------------------------- verbs --

def rebuild(d: str, producer, into: str, *, produce_from: str = None,
            input_from: str = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    """Regrow a claim's generated outputs into a fresh room, via a producer
    (a shell command) or by copying them `produce_from` an existing one,
    then run every gate and seal if they hold."""
    source = input_from or d
    recipe = recipe_mod.load_recipe(source)

    if os.path.exists(into) and os.listdir(into):
        raise core.ClaimError(f"refuses a non-empty rebuild target: {into!r}")
    os.makedirs(into, exist_ok=True)

    auth = _authorized(source, recipe)
    if not auth["ok"]:
        return {"root": None, "status": "environment", "reason": auth["reason"]}

    _materialize(source, into, recipe, include_generated=False)

    outputs = recipe_mod.generated_outputs(recipe)
    usage_path = os.path.join(into, core.STORE, "usage.json")
    os.makedirs(os.path.dirname(usage_path), exist_ok=True)

    if produce_from is not None:
        for output in outputs:
            src = core._safe(produce_from, output)
            if os.path.isfile(src):
                core._copy_into(src, os.path.join(into, output))
        prod_result = {"status": "ok", "stdout": "", "stderr": ""}
    else:
        started = time.monotonic()
        prod_result = _produce(producer, into, recipe, outputs, usage_path,
                               guidance=guidance, producer_env=producer_env)
        if prod_result["status"] == "ok":
            usage = _read_usage(usage_path)
            usage["seconds"] = time.monotonic() - started
            run_mod.ledger(into, usage)

    if prod_result["status"] != "ok":
        return {"root": None, "status": prod_result["status"],
                "stdout": prod_result["stdout"], "stderr": prod_result["stderr"]}

    gates = []
    ok = True
    quarantine = "none"
    for step in recipe_mod.gates(recipe):
        result = run_mod.run_gate(step["run"], into, recipe)
        quarantine = result["quarantine"]
        gates.append({"output": step["output"], "status": result["status"],
                      "quarantine": result["quarantine"]})
        if result["status"] != "ok":
            ok = False

    if not ok:
        return {"root": None, "status": "failed", "gates": gates,
                "quarantine": quarantine}

    manifest = seal_mod.seal(into)
    return {"root": manifest["root"], "status": "ok", "gates": gates,
            "quarantine": quarantine}


def audit(d: str, shallow: bool = False) -> dict:
    """Re-earn a sealed claim's gates cold: identity must hold, every gate
    reruns in a fresh room against the bytes present, and its pinned verdict
    must reproduce byte-for-byte."""
    recipe = recipe_mod.load_recipe(d)
    verified = seal_mod.verify(d)
    if not verified["ok"]:
        return {"ok": False, "verdict": "mismatch", "root": verified["root"],
                "recomputed": verified["recomputed"], "gates": []}

    auth = _authorized(d, recipe)
    if not auth["ok"]:
        return {"ok": False, "verdict": "environment", "reason": auth["reason"],
                "root": verified["root"], "gates": []}

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        _materialize(d, room, recipe, include_generated=True)
        gates = []
        ok = True
        for step in recipe_mod.gates(recipe):
            result = run_mod.run_gate(step["run"], room, recipe)
            if result["status"] != "ok":
                status = result["status"]
                ok = False
            elif _compare_pin(d, room, step["output"]):
                status = "reproduced"
            else:
                status = "mismatch"
                ok = False
            gates.append({"output": step["output"], "status": status,
                          "quarantine": result["quarantine"]})
        return {"ok": ok, "verdict": "accept" if ok else "reject",
                "root": verified["root"], "gates": gates}
    finally:
        shutil.rmtree(room, ignore_errors=True)
