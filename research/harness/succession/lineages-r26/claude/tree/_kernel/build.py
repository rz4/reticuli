"""Rebuilding and auditing a claim: the kernel's two re-earning verbs.

`rebuild` materializes a fresh room from a claim's pinned bytes (its
declared inputs, plus -- at format 3+ -- the guidance-stripped preimage
recipe, written under the recipe's own filename so a gate that reads its
own recipe reads what the root names), runs a producer there to regrow
every `generated` output, then runs the claim's gates in that room and
seals it. The producer is handed the caller's own environment -- network,
`HOME`, credentials included -- because it is the caller's oracle, working
with the caller's standing; only the gates it feeds are sandboxed and
scrubbed (`spec/claim-format.md`).

`audit` trusts nothing: it re-verifies identity against the bytes present,
then re-runs every gate in place and requires the resulting bytes to match
what the sealed manifest pinned. A verdict is `ok` only when every gate
reproduces; a tampered pinned input fails identity before any gate runs.

Stdlib only, never the network.
"""
import contextlib
import json
import os
import re
import shutil
import subprocess
import time

from . import core, identity, recipe, run, seal
from .core import ClaimError

# -- a minimal TOML writer, just enough for a recipe's own shape -----------

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_key(k: str) -> str:
    return k if _BARE_KEY.match(k) else _toml_string(k)


