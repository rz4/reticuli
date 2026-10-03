"""The crosscheck/audit/mutation engine: everything above identity and gate
execution that the kernel-core check exercises through `reticuli.kernel`.

This module owns:

- `verify`/`phase` -- a stricter `verify` than `seal.verify` (it raises when
  the claim's own bytes cannot even be read -- an escaping or missing
  pinned input, a corrupt recipe -- rather than silently reporting
  `ok: False`), and `phase`, which layers signature verification
  (authorized + proven = signed) on top of it.
- `rebuild` -- regrow a claim's generated outputs via an external producer
  (a shell command), threading inputs, reusing component-supplied bytes,
  and refusing a producer that rewrites the claim's own pinned bytes.
- `audit` -- re-earn a claim's verdict cold, gate by gate, including the
  declared-environment furnish step and substituted-bytes judging
  (`produce_from`).
- `gate_deciders`/`vacuous_gates` -- name the workspace scripts a gate's
  `run` line actually executes, and which gates decide by no claimed byte
  at all.
- `mutation_score` -- deterministic mutants of a claim's generated Python,
  drawn from the root, re-audited to measure a kill rate.
- `crosscheck`/`record_proof` -- the three-machine test over directories
  and/or frozen records, and freezing a passing crosscheck onto M1's
  manifest as residue.
- `record_canonical`/`record_digest`/`record_validate`/`record_read`/
  `record_signer` -- the record reader (spec/record.md), versions 1 and 2
  (version 2 carries the claim's declared obligations).
- `independence` -- a directory's declared producer (vendor/model/blind),
  read from its own ledger.
- `sandbox`/`run_gate` -- the gate-running primitive every verb above uses;
  unlike `run.run_gate`, the value handed to a wrapped gate under
  `RETICULI_JAILED` is the sandbox backend itself, not a bare flag, so a
  gate that is itself a claim runner can tell which jail it is inside.

Stdlib only; no network.
"""
import ast
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

from . import build as _build
from . import core
from . import identity
from . import recipe
from . import run
from . import seal as _seal
from .core import ClaimError

# ===========================================================================
# Gate running: the one place a gate is actually executed. Differs from
# run.run_gate in exactly one way -- a REAL sandbox tells the wrapped
# process which backend it is inside (the value, not a flag), so a gate
# that is itself a claim runner can inherit instead of nesting.
# ===========================================================================


# ===========================================================================
# load_recipe: recipe.load_recipe, plus the one validation it does not
# cover -- a declared `[claim] envelope`'s shape (spec/claim-format.md:
# "the envelope compares the redo to the claim's own commitment", so a
# damaged table must refuse at parse, not silently mean nothing).
# ===========================================================================


def _validate_claim_extras(parsed: dict) -> None:
    claim = parsed.get("claim", {})
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("[claim] envelope must be a non-empty table")
        for unit, ceiling in envelope.items():
            if unit not in core.COST_UNITS:
                raise ClaimError(f"[claim] envelope carries unknown unit {unit!r}")
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                raise ClaimError("[claim] envelope ceiling must be a positive number")


def _fold_environment_input(doc: dict) -> dict:
    """A declared `[claim] environment` file is automatically a pinned
    input (spec/claim-format.md: "named ... automatically a pinned
    input"): fold it into the parsed recipe's own `inputs` list (when the
    claim uses the plain list form, not a format-2 manifest) so identity
    hashes it like any other declared input, with no change to
    `identity.py` itself.
    """
    claim = doc.get("claim", {})
    env_file = claim.get("environment")
    if env_file is None or claim.get("inputs_manifest") is not None:
        return doc
    inputs = list(claim.get("inputs", []))
    if env_file in inputs:
        return doc
    inputs.append(env_file)
    claim = dict(claim)
    claim["inputs"] = inputs
    doc = dict(doc)
    doc["claim"] = claim
    return doc


def load_recipe(d: str) -> dict:
    """`recipe.load_recipe`, plus validating a declared `[claim] envelope`
    and folding a declared `[claim] environment` into the pinned inputs.
    """
    parsed = recipe.load_recipe(d)
    _validate_claim_extras(parsed)
    return _fold_environment_input(parsed)


def sandbox(cmd=None, room=None):
    """A functional probe of the host sandbox backend. `cmd`/`room` are
    accepted for the caller's convenience (a probe command and the room it
    would run in) but do not change what is probed; the backend is a
    property of the host and the current jail state alone.
    """
    backend = run.sandbox_backend()
    return (cmd, backend)


def run_gate(cmd: str, d: str, parsed) -> dict:
    """Run one gate command: scrubbed environment, sandboxed, bounded by
    the claim's declared timeout (capped by the host ceiling). Returns
    `status` (`ok`/`failed`/`timeout`), `quarantine` (the backend actually
    applied), `returncode`, and the captured output (`stdout`; `stderr` is
    always empty since the underlying run combines both streams).

    THE SENDING HALF of the sandbox contract: when a real backend is
    applied (not already inherited), the wrapped process is told the
    backend's name under `RETICULI_JAILED` -- not a bare flag -- so a gate
    that is itself a claim runner can tell which jail it is inside and
    inherit rather than nest.
    """
    timeout = run.gate_timeout(parsed) if parsed is not None else core.GATE_TIMEOUT
    backend = run.sandbox_backend()
    scratch_root = os.path.join(d, core.STORE, "scratch")
    os.makedirs(scratch_root, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="run-", dir=scratch_root)
    try:
        jailed_value = backend if backend in ("seatbelt", "bubblewrap") else \
            os.environ.get(core._JAILED, "")
        extra = {"HOME": scratch, "TMPDIR": scratch}
        if jailed_value:
            extra[core._JAILED] = jailed_value
        env = run._scrub_env(extra)
        argv = run._sandbox_argv(backend, [core._SHELL, "-c", cmd], d, scratch)
        result = run._run(argv, cwd=d, env=env, timeout=timeout)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend, "returncode": result["returncode"],
            "stdout": result["stdout"], "stderr": ""}


# ===========================================================================
# verify / phase: a stricter identity check than seal.verify, and the
# authorized-and-proven phase computation.
# ===========================================================================


