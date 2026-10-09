"""Kernel-build: re-earning a verdict (`audit`) and regrowing one (`rebuild`).

`audit(d)` trusts nothing already on disk: it recomputes identity, deletes
each gate's pinned output, re-runs the gate cold, and requires the fresh
bytes to match what was sealed -- a verdict is *earned* only this way, never
*carried* from a past run (`spec/verification.md`). `rebuild(d, producer,
into)` materializes a judging room at `into` (the recipe -- byte-for-byte
below format 3, the guidance-stripped preimage as TOML at format 3+ -- plus
every pinned input), runs the producer there to regrow the generated
outputs, then runs every gate and seals on success (`spec/claim-format.md`,
`spec/identity.md`).

The producer runs with the caller's own environment -- network reachable,
HOME intact -- because it is the caller's oracle, not a jailed gate; the
gates it must still pass run exactly as `run.run_gate` always runs them
(scrubbed, sandboxed, bounded).

Stdlib only.
"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time

from . import core, identity, recipe, run, seal
from .core import ClaimError


# -- a minimal TOML writer, for the room's format-3+ preimage recipe --------

def _toml_value(v) -> str:
    """One recipe value as TOML source -- scalars, lists of scalars, and
    flat dicts (inline tables) only, which is everything a recipe carries."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(
            f"{k} = {_toml_value(v2)}" for k, v2 in v.items()) + " }"
    raise ClaimError(f"recipe value has no TOML form: {v!r}")


