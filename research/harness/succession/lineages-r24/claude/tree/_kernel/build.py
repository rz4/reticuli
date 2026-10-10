"""Build: audit (deep re-earning) and rebuild (regrow generated outputs)
(spec/verification.md, spec/claim-format.md, spec/identity.md).

`audit` trusts nothing stored: it recomputes identity, then re-runs every
gate cold and classifies each pinned byte as earned fresh (`reproduced`) or
not (`mismatch`), never reading a carried verdict. `rebuild` materializes a
fresh room holding only the claim's pinned bytes and its (guidance-stripped
at format >= 3) recipe, hands a producer the room and the names of the
outputs it must write, then earns the gates in place and seals the result.
"""
import json
import os
import subprocess

from reticuli._kernel import core, identity, recipe, run, seal

QUARANTINES = frozenset({"seatbelt", "bubblewrap", "inherited", "none"})


# -- TOML emission: only what a recipe's own shapes need --------------------

def _toml_string(s: str) -> str:
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
        return "{" + ", ".join(f"{k} = {_toml_value(vv)}" for k, vv in v.items()) + "}"
    raise core.ClaimError(f"refused: a {type(v).__name__} value has no TOML form")


def _write_toml_recipe(path: str, preimage: dict) -> None:
    """The room's recipe: the PREIMAGE, written as parseable TOML
    (spec/claim-format.md: "the room recipe is the preimage, as TOML")."""
    lines = ["[claim]"]
    for k in sorted(preimage.get("claim", {})):
        lines.append(f"{k} = {_toml_value(preimage['claim'][k])}")
    for step in preimage.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for k in sorted(step):
            lines.append(f"{k} = {_toml_value(step[k])}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# -- guidance: a hint for a producer, never a condition on acceptance -------

def _step_guidance(step: dict):
    """A produce step's hint for a rebuilder, under either spelling
    (`guidance`, `request`; spec/claim-format.md). `None` if it carries none."""
    for key in core.GUIDANCE_KEYS:
        v = step.get(key)
        if v is not None:
            return v
    return None


# -- materializing a room: pinned bytes and the preimage recipe only --------

def _materialize(d: str, into: str, parsed: dict) -> None:
    """Build the room at `into`: the claim's pinned inputs, every
    non-generated produce output nothing else will create, and the recipe
    the root was computed from -- never a generated or gate (validated)
    output, which are earned fresh in the room."""
    if os.path.exists(into):
        if os.listdir(into):
            raise core.ClaimError(f"refused: {into!r} already holds bytes")
    else:
        os.makedirs(into)

    def _copy_path(path: str) -> None:
        src = core._safe(d, path)
        dst = os.path.join(into, path)
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        core._copy_into(src, dst)

    for path in recipe._inputs(d, parsed):
        _copy_path(path)
    for step in parsed.get("step", []):
        if step.get("kind") == "produce" and identity._effective_class(step) == "pinned":
            _copy_path(step["output"])

    fmt = parsed.get("claim", {}).get("format", 1)
    if fmt < 3:
        src_recipe = recipe.recipe_path(d)
        core._copy_into(src_recipe, os.path.join(into, os.path.basename(src_recipe)))
    else:
        _write_toml_recipe(os.path.join(into, core.RECIPE), identity._preimage_recipe(parsed))


# -- the producer: the caller's oracle, inheriting the caller's standing ----

def _produce(room: str, parsed: dict, producer: str, guidance: bool = True,
             producer_env=None) -> None:
    """Run the producer in `room`, told which output to write (absolutely)
    and which outputs exist, unjailed and with the caller's HOME and
    network reachability (spec/claim-format.md)."""
    outputs = [s["output"] for s in recipe.produces(parsed)
               if identity._effective_class(s) == "generated" and s.get("from") is None]
    if not outputs:
        return
    real_room = os.path.realpath(room)
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env[core._ENV_OUTPUT] = os.path.join(real_room, outputs[0])
    env[core._ENV_OUTPUTS] = json.dumps(outputs)
    env[core._ENV_USAGE] = os.path.join(real_room, core.USAGE)
    if guidance:
        for step in recipe.produces(parsed):
            hint = _step_guidance(step)
            if hint is not None:
                env[core._ENV_REQUEST] = hint
                break
    if producer_env:
        env.update(producer_env)
    try:
        proc = subprocess.run([core._SHELL, "-c", producer], cwd=room, env=env,
                               timeout=core.PRODUCER_TIMEOUT, check=False)
    except subprocess.TimeoutExpired as e:
        raise core.ClaimError(f"producer timed out: {e}") from e
    if proc.returncode != 0:
        raise core.ClaimError(f"producer failed with exit {proc.returncode}")


def _read_usage(room: str):
    """Cost a producer self-reported at `[claim.USAGE]`, filtered to the
    keys a usage payload may carry -- `seconds` is the kernel's own
    measurement and is never accepted from one (spec/kernel-api.md)."""
    path = os.path.join(room, core.USAGE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    out = {k: raw[k] for k in ("usd", "tokens", "calls")
           if isinstance(raw.get(k), (int, float)) and not isinstance(raw.get(k), bool)}
    return out or None


# -- authorization: an ssh signature, verified against the caller's anchor --

def _ssh_verify(allowed_signers: str, namespace: str, signer_id: str,
                 signature_path: str, data: bytes) -> bool:
    """Verify a detached `ssh-keygen -Y` signature over `data`."""
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", signer_id,
             "-n", namespace, "-s", signature_path],
            input=data, capture_output=True, timeout=30, check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def _authorized(d: str) -> bool:
    """Whether an allowed-signers anchor is configured for this run -- the
    precondition for any ssh-based authorization check; unconfigured is
    `False`, not a crash."""
    signers = os.environ.get(core._ENV_SIGNERS)
    return bool(signers and os.path.isfile(signers))


# -- audit: re-earn every gate cold, trusting no carried verdict ------------

def _sealed_parts(d: str) -> dict:
    path = os.path.join(d, seal.PARTS_RESIDUE)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _compare_pin(d: str, step: dict, sealed_parts: dict) -> bool:
    """Whether a gate's just-earned output byte-matches what was pinned at
    seal time -- `reproduced` versus `mismatch` (spec/verification.md)."""
    want = sealed_parts.get("pinned:" + step["output"])
    if want is None:
        return False
    try:
        got = core._hash_file(core._safe(d, step["output"]))
    except core.ClaimError:
        return False
    return got == want


def audit(d: str) -> dict:
    """Deep re-earning: identity first, then every gate re-run cold and
    sandboxed, classified earned (`reproduced`) or carried/broken
    (`mismatch`/`failed`/`timeout`/`environment`) (spec/verification.md)."""
    try:
        parsed = recipe.load_recipe(d)
    except core.ClaimError as e:
        return {"ok": False, "verdict": str(e), "gates": []}

    v = seal.verify(d)
    if not v["ok"]:
        return {"ok": False, "verdict": "mismatch", "root": v["root"], "gates": []}

    missing = run.preflight(parsed)
    if missing:
        return {"ok": False, "verdict": "environment", "root": v["root"],
                "gates": [], "missing": missing}

    sealed_parts = _sealed_parts(d)
    gates_out = []
    ok = True
    for step in recipe.gates(parsed):
        res = run.run_gate(step["run"], d, parsed)
        status = res["status"]
        if status == "ok":
            status = "reproduced" if _compare_pin(d, step, sealed_parts) else "mismatch"
        if status not in ("ok", "reproduced"):
            ok = False
        gates_out.append({"output": step["output"], "status": status,
                           "quarantine": res["quarantine"]})
    return {"ok": ok, "root": v["root"], "gates": gates_out}


# -- rebuild: materialize, produce, earn the gates, seal --------------------

def rebuild(d: str, producer: str, into: str, produce_from=None, input_from=None,
            guidance: bool = True, producer_env=None) -> dict:
    """Regrow `d`'s generated outputs in a fresh room at `into` via
    `producer`, earn the gates there, and seal the result
    (spec/kernel-api.md). Returns `{"root", "name", "quarantine"}`."""
    parsed = recipe.load_recipe(d)
    missing = run.preflight(parsed)
    if missing:
        raise core.ClaimError(f"missing environment requirements: {missing}")

    _materialize(d, into, parsed)
    _produce(into, parsed, producer, guidance=guidance, producer_env=producer_env)
    usage = _read_usage(into)

    entry = {"kind": "rebuild"}
    if usage:
        entry.update(usage)
    run.ledger(into, entry)

    quarantine = None
    for step in recipe.gates(parsed):
        res = run.run_gate(step["run"], into, parsed)
        quarantine = res["quarantine"]
        if res["status"] != "ok":
            raise core.ClaimError(f"gate {step['output']!r} did not pass: {res['status']}")

    manifest = seal.seal(into)
    return {"root": manifest["root"], "name": manifest["name"], "quarantine": quarantine}