def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare it with the
    sealed manifest. Unlike `seal.verify`, this raises `ClaimError` when
    the claim's own bytes cannot even be read for recomputation (an
    escaping or missing pinned input) rather than quietly reporting
    `ok: False` -- the distinction `phase` depends on to refuse a claim
    its own verify cannot complete, rather than answering it stale.
    """
    try:
        manifest = _seal.read_manifest(d)
    except ClaimError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise ClaimError(f"malformed manifest in {d!r}: {exc}") from exc
    try:
        parsed = load_recipe(d)
    except ClaimError:
        raise
    try:
        recomputed = identity.root(parsed, d)
    except ClaimError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise ClaimError(f"cannot verify {d!r}: {exc}") from exc
    ok = recomputed == manifest["root"]
    return {"ok": ok, "name": manifest.get("name"), "root": manifest["root"],
            "recomputed": recomputed}


def _signers_principals(allowed_signers: str) -> list:
    """The principal (identity) named by each line of an `allowed_signers`
    file -- `ssh-keygen -Y verify -I <principal>` must be told which
    principal to check a signature against, so finding out *who* signed
    something means trying each principal the anchor knows until one
    verifies.
    """
    principals = []
    try:
        with open(allowed_signers, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                token = line.split(None, 1)[0]
                if token not in principals:
                    principals.append(token)
    except OSError:
        pass
    return principals


def _is_signed(d: str, vr: dict) -> bool:
    """Whether `d` carries a trusted, coherent authorization: a signature
    under `core.SIGN_NAMESPACE`, verified against `RETICULI_SIGNERS`, over
    a statement that binds (by digest) a stored packet file whose root and
    build digest match the claim's CURRENT bytes and whose proof is
    non-empty. Any missing piece -- no anchor, no signing directory, no
    verifying signature, a swapped packet, drifted bytes, an absent proof
    -- is simply not signed; the first candidate that satisfies every
    check wins.
    """
    allowed_signers = os.environ.get(core._ENV_SIGNERS)
    if not allowed_signers or not os.path.isfile(allowed_signers):
        return False
    sign_dir = os.path.join(d, core.SIGN_DIR)
    if not os.path.isdir(sign_dir) or not shutil.which("ssh-keygen"):
        return False

    current_digest = identity.build_digest(d)
    for fname in sorted(os.listdir(sign_dir)):
        if not fname.endswith(".sign.json"):
            continue
        prefix = fname[: -len(".sign.json")]
        stmt_path = os.path.join(sign_dir, fname)
        sig_path = stmt_path + ".sig"
        packet_path = os.path.join(sign_dir, prefix + ".packet.json")
        if not (os.path.isfile(sig_path) and os.path.isfile(packet_path)):
            continue
        with open(stmt_path, "rb") as f:
            stmt_bytes = f.read()
        try:
            stmt = json.loads(stmt_bytes)
        except json.JSONDecodeError:
            continue
        verified = False
        for principal in _signers_principals(allowed_signers):
            try:
                done = subprocess.run(
                    ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", principal,
                     "-n", core.SIGN_NAMESPACE, "-s", sig_path],
                    input=stmt_bytes, capture_output=True, timeout=10, check=False,
                )
            except OSError:
                continue
            if done.returncode == 0:
                verified = True
                break
        if not verified:
            continue
        with open(packet_path, "rb") as f:
            packet_bytes = f.read()
        if hashlib.sha256(packet_bytes).hexdigest() != stmt.get("packet_digest"):
            continue
        try:
            packet = json.loads(packet_bytes)
        except json.JSONDecodeError:
            continue
        if packet.get("root") != vr["root"]:
            continue
        if packet.get("build_digest") != current_digest:
            continue
        if not packet.get("proof"):
            continue
        return True
    return False


def phase(d: str) -> str:
    """`draft` (no manifest yet) / `sealed` (verified, with or without a
    recorded proof) / `signed` (verified, a recorded proof, AND a trusted
    signature over a coherent, undrifted packet). Refuses -- never
    "sealed" -- a claim whose own verify cannot complete.
    """
    load_recipe(d)
    manifest_path = os.path.join(d, core.MANIFEST)
    if not os.path.isfile(manifest_path):
        return "draft"
    vr = verify(d)
    if not vr["ok"]:
        raise ClaimError(f"claim at {d!r} does not verify")
    manifest = _seal.read_manifest(d)
    if not manifest.get("proof"):
        return "sealed"
    if _is_signed(d, vr):
        return "signed"
    return "sealed"


# ===========================================================================
# seal: a lenient parse that does not refuse a GENERATED step's output for
# merely being a symlink. recipe.load_recipe validates every step's output
# through core._safe, which refuses any symlink -- correct for a pinned
# output (its bytes enter the root) but too strict for a generated one
# (seal never hashes it; identity._parts already skips it). Confinement on
# a generated output is enforced where it is actually touched -- audit's
# copy into a room -- not at parse time, so a generated-symlink claim
# still seals and only refuses when audited.
# ===========================================================================


def _load_recipe_lenient(d: str) -> dict:
    """Exactly `recipe.load_recipe`'s validation, except a GENERATED step's
    output is not passed through the symlink/escape check `_safe` applies
    to every other declared path.
    """
    path = recipe.recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    except OSError as exc:
        raise ClaimError(f"cannot read recipe {path!r}: {exc}") from exc

    if not isinstance(doc, dict):
        raise ClaimError(f"malformed recipe {path!r}: not a table")

    claim = doc.get("claim", doc.get("record"))
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} needs a [claim] table")
    doc["claim"] = claim

    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError(f"recipe {path!r}: [[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("each step must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise ClaimError(f"step kind must be one of {sorted(core.KINDS)}: {kind!r}")
        output = step.get("output")
        if not isinstance(output, str) or output == "":
            raise ClaimError("every step needs a non-empty string output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"gate step {output!r} needs a run command")
        default_class = "generated" if kind == "produce" else "pinned"
        if step.get("class", default_class) == "generated":
            continue
        core._safe(d, output)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        names = recipe._read_input_manifest(d, manifest)
        for n in names:
            core._safe(d, n)
        doc["_manifest_inputs"] = names
    else:
        inputs = claim.get("inputs", [])
        if not isinstance(inputs, list) or not all(isinstance(i, str) for i in inputs):
            raise ClaimError("[claim] inputs must be a list of strings")
        for n in inputs:
            core._safe(d, n)

    _validate_claim_extras(doc)
    return _fold_environment_input(doc)


def seal(d: str) -> dict:
    """Freeze `d` into a claim: compute the root from its pinned bytes
    (`_load_recipe_lenient`, `identity._parts`) and write
    `.reticuli/manifest.json`.
    """
    parsed = _load_recipe_lenient(d)
    parts = identity._parts(parsed, d)
    root_hex = hashlib.sha256(identity._canonical_json(parts).encode("utf-8")).hexdigest()
    manifest = {"name": parsed["claim"]["name"], "root": root_hex, "parts": parts}
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    return manifest


# ===========================================================================
# Room building, shared by rebuild and audit: copying pinned inputs
# (threading a fresh one where asked), and writing the room's own recipe --
# guidance-stripped at format 3, so a gate that reads its own recipe finds
# exactly what the root names (spec/identity.md, "Format 3").
# ===========================================================================

_GUIDANCE_LINE = re.compile(r'(?m)^[ \t]*(?:guidance|request)[ \t]*=.*\n?')


def _strip_guidance_text(raw_text: str, fmt: int) -> str:
    """The room's own recipe text: unchanged below format 3; at format 3
    and above, every standalone `guidance = ...` / `request = ...` line is
    removed, so a gate cannot read a hint the root itself does not carry.
    """
    if fmt < 3:
        return raw_text
    return _GUIDANCE_LINE.sub("", raw_text)


def _write_room_recipe(d: str, parsed: dict, into: str) -> str:
    """Write the room's recipe (same filename as `d`'s own), guidance
    stripped per format. Returns the filename written.
    """
    fmt = parsed.get("claim", {}).get("format", 1)
    name = os.path.basename(recipe.recipe_path(d))
    with open(recipe.recipe_path(d), "r", encoding="utf-8") as f:
        raw = f.read()
    with open(os.path.join(into, name), "w", encoding="utf-8") as f:
        f.write(_strip_guidance_text(raw, fmt))
    return name


def _materialize_inputs(d: str, parsed: dict, into: str, input_from=None) -> None:
    """Copy every pinned input into `into`, substituting a threaded
    replacement (`input_from`) where the caller names one (spec: a
    rebuilt component's fresh input, snapshotted after it lands).
    """
    input_from = input_from or {}
    for name in recipe._inputs(parsed):
        override = input_from.get(name)
        if override is not None:
            dest = os.path.join(into, name)
            os.makedirs(os.path.dirname(dest) or into, exist_ok=True)
            shutil.copy2(override, dest)
        else:
            core._copy_into(d, into, [name])


# ===========================================================================
# rebuild: regrow a claim's generated outputs via an external producer.
# ===========================================================================


def rebuild(d: str, producer: str, into: str, produce_from=None, input_from=None) -> dict:
    """Regrow `d`'s generated outputs into `into` by running `producer`
    (a shell command) with `cwd=into`, then run every gate until each
    passes, then seal. Refuses: a host missing a declared `requires`; a
    non-empty target; a producer that rewrites the recipe or a pinned
    input after materialization; a gate that fails, times out, or is
    denied by the sandbox. `produce_from` supplies a named generated
    output's bytes directly (ledgered as reuse, component-supplied code);
    `input_from` threads a fresh pinned input's bytes in place of `d`'s own.
    """
    parsed = load_recipe(d)
    missing = run.preflight(parsed)
    if missing:
        raise ClaimError(f"environment: missing requirement(s) {missing}")

    into_abs = os.path.abspath(into)
    if os.path.isdir(into_abs):
        if os.listdir(into_abs):
            raise ClaimError(f"rebuild target {into!r} already holds bytes")
    else:
        os.makedirs(into_abs)

    produce_from = produce_from or {}

    _materialize_inputs(d, parsed, into_abs, input_from)
    recipe_name = _write_room_recipe(d, parsed, into_abs)

    snapshot = {"recipe": core._hash_file(os.path.join(into_abs, recipe_name))}
    for name in recipe._inputs(parsed):
        snapshot["input:" + name] = core._hash_file(os.path.join(into_abs, name))

    remaining = []
    for step in recipe.produces(parsed):
        if step.get("class", "generated") != "generated" or "from" in step:
            continue
        output = step["output"]
        if output in produce_from:
            dest = core._safe(into_abs, output)
            os.makedirs(os.path.dirname(dest) or into_abs, exist_ok=True)
            shutil.copy2(produce_from[output], dest)
            run.ledger(into_abs, {"event": "reuse", "output": output})
        else:
            remaining.append(step)

    if remaining:
        env = dict(os.environ)
        usage_path = os.path.join(into_abs, core.STORE, "producer-usage.json")
        os.makedirs(os.path.dirname(usage_path), exist_ok=True)
        env[core._ENV_USAGE] = usage_path
        env[core._ENV_CLAIM] = into_abs
        if len(remaining) == 1:
            env[core._ENV_OUTPUT] = os.path.join(into_abs, remaining[0]["output"])
            guidance = _build._step_guidance(remaining[0])
            if guidance is not None:
                env[core._ENV_REQUEST] = guidance
        env[core._ENV_OUTPUTS] = json.dumps(
            [os.path.join(into_abs, s["output"]) for s in remaining])

        start = time.monotonic()
        try:
            result = subprocess.run(
                producer, shell=True, cwd=into_abs, env=env,
                capture_output=True, timeout=core.PRODUCER_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaimError(f"producer timed out: {exc}") from exc
        elapsed = time.monotonic() - start

        usage = {}
        if os.path.isfile(usage_path):
            with open(usage_path, "r", encoding="utf-8") as f:
                payload = f.read()
            usage = _build._read_usage(payload)
            os.remove(usage_path)
        usage.pop("seconds", None)
        ledger_entry = {"event": "oracle", "calls": 1, "seconds": elapsed}
        ledger_entry.update(usage)
        run.ledger(into_abs, ledger_entry)

        if result.returncode != 0:
            raise ClaimError(
                "producer failed: " + result.stderr.decode("utf-8", "replace")[-500:])

    vendor = os.environ.get(core._ENV_VENDOR)
    model = os.environ.get(core._ENV_MODEL)
    if vendor or model:
        run.ledger(into_abs, {"event": "producer", "vendor": vendor or "unknown",
                              "model": model or "unknown", "blind": True})

    if core._hash_file(os.path.join(into_abs, recipe_name)) != snapshot["recipe"]:
        raise ClaimError("the producer rewrote the recipe; refusing to seal")
    for name in recipe._inputs(parsed):
        if core._hash_file(os.path.join(into_abs, name)) != snapshot["input:" + name]:
            raise ClaimError(f"the producer rewrote pinned input {name!r}; refusing to seal")

    logged_env = False
    for step in recipe.gates(parsed):
        outcome = run_gate(step["run"], into_abs, parsed)
        run.ledger(into_abs, {"event": "gate", "output": step["output"],
                              "quarantine": outcome["quarantine"]})
        if not logged_env:
            run.ledger(into_abs, {"event": "environment", "python": sys.version,
                                  "quarantine": outcome["quarantine"]})
            logged_env = True
        if outcome["status"] != "ok":
            raise ClaimError(f"gate {step['output']!r} did not pass: {outcome['status']}")

    return seal(into_abs)


# ===========================================================================
# audit: re-earn a claim's verdict cold.
# ===========================================================================


def audit(d: str, produce_from=None) -> dict:
    """Re-earn `d`'s verdict cold (spec/verification.md, "Audit: earned vs.
    carried"). Identity must hold against the sealed manifest first (a
    corrupt manifest or recipe raises; a mismatched-but-readable claim
    returns `ok: False` without raising). The environment contract
    (`requires`, then a declared `environment` furnished into a private
    venv) must be met, or every gate reports `environment` without
    running. Each gate then runs fresh in a room built from the claim's
    pinned inputs and its present (or `produce_from`-substituted) generated
    bytes, and the bytes it pins must reproduce exactly what the claim
    already holds.
    """
    vr = verify(d)
    if not vr["ok"]:
        return {"ok": False, "verdict": "mismatch", "gates": []}

    parsed = load_recipe(d)
    produce_from = produce_from or {}

    missing = run.preflight(parsed)
    if missing:
        gates_list = [{"output": s["output"], "status": "environment", "quarantine": None}
                      for s in recipe.gates(parsed)]
        return {"ok": False, "environment": missing, "gates": gates_list}

    venv_bin = None
    env_file = parsed.get("claim", {}).get("environment")
    if env_file is not None:
        # run.furnish resolves the environment file's own relative wheel
        # paths against the process cwd, not `d`; furnish from inside the
        # claim directory so a relocatable, relative requirements file
        # resolves correctly regardless of the caller's own cwd.
        cwd_before = os.getcwd()
        os.chdir(d)
        try:
            venv_bin = run.furnish(d, parsed)
        except ClaimError:
            gates_list = [{"output": s["output"], "status": "environment", "quarantine": None}
                          for s in recipe.gates(parsed)]
            return {"ok": False, "environment": [], "gates": gates_list}
        finally:
            os.chdir(cwd_before)

    room = tempfile.mkdtemp(prefix="audit-")
    try:
        _materialize_inputs(d, parsed, room)
        _write_room_recipe(d, parsed, room)
        for step in recipe.produces(parsed):
            if step.get("class", "generated") != "generated":
                continue
            output = step["output"]
            if output in produce_from:
                dest = core._safe(room, output)
                os.makedirs(os.path.dirname(dest) or room, exist_ok=True)
                shutil.copy2(produce_from[output], dest)
            else:
                src = core._safe(d, output)
                if os.path.isfile(src):
                    core._copy_into(d, room, [output])

        old_path = os.environ.get("PATH")
        if venv_bin:
            os.environ["PATH"] = venv_bin + os.pathsep + (old_path or "")
        try:
            gate_results = []
            ok = True
            for step in recipe.gates(parsed):
                outcome = run_gate(step["run"], room, parsed)
                output = step["output"]
                if outcome["status"] == "ok":
                    status = "ok" if _build._compare_pin(room, d, output) else "mismatch"
                else:
                    status = outcome["status"]
                if status != "ok":
                    ok = False
                gate_results.append({"output": output, "status": status,
                                     "quarantine": outcome["quarantine"]})
            return {"ok": ok, "gates": gate_results}
        finally:
            if venv_bin:
                if old_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = old_path
    finally:
        shutil.rmtree(room, ignore_errors=True)


# ===========================================================================
# gate_deciders / vacuous_gates: which workspace scripts a gate's `run`
# line actually executes, and which gates decide by no claimed byte at all.
# ===========================================================================

_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2',
                           'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh',
                           'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})

_OPERATOR_PATTERN = re.compile(
    "(" + "|".join(re.escape(op) for op in sorted(_OPERATORS, key=len, reverse=True)) + ")"
)


def _split_commands(run_string: str) -> list:
    """Split a gate's `run` line into its individual commands, cut at the
    shell operators that separate them (`&&`, `||`, `;`, `|`, `&`, a bare
    newline).
    """
    commands, current = [], []
    for part in _OPERATOR_PATTERN.split(run_string):
        if part in _OPERATORS:
            if current:
                commands.append("".join(current))
            current = []
        else:
            current.append(part)
    if current:
        commands.append("".join(current))
    return [c.strip() for c in commands if c.strip()]


def _decider_name(token: str) -> str:
    """A script token's decider name: its basename, extension stripped."""
    name = os.path.basename(token)
    root, _ext = os.path.splitext(name)
    return root if root else name


