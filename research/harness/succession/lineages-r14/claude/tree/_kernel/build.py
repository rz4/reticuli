"""Rebuilding and re-earning a claim (spec/verification.md, spec/claim-format.md).

`rebuild` materializes a fresh room from a claim's pinned inputs and recipe,
drives a producer to regrow each declared `generated` output, then runs the
gates in that room and seals it if they pass. `audit` trusts nothing already
on record: it recomputes identity, materializes a fresh room from the bytes
present, and re-runs every gate cold, distinguishing a verdict *earned* now
from one merely *carried* from the past.

A room is handed the recipe exactly as `spec/identity.md` says a reader must:
byte-for-byte at format < 3, and -- because guidance must never decide
acceptance -- the guidance-stripped preimage, re-serialized as TOML under the
canonical recipe name, at format >= 3. A producer never sees the room's
sandbox: it is the caller's oracle, so it inherits the caller's environment,
network reachability, and HOME, with only the kernel's own `RETICULI_*`
variables added on top.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time

from . import core
from . import identity as _identity
from . import recipe as _recipe
from . import run as _run_mod
from . import seal as _seal
from .core import ClaimError


# -- the room a producer or a gate materializes into ----------------------

def _toml_escape(text: str) -> str:
    out = []
    for ch in text:
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
    return "".join(out)


def _toml_value(value) -> str:
    """A Python value as a TOML literal; enough of the grammar for a
    recipe's shape (strings, integers, floats, bools, lists, inline tables)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return '"' + _toml_escape(value) + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items()) + " }"
    raise ClaimError(f"cannot write {value!r} as TOML")


def _dump_toml(doc: dict) -> str:
    """`doc` (a recipe-shaped dict: tables and a `[[step]]` array) as TOML
    text that a conforming TOML reader parses back to an equal structure."""
    lines = []
    for key, value in doc.items():
        if key == "step":
            continue
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for k, v in value.items():
                lines.append(f"{k} = {_toml_value(v)}")
            lines.append("")
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    for step in doc.get("step", []):
        lines.append("[[step]]")
        for k, v in step.items():
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _materialize(d: str, parsed: dict, room: str, include_generated: bool = False,
                  inputs_from: str = None) -> None:
    """Build a fresh room for `parsed` at `room`: the recipe exactly as a
    reader must receive it, every pinned input, and -- when
    `include_generated` -- every generated output present in `d` right now.
    A step's `from` bytes are always carried in: they are a deterministic
    copy, never something a producer earns."""
    os.makedirs(room, exist_ok=True)
    source = inputs_from or d

    if _identity._claim_format(parsed) >= 3:
        text = _dump_toml(_identity._preimage_recipe(parsed))
        with open(os.path.join(room, core.RECIPE), "w", encoding="utf-8") as f:
            f.write(text)
    else:
        src_path = _recipe.recipe_path(d)
        shutil.copy2(src_path, os.path.join(room, os.path.basename(src_path)))

    core._copy_into(source, room, _recipe._inputs(d, parsed))

    for step in _recipe._steps(parsed):
        if step.get("kind") != "produce":
            continue
        output = step.get("output")
        source_name = step.get("from")
        if source_name:
            full_src = core._safe(source, source_name)
            if os.path.isfile(full_src):
                target = core._safe(room, output)
                os.makedirs(os.path.dirname(target) or room, exist_ok=True)
                shutil.copy2(full_src, target)
            continue
        if include_generated:
            full = core._safe(d, output)
            if os.path.isfile(full):
                target = core._safe(room, output)
                os.makedirs(os.path.dirname(target) or room, exist_ok=True)
                shutil.copy2(full, target)


def _step_guidance(step: dict):
    """A produce step's hint for a rebuilder, under either spelling
    (`guidance`, older `request`); `None` if it carries neither."""
    for key in core.GUIDANCE_KEYS:
        value = step.get(key)
        if isinstance(value, str):
            return value
    return None