def _toml_dumps(doc: dict) -> str:
    """Serialize a parsed recipe (`[claim]` plus zero or more `[[step]]`)
    back to TOML text that `tomllib` parses to an equal structure."""
    lines = ["[claim]"]
    for k, v in doc.get("claim", {}).items():
        lines.append(f"{k} = {_toml_value(v)}")
    for step in doc.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for k, v in step.items():
            lines.append(f"{k} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


# -- building the judging room ----------------------------------------------

def _materialize(d: str, into: str, parsed: dict) -> None:
    """Build the judging room at `into`: the recipe plus every pinned input.

    Below format 3 the recipe enters byte-for-byte, exactly as sealed --
    the room's criteria ARE the sealed file. At format 3+ the room receives
    the guidance-stripped preimage (`spec/identity.md`), serialized fresh as
    TOML under the same filename, so a gate that reads its own recipe reads
    only what the root names.
    """
    os.makedirs(into, exist_ok=True)
    src_path = recipe.recipe_path(d)
    basename = os.path.basename(src_path)
    fmt = identity._claim_format(parsed)
    if fmt < 3:
        shutil.copy2(src_path, os.path.join(into, basename))
    else:
        preimage = identity._preimage_recipe(parsed)
        with open(os.path.join(into, basename), "w", encoding="utf-8") as f:
            f.write(_toml_dumps(preimage))
    core._copy_into(d, into, recipe._inputs(d, parsed))


# -- running the producer -----------------------------------------------

def _step_guidance(step: dict):
    """A produce step's hint for a rebuilder, under either spelling
    (`guidance`, or the older `request`); `None` if it carries neither."""
    for key in core.GUIDANCE_KEYS:
        value = step.get(key)
        if value is not None:
            return value
    return None


def _produce(room: str, producer: str, parsed: dict, *,
              guidance: bool = True, producer_env: dict = None) -> None:
    """Run the producer in `room`, regrowing its generated outputs.

    The producer is the caller's oracle: it runs with the caller's own
    environment (network reachable, HOME intact), unsandboxed -- the gates
    its output must still pass are what stays jailed. It is named the
    output(s) to write (`RETICULI_OUTPUT`, absolute; `RETICULI_OUTPUTS`,
    every declared one, as JSON) and, unless withheld, the authoring
    guidance for each produce step (`RETICULI_REQUEST`).
    """
    outputs = recipe.generated_outputs(parsed)
    os.makedirs(os.path.join(room, core.STORE), exist_ok=True)

    env = dict(os.environ)
    if outputs:
        env[core._ENV_OUTPUT] = os.path.join(os.path.realpath(room), outputs[0])
        env[core._ENV_OUTPUTS] = json.dumps(outputs)
    env[core._ENV_USAGE] = os.path.join(os.path.realpath(room), core.USAGE)
    if guidance:
        hints = [h for h in (_step_guidance(s) for s in recipe.produces(parsed))
                  if h is not None]
        if hints:
            env[core._ENV_REQUEST] = "\n".join(hints)
    if producer_env:
        env.update(producer_env)

    result = subprocess.run([core._SHELL, "-c", producer], cwd=room, env=env,
                             timeout=core.PRODUCER_TIMEOUT, capture_output=True)
    if result.returncode != 0:
        raise ClaimError(
            f"producer failed (exit {result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace')}")


def _read_usage(room: str) -> dict:
    """Cost the producer self-reported, if any (`spec/kernel-api.md`).

    Only `usd`/`tokens`/`calls` are ever accepted from this source --
    `seconds` is the kernel's own measurement, never a producer's claim.
    """
    path = os.path.join(room, core.USAGE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(doc, dict):
        return {}
    return {k: v for k, v in doc.items()
            if k in ("usd", "tokens", "calls")
            and isinstance(v, (int, float)) and not isinstance(v, bool)}


# -- authorization: optional, and vacuous without a trust anchor -----------

def _ssh_verify(namespace: str, allowed_signers: str, signer_id: str,
                 signature: bytes, data: bytes) -> bool:
    """Verify a detached `ssh-keygen -Y` signature over `data`."""
    if not allowed_signers or not os.path.isfile(allowed_signers):
        return False
    fd, sig_path = tempfile.mkstemp(suffix=".sig")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(signature)
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", signer_id, "-n", namespace, "-s", sig_path],
            input=data, capture_output=True, timeout=10)
    except OSError:
        return False
    finally:
        try:
            os.remove(sig_path)
        except OSError:
            pass
    return result.returncode == 0


def _authorized(d: str, root: str) -> bool:
    """Whether a producer is authorized to realize `root` on this host.

    Optional: with no `RETICULI_SIGNERS` on the host, every producer is
    authorized -- no fixture in this boundary ever sets it. Where it is
    set, a `SIGN_NAMESPACE` signature over the root, from a key named in
    that file, must be recorded at `<d>/<SIGN_DIR>/<root>.sign.json`
    (`{"signer": ..., "signature": <base64>}`).
    """
    allowed_signers = os.environ.get(core._ENV_SIGNERS)
    if not allowed_signers:
        return True
    sign_path = os.path.join(d, core.SIGN_DIR, f"{root}.sign.json")
    if not os.path.isfile(sign_path):
        return False
    try:
        with open(sign_path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        signature = base64.b64decode(doc["signature"])
        signer = doc["signer"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False
    return _ssh_verify(core.SIGN_NAMESPACE, allowed_signers, signer,
                        signature, root.encode("utf-8"))


# -- rebuild: materialize, produce, judge, seal ------------------------------

def rebuild(d: str, producer: str, into: str, *, produce_from: str = None,
            input_from: str = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    """Regrow `d`'s generated outputs at a fresh room, until its gates pass.

    `into` must not already exist -- a partial room is a refusal, never a
    silent resumption. On success the room is sealed and its root returned;
    on a failing gate, `root` is `None` and `status`/`output` name why.
    """
    parsed = recipe.load_recipe(d)
    if os.path.exists(into):
        raise ClaimError(f"rebuild target already exists: {into!r}")
    _materialize(d, into, parsed)

    if produce_from is not None:
        for output in recipe.generated_outputs(parsed):
            src = core._safe(produce_from, output)
            dst = core._safe(into, output)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    else:
        start = time.monotonic()
        _produce(into, producer, parsed, guidance=guidance,
                  producer_env=producer_env)
        entry = _read_usage(into)
        entry["seconds"] = time.monotonic() - start
        run.ledger(into, entry)

    quarantine = None
    for step in recipe.gates(parsed):
        result = run.run_gate(step["run"], into, parsed)
        quarantine = result["quarantine"]
        if result["status"] != "ok":
            return {"root": None, "status": result["status"],
                    "quarantine": quarantine, "output": step["output"]}

    manifest = seal.seal(into)
    if not _authorized(into, manifest["root"]):
        raise ClaimError(f"producer not authorized for root {manifest['root']!r}")
    return {"root": manifest["root"], "quarantine": quarantine}


# -- audit: re-earn every gate, cold, trusting nothing carried --------------

def _compare_pin(d: str, output: str, manifest: dict) -> bool:
    """Whether `output`'s present bytes match what the manifest pinned."""
    expected = manifest.get("parts", {}).get(f"pinned:{output}")
    if expected is None:
        return True
    path = core._safe(d, output)
    if not os.path.isfile(path):
        return False
    return core._hash_file(path) == expected


def audit(d: str, **kwargs) -> dict:
    """Deep re-earning (`spec/verification.md`): identity, then every gate,
    cold -- a stored "passed" is never trusted.

    Identity is checked first (`seal.verify`): a claim whose present bytes
    do not recompute to its sealed root gets no gate run at all. Each gate's
    pinned output is then deleted and the gate re-run; a clean exit whose
    fresh bytes do not match what was sealed is a `mismatch`, not an `ok`.
    """
    parsed = recipe.load_recipe(d)
    v = seal.verify(d)
    if not v["ok"]:
        return {"ok": False, "verdict": "mismatch", "gates": []}

    missing = run.preflight(parsed)
    if missing:
        return {"ok": False, "verdict": "environment", "gates": [],
                "missing": missing}

    furnished = run.furnish(d, parsed)
    if furnished["status"] != "ok":
        return {"ok": False, "verdict": "environment", "gates": [],
                "reason": furnished.get("reason")}

    manifest = seal.read_manifest(d)
    gate_rows = []
    ok = True
    for step in recipe.gates(parsed):
        output = step["output"]
        path = core._safe(d, output)
        if os.path.isfile(path):
            os.remove(path)
        result = run.run_gate(step["run"], d, parsed)
        status = result["status"]
        if status == "ok" and not _compare_pin(d, output, manifest):
            status = "mismatch"
        gate_rows.append({"output": output, "status": status,
                           "quarantine": result["quarantine"]})
        if status != "ok":
            ok = False

    return {"ok": ok, "verdict": "accept" if ok else "reject", "gates": gate_rows}