def gate_deciders(run_string: str) -> list:
    """The workspace scripts a gate's `run` line executes: the first
    non-flag argument to a recognized interpreter (`_INTERPRETERS`), or a
    bare path-like executable (`./check`, `bin/run`). A command that is
    neither -- a plain shell utility like `grep`, `printf`, `test` -- names
    no decider: such a gate is decided by the recipe's own pinned run text,
    not by a workspace file.
    """
    deciders = []
    for cmd in _split_commands(run_string):
        tokens = cmd.split()
        if not tokens:
            continue
        head = tokens[0]
        head_name = os.path.basename(head)
        rest = tokens[1:]
        if head_name in _INTERPRETERS:
            i = 0
            found = None
            while i < len(rest):
                tok = rest[i]
                if tok in _SKIP_VALUE:
                    i += 2
                    continue
                if tok.startswith("-"):
                    i += 1
                    continue
                found = tok
                break
            if found:
                deciders.append(_decider_name(found))
        elif "/" in head or head.startswith("."):
            deciders.append(_decider_name(head))
    return deciders


def vacuous_gates(parsed: dict) -> list:
    """The outputs of every gate step whose every decider is a generated
    (regrowable) output -- the verdict depends on no claimed byte, so any
    implementation that prints the passing bytes satisfies it. A gate
    whose `run` line names no decider at all (`grep`, `printf`, ...) is
    decided by the recipe's own pinned text instead, and is never vacuous.
    """
    generated = {os.path.splitext(o)[0] for o in recipe.generated_outputs(parsed)}
    vac = []
    for step in recipe.gates(parsed):
        deciders = gate_deciders(step["run"])
        if deciders and all(dec in generated for dec in deciders):
            vac.append(step["output"])
    return vac