# -- the producer: the caller's oracle, confined only by the room's name --

def _read_usage(path: str) -> dict:
    """A producer's self-reported cost, if it wrote one; `{}` for anything
    missing, malformed, or carrying a value the ledger cannot trust."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(doc, dict):
        return {}
    usage = {}
    for key in ("usd", "tokens", "calls"):
        value = doc.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            usage[key] = value
    return usage


def _produce(command: str, room: str, outputs, step: dict, parsed: dict,
             guidance: bool = True, producer_env: dict = None) -> dict:
    """Run `command` once in `room` to earn `step`'s output. The producer
    inherits the caller's whole environment -- network reachability, HOME,
    credentials included -- because it is the caller's oracle and its
    output faces the jailed gate regardless; only the kernel's own
    `RETICULI_*` variables are added on top."""
    env = dict(os.environ)
    env[core._ENV_OUTPUT] = os.path.join(os.path.realpath(room), step.get("output"))
    env[core._ENV_OUTPUTS] = json.dumps(list(outputs))
    if guidance:
        hint = _step_guidance(step)
        if hint is not None:
            env[core._ENV_REQUEST] = hint
    name = parsed.get("claim", {}).get("name") if isinstance(parsed, dict) else None
    if isinstance(name, str):
        env[core._ENV_CLAIM] = name
    env[core._ENV_USAGE] = os.path.join(os.path.realpath(room), core.USAGE)
    if producer_env:
        env.update(producer_env)

    start = time.time()
    try:
        done = subprocess.run(command, shell=True, cwd=room, env=env,
                               capture_output=True, text=True,
                               timeout=core.PRODUCER_TIMEOUT, check=False)
        return {"returncode": done.returncode, "stdout": done.stdout,
                "stderr": done.stderr, "seconds": time.time() - start,
                "usage": _read_usage(env[core._ENV_USAGE])}
    except subprocess.TimeoutExpired as e:
        return {"returncode": None, "stdout": e.stdout or "", "stderr": e.stderr or "",
                "seconds": time.time() - start, "usage": {}}


# -- authorization: an optional gate in front of the producer --------------

def _ssh_verify(data: bytes, signature_path: str, namespace: str,
                 signers_file: str, identity: str = None) -> bool:
    """Does `signature_path` verify over `data` in `namespace`, against a
    key in `signers_file` (ssh-keygen's allowed-signers format)?"""
    if not signers_file or not os.path.isfile(signers_file):
        return False
    if not os.path.isfile(signature_path):
        return False
    if shutil.which("ssh-keygen") is None:
        return False
    argv = ["ssh-keygen", "-Y", "verify", "-f", signers_file,
            "-n", namespace, "-s", signature_path, "-I", identity or "producer"]
    try:
        done = subprocess.run(argv, input=data, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def _authorized(d: str, parsed: dict) -> bool:
    """Whether a producer run for `d` is authorized to proceed. With no
    `RETICULI_SIGNERS` configured, no authorization is required -- the
    ordinary, host-local case. Configured, a producer needs a mint
    statement in the claim's sign directory verifying against it."""
    signers_file = os.environ.get(core._ENV_SIGNERS)
    if not signers_file:
        return True
    sign_dir = os.path.join(d, core.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return False
    for entry in sorted(os.listdir(sign_dir)):
        if not entry.endswith(".json"):
            continue
        path = os.path.join(sign_dir, entry)
        sig_path = path[: -len(".json")] + ".sig"
        if not os.path.isfile(sig_path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        if _ssh_verify(data, sig_path, core.SIGN_NAMESPACE, signers_file):
            return True
    return False


# -- rebuild: regrow, judge, seal -------------------------------------------

def rebuild(d: str, producer: str, into: str, produce_from: str = None,
            input_from: str = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    """Regrow `d`'s generated outputs into `into` by running `producer`
    once per declared generated output, then run the gates there and seal
    on a pass (spec/verification.md: `realize`, carried as `rebuild`)."""
    parsed = _recipe.load_recipe(d)

    if os.path.exists(into):
        if os.listdir(into):
            raise ClaimError(f"refuses to rebuild into a non-empty directory: {into!r}")
    else:
        os.makedirs(into)

    if not _authorized(d, parsed):
        raise ClaimError("producer is not authorized for this claim")

    _materialize(d, parsed, into, include_generated=False, inputs_from=input_from)

    generated_steps = [s for s in _recipe.produces(parsed)
                        if s.get("class", "generated") == "generated" and not s.get("from")]
    all_outputs = [s["output"] for s in generated_steps]

    for step in generated_steps:
        output = step["output"]
        if produce_from:
            carried = os.path.join(produce_from, output)
            if os.path.isfile(carried):
                target = core._safe(into, output)
                os.makedirs(os.path.dirname(target) or into, exist_ok=True)
                shutil.copy2(carried, target)
                continue

        result = _produce(producer, into, all_outputs, step, parsed, guidance, producer_env)
        entry = {"kind": "produce", "output": output, "seconds": result["seconds"]}
        entry.update(result.get("usage") or {})
        entry.update(core._judging_host())
        _run_mod.ledger(into, entry)
        if result["returncode"] != 0:
            return {"ok": False, "root": None, "verdict": "failed", "gates": [],
                    "error": result["stderr"]}

    gate_results = []
    quarantine = None
    ok = True
    for step in _recipe.gates(parsed):
        res = _run_mod.run_gate(step["run"], into, parsed)
        quarantine = res["quarantine"]
        gate_results.append({"output": step["output"], "status": res["status"],
                              "quarantine": quarantine})
        if res["status"] != "ok":
            ok = False

    if not ok:
        return {"ok": False, "root": None, "verdict": "failed",
                "gates": gate_results, "quarantine": quarantine}

    manifest = _seal.seal(into)
    return {"ok": True, "root": manifest["root"], "verdict": "ok",
            "gates": gate_results, "quarantine": quarantine}


# -- audit: trust nothing already on record ---------------------------------

def _compare_pin(d: str, room: str, output: str) -> bool:
    """Do the bytes of `output` in `room` match those in `d`? Used to tell
    a freshly earned verdict (`reproduced`) from a broken one (`mismatch`)."""
    try:
        return core._hash_file(core._safe(d, output)) == core._hash_file(core._safe(room, output))
    except (OSError, ClaimError):
        return False


def audit(d: str, shallow: bool = False) -> dict:
    """Re-earn every gate of `d`, cold: recompute identity, materialize a
    fresh room from the bytes present (no verdict carried in), re-run every
    gate sandboxed, and require every pinned byte to reproduce
    (spec/verification.md: the only verb that re-earns a verdict)."""
    try:
        parsed = _recipe.load_recipe(d)
    except ClaimError as e:
        return {"ok": False, "verdict": "error", "gates": [], "error": str(e)}

    verified = _seal.verify(d)
    if not verified["ok"]:
        return {"ok": False, "verdict": "mismatch", "gates": [], "root": verified["root"]}

    missing = _run_mod.preflight(parsed)
    if missing:
        return {"ok": False, "verdict": "environment", "gates": [],
                "root": verified["root"], "missing": missing}

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        _materialize(d, parsed, room, include_generated=True)
        gate_results = []
        earned = True
        for step in _recipe.gates(parsed):
            res = _run_mod.run_gate(step["run"], room, parsed)
            status = res["status"]
            if status == "ok" and step.get("class", "pinned") != "generated":
                status = "reproduced" if _compare_pin(d, room, step["output"]) else "mismatch"
            gate_results.append({"output": step["output"], "status": status,
                                  "quarantine": res["quarantine"]})
            if status not in ("ok", "reproduced"):
                earned = False
        return {"ok": earned, "verdict": "earned" if earned else "broken",
                "gates": gate_results, "root": verified["root"]}
    finally:
        shutil.rmtree(room, ignore_errors=True)