def _toml_string(s: str) -> str:
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return _toml_string(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(
            f"{_toml_key(k)} = {_toml_value(x)}" for k, x in v.items()
        ) + " }"
    raise ClaimError(f"cannot serialize {v!r} as TOML")


def _dump_toml(doc: dict) -> str:
    """Render a preimage-recipe-shaped dict (`[claim]` + `[[step]]`) as TOML."""
    lines = []
    claim = doc.get("claim")
    if isinstance(claim, dict):
        lines.append("[claim]")
        for k, v in claim.items():
            lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
        lines.append("")
    for step in doc.get("step", []):
        lines.append("[[step]]")
        for k, v in step.items():
            lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
        lines.append("")
    return "\n".join(lines)


# -- furnished-environment PATH, scoped to a `with` block -------------------


@contextlib.contextmanager
def _path_prefixed(bindir):
    if not bindir:
        yield
        return
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = bindir + os.pathsep + old
    try:
        yield
    finally:
        os.environ["PATH"] = old


# -- producer guidance -------------------------------------------------------


def _step_guidance(step: dict):
    """A produce step's hint for a rebuilder, under either spelling, or `None`."""
    for key in core.GUIDANCE_KEYS:
        if key in step:
            return step[key]
    return None


# -- ssh signature primitives (shared low-level verbs; callers trust-anchor
# their own `allowed_signers`) ----------------------------------------------


def _ssh_verify(data: bytes, signature_path: str, namespace: str,
                 allowed_signers: str, principal: str) -> bool:
    """Verify a detached `ssh-keygen -Y` signature over `data`."""
    if not (os.path.isfile(signature_path) and os.path.isfile(allowed_signers)):
        return False
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", principal, "-n", namespace, "-s", signature_path],
            input=data, capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _authorized(principal: str, allowed_signers: str) -> bool:
    """Whether `principal` names a line in an `allowed_signers` file."""
    if not principal or not os.path.isfile(allowed_signers):
        return False
    with open(allowed_signers, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.split()[0] == principal:
                return True
    return False


# -- materializing the room a producer and its gates run in -----------------


def _materialize(d: str, into: str, parsed: dict, input_from: dict = None) -> str:
    """Build a fresh room: the claim's pinned inputs, plus its recipe.

    Format 1/2 copy the recipe file byte for byte, guidance included --
    their root covers the whole file. Format 3+ writes the preimage recipe
    (guidance stripped) as TOML under the same filename, so a gate that
    reads its own recipe reads exactly what the root names.
    """
    if os.path.isdir(into) and os.listdir(into):
        raise ClaimError(f"rebuild target is not empty: {into!r}")
    os.makedirs(into, exist_ok=True)

    input_from = input_from or {}
    for path in identity._declared_inputs(d, parsed):
        src_dir = input_from.get(path, d)
        src = core._safe(src_dir, path)
        dst = os.path.join(into, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    src_recipe = recipe.recipe_path(d)
    name = os.path.basename(src_recipe)
    dst_recipe = os.path.join(into, name)
    if identity._claim_format(parsed) >= 3:
        with open(dst_recipe, "w", encoding="utf-8") as f:
            f.write(_dump_toml(identity._preimage_recipe(parsed)))
    else:
        shutil.copy2(src_recipe, dst_recipe)

    os.makedirs(os.path.join(into, core.STORE), exist_ok=True)
    return into


# -- running the producer -----------------------------------------------------


def _produce(room: str, parsed: dict, producer: str, outputs: list,
             guidance: bool, producer_env: dict, usage_path: str) -> dict:
    """Run `producer` in `room`, inheriting the caller's own environment.

    The producer is the caller's oracle: it keeps the caller's network
    reachability and `HOME`, unjailed and unscrubbed -- only the gates its
    output faces are sandboxed. It is told every output the claim needs
    (`RETICULI_OUTPUTS`) and one absolute target to write (`RETICULI_OUTPUT`).
    """
    env = os.environ.copy()
    claim = parsed.get("claim", {})
    env[core._ENV_CLAIM] = claim.get("name", "")
    env[core._ENV_OUTPUTS] = json.dumps(outputs)
    env[core._ENV_OUTPUT] = os.path.join(room, outputs[0]) if outputs else room
    env[core._ENV_USAGE] = usage_path

    if guidance:
        hints = {}
        for step in recipe.produces(parsed):
            if step.get("output") in outputs:
                g = _step_guidance(step)
                if g is not None:
                    hints[step["output"]] = g
        if hints:
            env[core._ENV_REQUEST] = json.dumps(hints)

    if producer_env:
        env.update(producer_env)

    try:
        proc = subprocess.run(
            [core._SHELL, "-c", producer], cwd=room, env=env,
            timeout=core.PRODUCER_TIMEOUT, capture_output=True,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaimError(f"producer timed out: {e}") from e
    except OSError as e:
        raise ClaimError(f"producer failed to start: {e}") from e
    if proc.returncode != 0:
        raise ClaimError(
            f"producer exited {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace')}"
        )
    return {"returncode": proc.returncode}


def _read_usage(room: str) -> dict:
    """A producer's self-reported `usd`/`tokens`/`calls` -- `seconds` is the
    kernel's own measurement and is never accepted from a usage payload."""
    path = os.path.join(room, core.USAGE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    usage = {}
    for key in ("usd", "tokens", "calls"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            usage[key] = value
    return usage


# -- comparing a freshly earned gate output against its pin -----------------


def _compare_pin(d: str, path: str, expected) -> bool:
    """Whether the bytes now at `path` hash to the pin sealed for them."""
    if not isinstance(expected, str):
        return False
    resolved = core._safe(d, path)
    if not os.path.exists(resolved):
        return False
    try:
        return core._hash_file(resolved) == expected
    except ClaimError:
        return False


# -- rebuild ------------------------------------------------------------------


def rebuild(d: str, producer: str, into: str, *, produce_from: dict = None,
            input_from: dict = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    """Regrow `d`'s generated outputs in a fresh room until its gates pass."""
    parsed = recipe.load_recipe(d)

    missing = run.preflight(parsed)
    if missing:
        return {"root": None, "verdict": "environment", "missing": missing}

    furnished = run.furnish(d, parsed)
    if not furnished.get("ok", True):
        return {"root": None, "verdict": "environment",
                "reason": furnished.get("reason")}

    room = _materialize(d, into, parsed, input_from)

    produce_from = produce_from or {}
    needed = []
    for output in recipe.generated_outputs(parsed):
        if output in produce_from:
            src = produce_from[output]
            if not os.path.isabs(src):
                src = os.path.join(d, src)
            dst = core._safe(room, output)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        else:
            needed.append(output)

    usage_path = os.path.join(room, core.USAGE)
    started = time.monotonic()
    if needed:
        _produce(room, parsed, producer, needed, guidance, producer_env, usage_path)
    elapsed = time.monotonic() - started
    usage = _read_usage(room)

    gates_result = []
    with _path_prefixed(furnished.get("path")):
        for step in recipe.gates(parsed):
            outcome = run.run_gate(step["run"], room, parsed)
            gates_result.append({
                "output": step["output"],
                "status": outcome["status"],
                "quarantine": outcome["quarantine"],
            })

    manifest = seal.seal(room)

    entry = {"event": "rebuild", "when": core._now(),
              "quarantine": run.sandbox_backend(), "seconds": elapsed}
    entry.update(usage)
    run.ledger(d, entry)

    return {
        "root": manifest["root"],
        "name": manifest["name"],
        "gates": gates_result,
        "quarantine": run.sandbox_backend(),
        "cost": dict(usage, seconds=elapsed),
    }


# -- audit ---------------------------------------------------------------------


def audit(d: str) -> dict:
    """Re-earn `d`'s verdicts cold: identity first, then every gate, in place."""
    parsed = recipe.load_recipe(d)

    missing = run.preflight(parsed)
    if missing:
        return {"ok": False, "verdict": "environment", "missing": missing, "gates": []}

    furnished = run.furnish(d, parsed)
    if not furnished.get("ok", True):
        return {"ok": False, "verdict": "environment",
                "reason": furnished.get("reason"), "gates": []}

    ver = seal.verify(d)
    if not ver["ok"]:
        return {"ok": False, "verdict": "mismatch", "root": ver.get("root"), "gates": []}

    manifest = seal.read_manifest(d)
    pins = manifest.get("parts", {})

    gates_result = []
    overall_ok = True
    with _path_prefixed(furnished.get("path")):
        for step in recipe.gates(parsed):
            outcome = run.run_gate(step["run"], d, parsed)
            output = step["output"]
            if outcome["status"] in ("timeout", "failed"):
                status = outcome["status"]
            else:
                expected = pins.get(f"pinned:{output}")
                status = "ok" if _compare_pin(d, output, expected) else "mismatch"
            if status != "ok":
                overall_ok = False
            gates_result.append({
                "output": output,
                "status": status,
                "quarantine": outcome["quarantine"],
            })

    return {
        "ok": overall_ok,
        "verdict": None if overall_ok else "failed",
        "root": ver["root"],
        "name": ver["name"],
        "gates": gates_result,
    }