# ===========================================================================
# MUTATION ENGINE: deterministic mutants of a claim's generated Python,
# drawn from the root, re-audited to measure a kill rate.
# ===========================================================================

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_ARITHMETIC = ('+', '-', '*', '/', '//', '%', '**')

_OP_KIND = {
    ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/',
    ast.FloorDiv: '//', ast.Mod: '%', ast.Pow: '**',
    ast.Gt: '>', ast.Lt: '<', ast.GtE: '>=', ast.LtE: '<=',
    ast.Eq: '==', ast.NotEq: '!=',
}
_OP_ALTS = {
    '+': ('-',), '-': ('+',), '*': ('/',), '/': ('*',),
    '//': ('/',), '%': ('*',), '**': ('*',),
    '>': ('<', '>='), '<': ('>', '<='),
    '>=': ('<=', '>'), '<=': ('>=', '<'),
    '==': ('!=',), '!=': ('==',),
}
_WORD_ALTS = {'and': 'or', 'or': 'and', 'True': 'False', 'False': 'True'}
_STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')


def _node_span(node) -> tuple:
    """A node's (start line, start col, end line, end col), 1-based lines."""
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def _span_text(lines: list, span: tuple) -> str:
    """The exact source text a span covers, `lines` being `splitlines()`
    (no line terminators) of the source it was computed against.
    """
    l1, c1, l2, c2 = span
    if l1 == l2:
        return lines[l1 - 1][c1:c2]
    parts = [lines[l1 - 1][c1:]]
    parts.extend(lines[l1:l2 - 1])
    parts.append(lines[l2 - 1][:c2])
    return "\n".join(parts)


def _splice(text: str, span: tuple, replacement: str) -> str:
    """`text` with the bytes covered by `span` replaced by `replacement`."""
    lines = text.splitlines(keepends=True)
    l1, c1, l2, c2 = span
    before = "".join(lines[: l1 - 1]) + lines[l1 - 1][:c1]
    after = lines[l2 - 1][c2:] + "".join(lines[l2:])
    return before + replacement + after


def _edit(text: str, span: tuple, replacement: str) -> str:
    """Apply one mutation: `_splice` under its proper name for the seam."""
    return _splice(text, span, replacement)


def _docstring_spans(tree) -> list:
    """Every docstring's span (the first statement of a module, function,
    or class body, when it is a bare string constant) -- excluded from
    mutation, since a docstring is prose, not behavior.
    """
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                spans.append(_node_span(body[0].value))
    return spans


def _named(node) -> str:
    """A short, deterministic label for an AST node: its kind and position."""
    return f"{type(node).__name__}@{node.lineno}:{node.col_offset}"


def _label(kind: str, span: tuple, before: str, after: str) -> str:
    """A human-readable label for one mutation: what changed, and where."""
    return f"{kind}:{span[0]}: {before!r} -> {after!r}"


def _in_spans(span: tuple, spans: list) -> bool:
    return any(span[0] >= s[0] and span[2] <= s[2] for s in spans)


def _token_mutants(src: str, tree, doc_spans: list) -> list:
    """Mutants from swapping a single arithmetic or comparison operator for
    an alternative (`_OP_ALTS`), skipping anything inside a docstring span.
    Each candidate is `(mutant_source, label)`.
    """
    lines = src.splitlines()
    mutants = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in _OP_KIND:
            op_sym = _OP_KIND[type(node.op)]
            if op_sym not in _ARITHMETIC:
                continue
            left_end = (node.left.end_lineno, node.left.end_col_offset)
            right_start = (node.right.lineno, node.right.col_offset)
            if left_end[0] != right_start[0]:
                continue
            span = (left_end[0], left_end[1], right_start[0], right_start[1])
            if _in_spans(span, doc_spans):
                continue
            text = lines[left_end[0] - 1][left_end[1]:right_start[1]]
            for alt in _OP_ALTS.get(op_sym, ()):
                if op_sym not in text:
                    continue
                replacement = text.replace(op_sym, alt, 1)
                mutants.append((_splice(src, span, replacement),
                                _label("op", span, op_sym, alt)))
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 \
                and type(node.ops[0]) in _OP_KIND:
            op_sym = _OP_KIND[type(node.ops[0])]
            left_end = (node.left.end_lineno, node.left.end_col_offset)
            right_start = (node.comparators[0].lineno, node.comparators[0].col_offset)
            if left_end[0] != right_start[0]:
                continue
            span = (left_end[0], left_end[1], right_start[0], right_start[1])
            if _in_spans(span, doc_spans):
                continue
            text = lines[left_end[0] - 1][left_end[1]:right_start[1]]
            for alt in _OP_ALTS.get(op_sym, ()):
                if op_sym not in text:
                    continue
                replacement = text.replace(op_sym, alt, 1)
                mutants.append((_splice(src, span, replacement),
                                _label("cmp", span, op_sym, alt)))
    return mutants


def _structural_mutants(src: str, tree, doc_spans: list) -> list:
    """Mutants from a structural change: negating an `if`'s test. Each
    candidate is `(mutant_source, label)`.
    """
    mutants = []
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            span = _node_span(node.test)
            if _in_spans(span, doc_spans):
                continue
            text = _span_text(lines, span)
            replacement = f"not ({text})"
            mutants.append((_splice(src, span, replacement),
                            _label("if", span, text, replacement)))
    return mutants


def _draw_order(n: int, root_hex: str) -> list:
    """A deterministic permutation of `range(n)`, seeded from the root, so
    the mutant draw is reproducible yet depends on no incidental ordering.
    """
    order = list(range(n))
    random.Random(root_hex).shuffle(order)
    return order


def _mutant_order(candidates: list, root_hex: str) -> list:
    """`candidates` reordered deterministically from the root."""
    order = _draw_order(len(candidates), root_hex)
    return [candidates[i] for i in order]


def _mutants(src: str, root_hex: str) -> list:
    """Every mutant of `src` (token and structural), in a deterministic
    order drawn from the root. Each candidate is `(mutant_source, label)`.
    """
    tree = ast.parse(src)
    doc_spans = _docstring_spans(tree)
    candidates = _token_mutants(src, tree, doc_spans) + _structural_mutants(src, tree, doc_spans)
    return _mutant_order(candidates, root_hex)


def _machine(d: str, parsed: dict, target: str, mutant_src: str) -> bool:
    """Build a room with `target`'s bytes replaced by `mutant_src` and run
    every gate. Returns `True` if the mutant is KILLED (some gate fails),
    `False` if it SURVIVES (every gate still passes).
    """
    room = tempfile.mkdtemp(prefix="mut-")
    try:
        _materialize_inputs(d, parsed, room)
        for step in recipe.produces(parsed):
            out = step["output"]
            if out == target:
                with open(os.path.join(room, out), "w", encoding="utf-8") as f:
                    f.write(mutant_src)
            else:
                src_path = core._safe(d, out)
                if os.path.isfile(src_path):
                    core._copy_into(d, room, [out])
        for step in recipe.gates(parsed):
            outcome = run_gate(step["run"], room, parsed)
            if outcome["status"] != "ok":
                return True
        return False
    finally:
        shutil.rmtree(room, ignore_errors=True)


def mutation_score(d: str, max_mutants: int = core.MUTANT_CEILING) -> dict:
    """Deterministic mutants of `d`'s generated Python, drawn from the
    root, re-audited: the kill rate is residue (`core.MUTATION_RESIDUE`),
    never touching identity. When the claim declares a `mutation_floor`,
    the result also carries `ok` (rate >= floor).
    """
    parsed = load_recipe(d)
    vr = verify(d)
    root_hex = vr["root"]
    floor = parsed.get("claim", {}).get("mutation_floor")

    targets = sorted(
        s["output"] for s in recipe.produces(parsed)
        if s.get("class", "generated") == "generated" and s["output"].endswith(".py")
        and os.path.isfile(core._safe(d, s["output"]))
    )

    all_mutants = []
    for target in targets:
        with open(core._safe(d, target), "r", encoding="utf-8") as f:
            src = f.read()
        for mutant_src, label in _mutants(src, root_hex):
            all_mutants.append((target, mutant_src, f"{target}:{label}"))

    all_mutants = _mutant_order(all_mutants, root_hex)[:max_mutants]

    killed = 0
    survivors = []
    for target, mutant_src, label in all_mutants:
        if _machine(d, parsed, target, mutant_src):
            killed += 1
        else:
            survivors.append(label)

    total = len(all_mutants)
    rate = (killed / total) if total else 1.0
    result = {"mutants": total, "rate": rate, "survivors": survivors}
    if floor is not None:
        result["ok"] = rate >= floor
    core._write_json(os.path.join(d, core.MUTATION_RESIDUE), result)
    return result


# ===========================================================================
# RECORDS (spec/record.md): the frozen leg. Versions 1 and 2 -- version 2
# adds the required `claim` member, carrying the recipe's declared
# obligations so a crosscheck over records enforces what one over
# directories would.
# ===========================================================================

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 2

_RECORD_MEMBERS_V1 = frozenset({
    "record", "name", "root", "build_digest", "gates",
    "cost", "producer", "environment", "when", "tool",
})
_RECORD_MEMBERS_V2 = _RECORD_MEMBERS_V1 | {"claim"}
_RECORD_REQUIRED_V1 = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_REQUIRED_V2 = _RECORD_REQUIRED_V1 | {"claim"}
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_COST = frozenset({"usd", "tokens", "calls", "seconds"})
_RECORD_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def record_canonical(doc: dict) -> bytes:
    """A record's canonical bytes: the identity serialization verbatim --
    sorted keys, default separators, non-ASCII escaped.
    """
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """The sha256 hex of a record's canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_validate(doc) -> None:
    """Refuse, in band, anything that is not a well-formed record this
    kernel understands -- not an object, an unknown or missing member for
    its version, a newer version than `RECORD_FORMAT`, `claim` at version
    1, a missing `claim` at version 2, a bad hex digest, an out-of-
    vocabulary status/sandbox, or a malformed `cost`/`producer`/`claim`
    block. The member set is closed per version.
    """
    if not isinstance(doc, dict):
        raise ClaimError("a record must be a JSON object")

    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ClaimError("record: 'record' must be a positive integer")
    if version > RECORD_FORMAT:
        raise ClaimError(
            f"record format {version} is newer than this kernel understands "
            f"(format {RECORD_FORMAT})"
        )

    members = _RECORD_MEMBERS_V2 if version >= 2 else _RECORD_MEMBERS_V1
    required = _RECORD_REQUIRED_V2 if version >= 2 else _RECORD_REQUIRED_V1

    extra = set(doc) - members
    if extra:
        raise ClaimError(f"record carries unknown member(s): {sorted(extra)}")
    missing = required - set(doc)
    if missing:
        raise ClaimError(f"record is missing required member(s): {sorted(missing)}")
    if version < 2 and "claim" in doc:
        raise ClaimError("record: 'claim' is not valid at version 1")

    if not isinstance(doc.get("name"), str):
        raise ClaimError("record: 'name' must be a string")

    for key in ("root", "build_digest"):
        value = doc.get(key)
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            raise ClaimError(f"record: {key!r} must be 64 lowercase hex characters")

    when = doc.get("when")
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise ClaimError("record: 'when' must be 'YYYY-MM-DDTHH:MM:SSZ'")

    environment = doc.get("environment")
    if not isinstance(environment, dict) or set(environment) != _RECORD_ENVIRONMENT:
        raise ClaimError("record: 'environment' must carry exactly platform/machine/runtime")
    for value in environment.values():
        if not isinstance(value, str):
            raise ClaimError("record: environment values must be strings")

    gates = doc.get("gates")
    if not isinstance(gates, list):
        raise ClaimError("record: 'gates' must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != _RECORD_GATE:
            raise ClaimError("record: each gate entry must carry exactly output/status/sandbox")
        if not isinstance(gate.get("output"), str):
            raise ClaimError("record: gate 'output' must be a string")
        if gate.get("status") not in _RECORD_STATUSES:
            raise ClaimError(f"record: gate status must be one of {sorted(_RECORD_STATUSES)}")
        if gate.get("sandbox") not in _RECORD_SANDBOXES:
            raise ClaimError(f"record: gate sandbox must be one of {sorted(_RECORD_SANDBOXES)}")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict):
            raise ClaimError("record: 'cost' must be an object")
        extra_cost = set(cost) - _RECORD_COST
        if extra_cost:
            raise ClaimError(f"record: cost carries unknown unit(s): {sorted(extra_cost)}")
        for value in cost.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ClaimError("record: cost values must be non-negative numbers")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict):
            raise ClaimError("record: 'producer' must be an object")
        extra_producer = set(producer) - _RECORD_PRODUCER
        if extra_producer:
            raise ClaimError(f"record: producer carries unknown member(s): {sorted(extra_producer)}")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise ClaimError(f"record: producer {key!r} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise ClaimError("record: producer 'blind' must be a boolean")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("record: 'tool' must be a string")

    if "claim" in doc:
        claim = doc["claim"]
        if not isinstance(claim, dict):
            raise ClaimError("record: 'claim' must be an object")
        extra_claim = set(claim) - _RECORD_CLAIM_KEYS
        if extra_claim:
            raise ClaimError(f"record: claim carries unknown obligation(s): {sorted(extra_claim)}")
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                value = claim[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    raise ClaimError(f"record: claim {key!r} must be a non-negative number")
        if "envelope" in claim:
            envelope = claim["envelope"]
            if not isinstance(envelope, dict) or not envelope:
                raise ClaimError("record: claim envelope must be a non-empty object")
            for unit, ceiling in envelope.items():
                if unit not in core.COST_UNITS:
                    raise ClaimError(f"record: claim envelope carries unknown unit {unit!r}")
                if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                    raise ClaimError("record: claim envelope ceiling must be a positive number")


def record_read(path: str) -> dict:
    """Read a record file and validate it. The file must be its own
    canonical bytes -- a reformatted (pretty-printed, re-keyed) copy
    refuses, since a record IS its canonical bytes or it is not a record
    (that is what a signature covers).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise ClaimError(f"cannot read record {path!r}: {exc}") from exc
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaimError(f"malformed record {path!r}: {exc}") from exc
    record_validate(doc)
    if text.encode("utf-8") != record_canonical(doc):
        raise ClaimError(f"record {path!r} is not its own canonical bytes")
    return doc


def record_signer(path: str, allowed_signers: str):
    """The identity that signed the record at `path`, verified against
    `allowed_signers` in `RECORD_NAMESPACE`. `None` on any failure: no
    detached signature, no usable `ssh-keygen`, a malformed record, or a
    signature that does not verify.
    """
    signature_path = path + ".sig"
    if not (os.path.isfile(path) and os.path.isfile(signature_path)):
        return None
    if not shutil.which("ssh-keygen"):
        return None
    try:
        doc = record_read(path)
    except ClaimError:
        return None
    data = record_canonical(doc)
    for principal in _signers_principals(allowed_signers):
        try:
            done = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", principal,
                 "-n", RECORD_NAMESPACE, "-s", signature_path],
                input=data, capture_output=True, timeout=10, check=False,
            )
        except OSError:
            continue
        if done.returncode == 0:
            return principal
    return None


# ===========================================================================
# independence: a directory's declared producer, read from its own ledger.
# ===========================================================================


def independence(d: str):
    """The most recent declared producer on `d`'s ledger (vendor/model/
    blind), or `None` when nothing was declared -- an observation, never
    proof (content cannot establish blindness).
    """
    for event in reversed(run.ledger_events(d)):
        if event.get("event") == "producer":
            return {"vendor": event.get("vendor"), "model": event.get("model"),
                    "blind": event.get("blind")}
    return None


def _independence_string(producer) -> str:
    if not producer or not producer.get("vendor"):
        return "unestablished (no producer declared for M3)"
    tag = "blind workspace" if producer.get("blind") else "not a blind workspace"
    return f"declared: {producer['vendor']}/{producer['model']}, {tag} (not proven)"


# ===========================================================================
# crosscheck / record_proof: the three-machine test, over directories
# and/or frozen records, and freezing a passing one onto M1's manifest.
# ===========================================================================


def _leg_info(path: str) -> dict:
    """Everything a crosscheck leg needs, read uniformly whether `path` is
    a claim directory (a live execution) or a record file (a frozen,
    relayed statement).
    """
    if os.path.isdir(path):
        vr = verify(path)
        if not vr["ok"]:
            raise ClaimError(f"leg {path!r} does not verify")
        aud = audit(path)
        parsed = load_recipe(path)
        return {
            "root": vr["root"],
            "build_digest": identity.build_digest(path),
            "ok": bool(aud.get("ok")),
            "cost": run.cost(path),
            "declared": parsed.get("claim", {}),
            "declared_known": True,
            "producer": independence(path),
        }
    doc = record_read(path)
    declared_known = doc.get("record", 1) >= 2
    return {
        "root": doc["root"],
        "build_digest": doc["build_digest"],
        "ok": all(g["status"] == "ok" for g in doc["gates"]),
        "cost": doc.get("cost"),
        "declared": doc.get("claim", {}) if declared_known else {},
        "declared_known": declared_known,
        "producer": doc.get("producer"),
    }


def _cost_comparable(cost1, cost3, tol: float):
    """Whether C3/C1 lands within `[1/tol, tol]` in the strongest unit both
    ledgers measured (`core.COST_LADDER`); `None` when they share none.
    """
    if not cost1 or not cost3:
        return None
    for unit in core.COST_LADDER:
        v1, v3 = cost1.get(unit), cost3.get(unit)
        if v1 is not None and v3 is not None:
            if v1 == 0:
                return None
            ratio = v3 / v1
            return (1.0 / tol) <= ratio <= tol
    return None


def crosscheck(m1: str, m2: str, m3: str, mutants=None) -> dict:
    """The three-machine test (spec/verification.md). Each of `m1`/`m2`/
    `m3` is a claim directory or a record file; the two transports mix
    freely. `mutants`, when given, caps the mutant draw used to re-earn a
    declared `mutation_floor` on M3.

    A hard condition (one root, byte reuse of M1 by M2, every verdict
    re-earned, and every condition the claim itself declares) must hold to
    accept, and rejects on false; a declared condition this run did not
    measure is neither true nor false, and the verdict is `incomplete` --
    which can never accept.
    """
    reals = set()
    for p in (m1, m2, m3):
        reals.add(os.path.realpath(p) if os.path.isdir(p) else os.path.abspath(p))
    if len(reals) < 3:
        raise ClaimError("crosscheck requires three distinct machines")

    L1, L2, L3 = _leg_info(m1), _leg_info(m2), _leg_info(m3)
    roots = {"M1": L1["root"], "M2": L2["root"], "M3": L3["root"]}
    equivalence = len(set(roots.values())) == 1
    reuse = L1["build_digest"] == L2["build_digest"]
    audited = {"M1": L1["ok"], "M2": L2["ok"], "M3": L3["ok"]}

    rejected, incomplete = [], []
    if not equivalence:
        rejected.append("root")
    if not reuse:
        rejected.append("reuse")
    if not all(audited.values()):
        rejected.append("audit")

    declared_known = L1["declared_known"]
    declared = L1["declared"] if declared_known else {}
    tol = declared.get("tolerance", core.TOLERANCE)
    comparable = _cost_comparable(L1["cost"], L3["cost"], tol)

    envelope_report = {}
    mscore = None

    if not declared_known:
        incomplete.append("declared conditions (version-1 record)")
    else:
        if "tolerance" in declared:
            if comparable is None:
                incomplete.append("cost band")
            elif comparable is False:
                rejected.append("cost band")

        envelope = declared.get("envelope") or {}
        for unit, ceiling in envelope.items():
            measured = (L3["cost"] or {}).get(unit)
            if measured is None:
                envelope_report[unit] = {"within": None}
                incomplete.append(f"envelope {unit}")
            else:
                within = measured <= ceiling
                envelope_report[unit] = {"within": within}
                if not within:
                    rejected.append(f"envelope {unit}")

        floor = declared.get("mutation_floor")
        if floor is not None:
            if mutants is None:
                incomplete.append("mutation_floor")
            elif os.path.isdir(m3):
                mscore = mutation_score(m3, max_mutants=mutants)
                if not mscore.get("ok", True):
                    rejected.append("mutation_floor")
            else:
                incomplete.append("mutation_floor")

    if rejected:
        verdict = "reject"
    elif incomplete:
        verdict = "incomplete"
    else:
        verdict = "accept"

    return {
        "satisfied": verdict == "accept",
        "verdict": verdict,
        "rejected": rejected,
        "incomplete": incomplete,
        "equivalence": equivalence,
        "reuse": reuse,
        "audited": audited,
        "roots": roots,
        "cost": {"comparable": comparable, "envelope": envelope_report},
        "independence": _independence_string(L3["producer"]),
        "mutation_score": mscore,
    }


def record_proof(m1: str, m2: str, m3: str) -> dict:
    """Run the crosscheck and, on an accept, freeze the proof onto M1's
    manifest as residue. M1 must be a claim directory (a proof is residue
    on its manifest); a record leg among M2/M3 must carry a signature that
    verifies against `RETICULI_SIGNERS`, or the proof refuses outright --
    directory legs are the caller's own executions and need no anchor,
    but a record leg is a relayed statement whose only provenance is its
    signature.
    """
    if not os.path.isdir(m1):
        raise ClaimError("a proof can only be recorded on a directory (M1 must be a claim)")

    allowed_signers = os.environ.get(core._ENV_SIGNERS)
    trail = []
    for leg in (m2, m3):
        if os.path.isdir(leg):
            continue
        if not allowed_signers or not os.path.isfile(allowed_signers):
            raise ClaimError(f"record leg {leg!r} is unanchored: no trusted signers")
        signer = record_signer(leg, allowed_signers)
        if signer is None:
            raise ClaimError(f"record leg {leg!r} does not verify against the trust anchor")
        doc = record_read(leg)
        trail.append({"digest": record_digest(doc), "signer": signer})

    result = crosscheck(m1, m2, m3)
    proof_recorded = result["verdict"] == "accept"
    if proof_recorded:
        manifest = _seal.read_manifest(m1)
        manifest["proof"] = {"kind": "crosscheck", "roots": result["roots"], "records": trail}
        core._write_json(os.path.join(m1, core.MANIFEST), manifest)
    return {"proof_recorded": proof_recorded, "crosscheck": result}
