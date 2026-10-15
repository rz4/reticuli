"""The kernel's higher verbs: rebuild, audit, the three-machine test, signing,
mutation scoring, and the proof that freezes a crosscheck onto a manifest.

Built on top of `core`/`identity`/`recipe`/`run`/`seal` (the primitives) and
`attest` (the record reader). `build.py` ships a first cut at `rebuild`/
`audit`; this module supersedes both with the behavior the kernel check
actually pins -- a scrubbed, hand-built producer environment (the inherited
one leaks secrets), a ledger written to the room rather than the source, a
snapshot that refuses a producer who rewrites the question, and a `verify`
that raises on a structurally broken claim rather than swallowing it into a
hash mismatch. Only the small, genuinely reusable pieces of `build.py` (TOML
rendering, PATH-prefixing, pin comparison, ssh verification) are imported.

Stdlib only, never the network.
"""
import ast
import hashlib
import io
import json
import math
import os
import platform
import random
import re
import shutil
import subprocess
import time
import tokenize
import tomllib

from . import attest, build, core, identity, recipe, run
from . import seal as _seal_mod
from .core import ClaimError

# ============================================================================
# seam constants -- pinned exactly by checks/kernel_check.py's `_seam()`
# ============================================================================

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2',
                           'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh',
                           'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})

_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<=', '<': '>=', '>=': '<', '<=': '>', '==': '!=', '!=': '==',
            '+': '-', '-': '+', '*': '+', '/': '*', '//': '*', '%': '*'}
_OP_KIND = {op: ('cmp' if op in _COMPARISON else 'arith') for op in _OP_ALTS}
_STRING_LITERAL = re.compile(r"""(?P<q>['"]).*?(?<!\\)(?P=q)""", re.DOTALL)
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and',
              'break': 'continue', 'continue': 'break'}

# -- derived, non-seam helpers -----------------------------------------------

_OP_SPLIT = re.compile(
    "|".join(re.escape(op) for op in sorted(_OPERATORS, key=len, reverse=True))
)
_REDIR_PREFIXES = (">", "<")
_OBLIGATION_KEYS = ("tolerance", "envelope", "mutation_floor")
_DEFAULT_TOLERANCE = 2.0
_UNKNOWN = object()  # sentinel: "cannot say what was declared" (a v1 record as M1)


# ============================================================================
# recipe loading -- supersedes recipe.load_recipe: that validator confines
# EVERY step's output unconditionally, including `generated` ones, so it
# refuses to even PARSE a claim whose generated output happens to be a
# symlink -- but confinement over generated outputs is audit's job (a
# generated output is never hashed; only COPYING one through a boundary,
# which audit does, can leak bytes). Parsing must stay lenient there so
# `seal`/`verify` succeed on such a claim and `audit` is what catches it.
# Also adds the envelope/tolerance/mutation_floor validation recipe.py
# does not itself pin.
# ============================================================================


def load_recipe(d: str) -> dict:
    path = recipe.recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e
    _validate_recipe(d, parsed)
    return parsed


def _validate_recipe(d: str, parsed) -> None:
    if not isinstance(parsed, dict):
        raise ClaimError("a recipe must be a table")
    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError("a recipe needs a [claim] table")
    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")
    fmt = claim.get("format", 1)
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ClaimError("[claim] inputs must be a list of strings")
    for p in inputs:
        core._safe(d, p)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        core._safe(d, manifest)
    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("the [[step]] array must be a list")
    for step in steps:
        _validate_step(d, step)
    _validate_obligations(claim)


def _validate_step(d: str, step) -> None:
    if not isinstance(step, dict):
        raise ClaimError("a step must be a table")
    kind = step.get("kind")
    if kind not in core.KINDS:
        raise ClaimError(f"unknown step kind: {kind!r}")
    output = step.get("output")
    if not isinstance(output, str) or not output:
        raise ClaimError("a step needs a string output")
    cls = step.get("class", recipe._default_class(step))
    if cls != "generated":
        core._safe(d, output)        # pinned/validated: confined at parse time
    if kind == "gate":
        run_cmd = step.get("run")
        if not isinstance(run_cmd, str) or not run_cmd:
            raise ClaimError("a gate step needs a run command")


def _validate_obligations(claim: dict) -> None:
    if "envelope" in claim:
        env = claim["envelope"]
        if not isinstance(env, dict) or not env:
            raise ClaimError("[claim] envelope must be a non-empty table")
        for unit, ceiling in env.items():
            if unit not in core.COST_UNITS:
                raise ClaimError(f"[claim] envelope has an unknown unit: {unit!r}")
            if not isinstance(ceiling, (int, float)) or isinstance(ceiling, bool) or ceiling <= 0:
                raise ClaimError(f"[claim] envelope.{unit} must be a positive number")
    if "tolerance" in claim:
        t = claim["tolerance"]
        if not isinstance(t, (int, float)) or isinstance(t, bool) or t <= 0:
            raise ClaimError("[claim] tolerance must be a positive number")
    if "mutation_floor" in claim:
        mf = claim["mutation_floor"]
        if not isinstance(mf, (int, float)) or isinstance(mf, bool) or not (0 <= mf <= 1):
            raise ClaimError("[claim] mutation_floor must be a number in [0, 1]")


# ============================================================================
# verify / phase -- identity, and the signed/sealed/draft ladder
# ============================================================================


def read_manifest(d: str) -> dict:
    """`seal.read_manifest`, but refuses non-UTF-8 manifest bytes in band
    too -- `seal.py`'s own reader lets a `UnicodeDecodeError` escape raw."""
    try:
        return _seal_mod.read_manifest(d)
    except UnicodeDecodeError as e:
        raise ClaimError(f"malformed manifest: {e}") from e


def _parts(parsed: dict, d: str) -> dict:
    """`identity._parts`, plus `[claim] environment` as an automatic
    pinned input -- a dependency version decides what "passes" means, so
    it belongs in the root like any other fixture, but `identity.py`'s
    own preimage builder only walks `[claim] inputs`."""
    parts = identity._parts(parsed, d)
    env_file = parsed.get("claim", {}).get("environment")
    if env_file:
        parts[f"input:{env_file}"] = identity._hash_declared(d, env_file)
    return parts


def seal(d: str) -> dict:
    """Freeze a workspace into a claim -- supersedes `seal.seal`, which
    internally calls the over-strict `recipe.load_recipe` and would refuse
    to seal a claim whose *generated* output happens to be a symlink."""
    parsed = load_recipe(d)
    name = parsed["claim"]["name"]
    parts = _parts(parsed, d)
    manifest = {"name": name, "root": _seal_mod._root_from_parts(parts), "parts": parts}
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    return manifest


def verify(d: str) -> dict:
    """Recompute the root from the bytes present; raise on a structurally
    broken claim (an escaping or missing declared path), never on an
    ordinary content edit, which simply recomputes a different root."""
    manifest = read_manifest(d)
    parsed = load_recipe(d)
    parts = _parts(parsed, d)                   # raises ClaimError: missing/escaping
    recomputed = _seal_mod._root_from_parts(parts)
    ok = recomputed == manifest["root"]
    result = {"ok": ok, "name": manifest["name"], "root": manifest["root"],
              "recomputed": recomputed}
    if not ok:
        result["changed"] = _seal_mod._changed_parts(manifest.get("parts", {}), parts)
    return result


def _signed_packets(d: str):
    mdir = os.path.join(d, core.SIGN_DIR)
    if not os.path.isdir(mdir):
        return
    for fn in sorted(os.listdir(mdir)):
        if not fn.endswith(".sign.json"):
            continue
        packet_fn = fn[: -len(".sign.json")] + ".packet.json"
        stmt_path = os.path.join(mdir, fn)
        packet_path = os.path.join(mdir, packet_fn)
        if os.path.isfile(packet_path):
            yield stmt_path, packet_path


def _is_signed(d: str) -> bool:
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):
        return False
    try:
        live_root = verify(d)["root"]
        live_bd = identity.build_digest(d)
    except ClaimError:
        return False
    for stmt_path, packet_path in _signed_packets(d):
        try:
            with open(stmt_path, "r", encoding="utf-8") as f:
                stmt = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        principal = stmt.get("identity")
        if not isinstance(principal, str):
            continue
        with open(stmt_path, "rb") as f:
            stmt_bytes = f.read()
        sig_path = stmt_path + ".sig"
        if not build._ssh_verify(stmt_bytes, sig_path, core.SIGN_NAMESPACE, anchor, principal):
            continue
        with open(packet_path, "rb") as f:
            packet_bytes = f.read()
        if hashlib.sha256(packet_bytes).hexdigest() != stmt.get("packet_digest"):
            continue
        try:
            packet = json.loads(packet_bytes)
        except json.JSONDecodeError:
            continue
        if packet.get("root") != live_root or packet.get("build_digest") != live_bd:
            continue
        if not packet.get("proof") or not stmt.get("proof_recorded"):
            continue
        return True
    return False


def phase(d: str) -> str:
    """`draft` / `sealed` / `signed` -- agrees with `verify` on validity."""
    load_recipe(d)                               # raises on a hostile recipe
    if not os.path.isfile(os.path.join(d, core.MANIFEST)):
        return "draft"
    ver = verify(d)                              # raises on a structural break
    if not ver["ok"]:
        return "sealed"
    return "signed" if _is_signed(d) else "sealed"


# ============================================================================
# materializing a room, and the producer-cannot-change-the-question snapshot
# ============================================================================


def _snapshot(d: str, parsed: dict) -> dict:
    paths = list(identity._declared_inputs(d, parsed))
    paths.append(os.path.basename(recipe.recipe_path(d)))
    snap = {}
    for p in paths:
        resolved = core._safe(d, p)
        if os.path.isfile(resolved):
            snap[p] = core._hash_file(resolved)
    return snap


def _materialize(d: str, into: str, parsed: dict, input_from: dict) -> str:
    if os.path.exists(into):
        if os.path.isdir(into):
            if os.listdir(into):
                raise ClaimError(f"rebuild target is not empty: {into!r}")
        else:
            raise ClaimError(f"rebuild target is not a directory: {into!r}")
    os.makedirs(into, exist_ok=True)

    input_from = input_from or {}
    for path in identity._declared_inputs(d, parsed):
        if path in input_from:
            src = input_from[path]
            if not os.path.isabs(src):
                src = os.path.join(d, src)
        else:
            src = core._safe(d, path)
        dst = os.path.join(into, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    src_recipe = recipe.recipe_path(d)
    name = os.path.basename(src_recipe)
    dst_recipe = os.path.join(into, name)
    if identity._claim_format(parsed) >= 3:
        with open(dst_recipe, "w", encoding="utf-8") as f:
            f.write(build._dump_toml(identity._preimage_recipe(parsed)))
    else:
        shutil.copy2(src_recipe, dst_recipe)

    os.makedirs(os.path.join(into, core.STORE), exist_ok=True)
    return os.path.realpath(into)


# ============================================================================
# running the producer -- a hand-built, scrubbed environment
# ============================================================================


def _run_producer(room: str, parsed: dict, producer: str, outputs: list,
                   guidance: bool, producer_env: dict, usage_path: str) -> None:
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    claim = parsed.get("claim", {})
    env[core._ENV_CLAIM] = claim.get("name", "")
    env[core._ENV_OUTPUTS] = json.dumps(outputs)
    env[core._ENV_OUTPUT] = os.path.join(room, outputs[0]) if outputs else room
    env[core._ENV_USAGE] = usage_path

    if guidance:
        hints = {}
        for step in recipe.produces(parsed):
            if step.get("output") in outputs:
                g = build._step_guidance(step)
                if g is not None:
                    hints[step["output"]] = g
        if len(hints) == 1:
            env[core._ENV_REQUEST] = next(iter(hints.values()))
        elif hints:
            env[core._ENV_REQUEST] = json.dumps(hints)

    if producer_env:
        env.update(producer_env)

    try:
        proc = subprocess.run([core._SHELL, "-c", producer], cwd=room, env=env,
                               timeout=core.PRODUCER_TIMEOUT, capture_output=True)
    except subprocess.TimeoutExpired as e:
        raise ClaimError(f"producer timed out: {e}") from e
    except OSError as e:
        raise ClaimError(f"producer failed to start: {e}") from e
    if proc.returncode != 0:
        raise ClaimError(
            f"producer exited {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')}"
        )


# ============================================================================
# rebuild
# ============================================================================


def rebuild(d: str, producer: str, into: str, *, produce_from: dict = None,
            input_from: dict = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    """Regrow `d`'s generated outputs in a fresh room until its gates pass."""
    parsed = load_recipe(d)

    missing = run.preflight(parsed)
    if missing:
        raise ClaimError(f"environment: missing {missing} on this host")
    furnished = furnish(d, parsed)
    if not furnished.get("ok", True):
        raise ClaimError(f"environment: {furnished.get('reason')}")

    room = _materialize(d, into, parsed, input_from)
    snap = _snapshot(room, parsed)

    produce_from = produce_from or {}
    needed, reused = [], []
    for output in recipe.generated_outputs(parsed):
        if output in produce_from:
            src = produce_from[output]
            if not os.path.isabs(src):
                src = os.path.join(d, src)
            dst = core._safe(room, output)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            reused.append(output)
        else:
            needed.append(output)

    vendor = os.environ.get(core._ENV_VENDOR)
    model = os.environ.get(core._ENV_MODEL)

    usage_path = os.path.join(room, core.USAGE)
    started = time.monotonic()
    if needed:
        _run_producer(room, parsed, producer, needed, guidance, producer_env, usage_path)
    elapsed = time.monotonic() - started

    if _snapshot(room, parsed) != snap:
        raise ClaimError("producer rewrote a pinned input or the recipe; refused")

    usage = build._read_usage(room)

    gates_result = []
    with build._path_prefixed(furnished.get("path")):
        for step in recipe.gates(parsed):
            outcome = run_gate(step["run"], room, parsed)
            gates_result.append({"output": step["output"], "status": outcome["status"],
                                  "quarantine": outcome["quarantine"]})
    for g in gates_result:
        if g["status"] != "ok":
            raise ClaimError(f"gate {g['output']!r} did not pass: {g['status']}")

    manifest = seal(room)
    backend = run.sandbox_backend()

    entry = {"event": "rebuild", "when": core._now(), "quarantine": backend,
              "seconds": elapsed}
    entry.update(usage)
    if "calls" not in entry and needed:
        entry["calls"] = 1
    if vendor or model:
        entry["vendor"], entry["model"], entry["blind"] = vendor, model, True
    run.ledger(room, entry)
    run.ledger(room, {"event": "environment", "python": platform.python_version(),
                       "quarantine": backend})
    for output in reused:
        run.ledger(room, {"event": "reuse", "output": output})
    for g in gates_result:
        run.ledger(room, {"event": "gate", "output": g["output"],
                           "quarantine": g["quarantine"]})

    return {"root": manifest["root"], "name": manifest["name"], "gates": gates_result,
            "quarantine": backend, "cost": dict(usage, seconds=elapsed)}


# ============================================================================
# audit
# ============================================================================


def audit(d: str, *, produce_from: dict = None) -> dict:
    """Re-earn `d`'s verdicts cold: identity, confinement, then every gate."""
    parsed = load_recipe(d)
    gate_steps = recipe.gates(parsed)

    missing = run.preflight(parsed)
    if missing:
        rows = [{"output": s["output"], "status": "environment", "quarantine": None}
                for s in gate_steps]
        return {"ok": False, "verdict": "environment", "missing": missing,
                "environment": missing, "gates": rows}

    furnished = furnish(d, parsed)
    if not furnished.get("ok", True):
        rows = [{"output": s["output"], "status": "environment", "quarantine": None}
                for s in gate_steps]
        return {"ok": False, "verdict": "environment", "reason": furnished.get("reason"),
                "environment": [], "gates": rows}

    ver = verify(d)
    if not ver["ok"]:
        return {"ok": False, "verdict": "mismatch", "root": ver.get("root"),
                "environment": [], "gates": []}

    for step in recipe.produces(parsed):
        core._safe(d, step["output"])            # confinement covers generated too

    manifest = read_manifest(d)
    pins = manifest.get("parts", {})

    backups = {}
    produce_from = produce_from or {}
    recipe_path = recipe.recipe_path(d)
    recipe_backup = None
    try:
        for output, src in produce_from.items():
            dst = core._safe(d, output)
            backups[output] = open(dst, "rb").read() if os.path.exists(dst) else None
            if not os.path.isabs(src):
                src = os.path.join(d, src)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

        if identity._claim_format(parsed) >= 3:
            # THE ROOM MATCHES THE NAME: a gate judges against the
            # guidance-stripped recipe (what the root names), never the
            # raw on-disk file -- else two claims sharing a root could
            # accept differently depending on how a hint was worded.
            with open(recipe_path, "r", encoding="utf-8") as f:
                recipe_backup = f.read()
            stripped = build._dump_toml(identity._preimage_recipe(parsed))
            with open(recipe_path, "w", encoding="utf-8") as f:
                f.write(stripped)

        gates_result, overall_ok = [], True
        with build._path_prefixed(furnished.get("path")):
            for step in gate_steps:
                outcome = run_gate(step["run"], d, parsed)
                output = step["output"]
                if outcome["status"] in ("timeout", "failed"):
                    status = outcome["status"]
                else:
                    expected = pins.get(f"pinned:{output}")
                    status = "ok" if build._compare_pin(d, output, expected) else "mismatch"
                if status != "ok":
                    overall_ok = False
                gates_result.append({"output": output, "status": status,
                                      "quarantine": outcome["quarantine"]})
    finally:
        if recipe_backup is not None:
            with open(recipe_path, "w", encoding="utf-8") as f:
                f.write(recipe_backup)
        for output, content in backups.items():
            dst = core._safe(d, output)
            if content is None:
                if os.path.exists(dst):
                    os.remove(dst)
            else:
                with open(dst, "wb") as f:
                    f.write(content)

    return {"ok": overall_ok, "verdict": None if overall_ok else "failed",
            "root": ver["root"], "name": ver["name"], "environment": [],
            "gates": gates_result}


# ============================================================================
# furnish -- supersedes run.furnish: that implementation never sets `cwd`
# for the pip install subprocess, so a requirements file naming a LOCAL
# wheel by a relative path (as `--require-hashes` offline fixtures must)
# fails -- pip resolves the relative path against the caller's cwd, not
# the requirements file's own directory.
# ============================================================================


def furnish(d: str, parsed) -> dict:
    env_file = (parsed or {}).get("claim", {}).get("environment")
    if not env_file:
        return {"ok": True, "path": None}
    resolved = core._safe(d, env_file)
    if not os.path.isfile(resolved):
        return {"ok": False, "reason": f"missing environment file: {env_file!r}"}
    digest = core._hash_file(resolved)
    key = f"{digest}-{platform.python_implementation()}-{platform.python_version()}-{platform.system()}"
    venv_dir = os.path.join(run._env_cache_dir(), key)
    bindir = os.path.join(venv_dir, "bin")
    if not os.path.isdir(venv_dir):
        os.makedirs(run._env_cache_dir(), exist_ok=True)
        try:
            subprocess.run(["python3", "-m", "venv", venv_dir],
                            check=True, timeout=core.FURNISH_TIMEOUT, capture_output=True)
            subprocess.run(
                [os.path.join(bindir, "pip"), "install", "--require-hashes",
                 "--only-binary=:all:", "-r", resolved],
                check=True, timeout=core.FURNISH_TIMEOUT, capture_output=True,
                cwd=os.path.dirname(resolved),
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            shutil.rmtree(venv_dir, ignore_errors=True)
            return {"ok": False, "reason": str(e)}
    return {"ok": True, "path": bindir}


# ============================================================================
# run_gate -- supersedes run.run_gate: the sandbox signal must name the
# backend ("seatbelt"/"bubblewrap"), not a bare "1". A kernel that applies a
# sandbox but never says which one makes a wrapped claim-runner gate nest and
# die; run.py's own scrub sets the flag but not its value, so the signal is
# rebuilt here rather than patched after the fact.
# ============================================================================


def run_gate(cmd: str, d: str, parsed) -> dict:
    d = os.path.realpath(d)
    backend = run.sandbox_backend()
    apply_sandbox = backend not in ("none", "inherited")
    room = run._room_dir(d)
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    if apply_sandbox:
        env["HOME"] = room
        env["TMPDIR"] = room
        env[core._JAILED] = backend
    argv = run._sandbox_argv(cmd, d, backend)
    timeout = run.gate_timeout(parsed)
    result = run._run(argv, d, env, timeout)
    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend}


# ============================================================================
# gate_deciders / vacuous_gates
# ============================================================================


def _strip_redirection(tokens: list) -> list:
    for i, tok in enumerate(tokens):
        if tok.startswith(_REDIR_PREFIXES):
            return tokens[:i]
    return tokens


def gate_deciders(cmd: str) -> list:
    """Which files a gate's run command executes as scripts/suites -- not
    every file it merely reads. `grep pattern data.txt` decides by the
    pattern (pinned in the recipe text); `python3 check.py` decides by
    check.py's own bytes."""
    deciders = []
    for segment in _OP_SPLIT.split(cmd):
        tokens = _strip_redirection(segment.split())
        if not tokens:
            continue
        head = tokens[0]
        if head in _INTERPRETERS:
            i = 1
        elif head.startswith("./") or ("/" in head and not head.startswith("-")):
            deciders.append(head[2:] if head.startswith("./") else head)
            continue
        else:
            continue
        while i < len(tokens):
            tok = tokens[i]
            if tok.startswith("-"):
                i += 2 if tok in _SKIP_VALUE else 1
                continue
            deciders.append(tok)
            break
    return deciders


def vacuous_gates(parsed: dict) -> list:
    """Gates whose every decider is itself a generated output -- the verdict
    then depends on no claimed bytes, and any implementation printing the
    passing status would satisfy it."""
    generated = set(recipe.generated_outputs(parsed))
    out = []
    for step in recipe.gates(parsed):
        deciders = gate_deciders(step.get("run", ""))
        if deciders and all(dec in generated for dec in deciders):
            out.append(step["output"])
    return out


# ============================================================================
# sign_node -- the bottom-anchored signature chain
# ============================================================================


def sign_node(root: str, digest: str, links: list) -> str:
    canon = json.dumps({"root": root, "build_digest": digest, "links": sorted(links)},
                        sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ============================================================================
# mutation scoring
# ============================================================================


def _line_offsets(source: str) -> list:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _node_span(source: str, node) -> tuple:
    offsets = _line_offsets(source)
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    return start, end


def _span_text(source: str, span: tuple) -> str:
    return source[span[0]:span[1]]


def _splice(source: str, start: int, end: int, replacement: str) -> str:
    return source[:start] + replacement + source[end:]


def _edit(source: str, span: tuple, replacement: str) -> str:
    return _splice(source, span[0], span[1], replacement)


def _docstring_spans(tree, source: str) -> list:
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and isinstance(body[0].value.value, str)):
                spans.append(_node_span(source, body[0]))
    return spans


def _overlaps(span: tuple, spans: list) -> bool:
    return any(not (span[1] <= s[0] or span[0] >= s[1]) for s in spans)


def _named(node) -> str:
    return f"{type(node).__name__}@{getattr(node, 'lineno', '?')}"


def _label(tag: str, detail: str, lineno) -> str:
    return f"{tag}:{lineno}:{detail}"


def _structural_mutants(tree, source: str) -> list:
    """AST-level edits on nodes with reliable spans: negate an `if` test,
    replace a `return`'s value with `None`."""
    skip = _docstring_spans(tree, source)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and node.test is not None:
            span = _node_span(source, node.test)
            if _overlaps(span, skip):
                continue
            old = _span_text(source, span)
            out.append((_label("negate-if", _named(node), node.lineno),
                        _edit(source, span, f"not ({old})")))
        elif isinstance(node, ast.Return) and node.value is not None:
            span = _node_span(source, node.value)
            if _overlaps(span, skip):
                continue
            out.append((_label("return-none", _named(node), node.lineno),
                        _edit(source, span, "None")))
    return out


def _token_mutants(source: str) -> list:
    """Token-level edits: flip a comparison/arithmetic operator, swap a
    boolean/control word -- found with `tokenize`, so a match inside a
    string literal is never mistaken for one in code."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenizeError, IndentationError, SyntaxError, UnicodeDecodeError):
        return []
    offsets = _line_offsets(source)
    out = []
    for tok in tokens:
        alt = None
        if tok.type == tokenize.OP and tok.string in _OP_ALTS:
            alt = _OP_ALTS[tok.string]
            tag = "op"
        elif tok.type == tokenize.NAME and tok.string in _WORD_ALTS:
            alt = _WORD_ALTS[tok.string]
            tag = "word"
        if alt is None:
            continue
        start = offsets[tok.start[0] - 1] + tok.start[1]
        end = offsets[tok.end[0] - 1] + tok.end[1]
        out.append((_label(tag, f"{tok.string}->{alt}", tok.start[0]),
                    _splice(source, start, end, alt)))
    return out


def _mutants(source: str) -> list:
    """Every candidate (label, mutated source) pair for one generated file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    out = list(_structural_mutants(tree, source)) if tree is not None else []
    out += _token_mutants(source)
    return out


def _mutant_order(n: int, seed) -> list:
    """A deterministic permutation of `range(n)`, seeded from the root."""
    order = list(range(n))
    random.Random(seed).shuffle(order)
    return order


def _draw_order(order: list, k: int) -> list:
    return order[:k]


def mutation_score(d: str, *, max_mutants: int = 50) -> dict:
    """Kill rate of deterministic mutants of `d`'s generated outputs,
    drawn from the root, against `d`'s own gates. Residue only."""
    parsed = load_recipe(d)
    floor = parsed.get("claim", {}).get("mutation_floor")
    manifest = read_manifest(d)
    root_hex = manifest["root"]
    pins = manifest.get("parts", {})

    candidates = []  # (output, label, mutated_source)
    for output in recipe.generated_outputs(parsed):
        path = core._safe(d, output)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except UnicodeDecodeError:
            continue
        for label, mutated in _mutants(source):
            candidates.append((output, label, mutated))

    gate_steps = recipe.gates(parsed)
    if not candidates:
        score = {"mutants": 0, "survivors": [], "rate": 1.0, "ok": True}
        _write_score_residue(d, score)
        return score

    order = _mutant_order(len(candidates), root_hex)
    chosen = [candidates[i] for i in _draw_order(order, max_mutants)]

    survivors = []
    for idx, (output, label, mutated) in enumerate(chosen):
        target = core._safe(d, output)
        with open(target, "r", encoding="utf-8") as f:
            backup = f.read()
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(mutated)
            killed = False
            for step in gate_steps:
                outcome = run_gate(step["run"], d, parsed)
                if outcome["status"] != "ok":
                    killed = True
                    break
                expected = pins.get(f"pinned:{step['output']}")
                if not build._compare_pin(d, step["output"], expected):
                    killed = True
                    break
            if not killed:
                survivors.append(_label(output, label, idx))
        finally:
            with open(target, "w", encoding="utf-8") as f:
                f.write(backup)

    n = len(chosen)
    rate = 1.0 - (len(survivors) / n) if n else 1.0
    score = {"mutants": n, "survivors": survivors, "rate": rate,
              "ok": floor is None or rate >= floor}
    _write_score_residue(d, score)
    return score


def _write_score_residue(d: str, score: dict) -> None:
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    core._write_json(os.path.join(d, core.MUTATION_RESIDUE), score)


# ============================================================================
# independence
# ============================================================================


def independence(d: str) -> dict:
    """A directory's declared producer, from the last ledgered rebuild that
    named one -- `{}` when nothing was declared."""
    for event in reversed(run.ledger_events(d)):
        if event.get("event") == "rebuild" and ("vendor" in event or "model" in event):
            return {"vendor": event.get("vendor"), "model": event.get("model"),
                    "blind": event.get("blind")}
    return {}


def _independence_line(producer: dict) -> str:
    vendor, model = producer.get("vendor"), producer.get("model")
    if not vendor or not model:
        return "unestablished"
    workspace = "blind workspace" if producer.get("blind") else "non-blind workspace"
    return f"declared: {vendor}/{model}, {workspace} (not proven)"


# ============================================================================
# _machine -- one leg of a crosscheck, directory or record, uniformly
# ============================================================================


def record_read(path: str) -> dict:
    """`attest.record_read`, plus the bond that a record IS its own
    canonical bytes -- `attest.py`'s reader validates the parsed document
    but never checks the file wasn't reformatted (pretty-printed) after
    the fact, which would make its digest name bytes nobody signed."""
    doc = attest.record_read(path)
    with open(path, "rb") as f:
        raw = f.read()
    if raw != attest.record_canonical(doc):
        raise ClaimError(f"record {path!r} is not its own canonical bytes")
    return doc


def _machine(leg: str) -> dict:
    if os.path.isdir(leg):
        parsed = load_recipe(leg)
        ver = verify(leg)
        try:
            bd = identity.build_digest(leg)
        except ClaimError:
            bd = None
        try:
            au = audit(leg)
        except ClaimError:
            au = {"ok": False, "gates": []}
        claim = parsed.get("claim", {})
        declared = {k: claim[k] for k in _OBLIGATION_KEYS if k in claim}
        return {"kind": "dir", "root": ver["root"], "build_digest": bd,
                "audited": bool(au.get("ok")), "gates": au.get("gates", []),
                "cost": run.cost(leg), "declared": declared,
                "producer": independence(leg)}
    doc = record_read(leg)
    declared = doc.get("claim") if doc.get("record", 1) >= 2 else _UNKNOWN
    audited = all(g.get("status") == "ok" for g in doc.get("gates", []))
    return {"kind": "record", "root": doc["root"], "build_digest": doc["build_digest"],
            "audited": audited, "gates": doc.get("gates", []),
            "cost": doc.get("cost"), "declared": declared,
            "producer": doc.get("producer", {})}


def _comparable(c1, c3, tolerance: float):
    """Whether C3/C1 lands within `[1/tolerance, tolerance]`, in the
    strongest unit both ledgers measured; `None` when nothing is shared."""
    if not c1 or not c3:
        return None
    for unit in core.COST_LADDER:
        if unit in c1 and unit in c3:
            v1, v3 = c1[unit], c3[unit]
            if v1 == 0:
                return v3 == 0
            ratio = v3 / v1
            return (1.0 / tolerance) <= ratio <= tolerance
    return None


# ============================================================================
# crosscheck -- the three-machine test
# ============================================================================


def crosscheck(m1, m2, m3, *, mutants: int = None) -> dict:
    reals = [os.path.realpath(p) for p in (m1, m2, m3)]
    if len(set(reals)) < 3:
        raise ClaimError("crosscheck requires three distinct machines")

    facts = {"M1": _machine(m1), "M2": _machine(m2), "M3": _machine(m3)}
    roots = {k: v["root"] for k, v in facts.items()}
    root_values = {r for r in roots.values() if r}
    equivalence = len(root_values) == 1 and all(roots.values())
    audited = {k: v["audited"] for k, v in facts.items()}

    bd1, bd2 = facts["M1"]["build_digest"], facts["M2"]["build_digest"]
    reuse = (bd1 == bd2) if (bd1 is not None and bd2 is not None) else None

    rejected, incomplete = [], []
    if not equivalence:
        rejected.append("root")
    if reuse is False:
        rejected.append("reuse")
    for key in ("M1", "M2", "M3"):
        if not audited[key]:
            rejected.append(f"audited {key}")

    declared = facts["M1"]["declared"]
    if declared is _UNKNOWN:
        incomplete.append("declared-conditions")
        declared = {}

    tolerance = declared.get("tolerance", _DEFAULT_TOLERANCE)
    c1, c3 = facts["M1"]["cost"], facts["M3"]["cost"]
    comparable = _comparable(c1, c3, tolerance)
    if "tolerance" in declared:
        if comparable is None:
            incomplete.append("tolerance")
        elif comparable is False:
            rejected.append("tolerance")

    envelope_report = {}
    for unit, ceiling in declared.get("envelope", {}).items():
        measured = c3.get(unit) if c3 else None
        if measured is None:
            envelope_report[unit] = {"within": None, "ceiling": ceiling}
            incomplete.append(f"envelope {unit}")
        else:
            within = measured <= ceiling
            envelope_report[unit] = {"within": within, "ceiling": ceiling, "measured": measured}
            if not within:
                rejected.append(f"envelope {unit}")

    floor = declared.get("mutation_floor")
    mscore = None
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
        "roots": roots,
        "audited": audited,
        "reuse": reuse,
        "cost": {"comparable": comparable, "envelope": envelope_report},
        "mutation_score": mscore,
        "independence": _independence_line(facts["M3"]["producer"]),
    }


# ============================================================================
# record_proof -- freezing a satisfied crosscheck onto M1's manifest
# ============================================================================


def record_proof(m1: str, m2, m3) -> dict:
    if not os.path.isdir(m1):
        raise ClaimError("record_proof requires M1 to be a claim directory")
    result = crosscheck(m1, m2, m3)
    if result["verdict"] != "accept":
        return {"proof_recorded": False, "crosscheck": result}

    anchor = os.environ.get(core._ENV_SIGNERS)
    records = []
    for label, leg in (("m2", m2), ("m3", m3)):
        if os.path.isdir(leg):
            continue
        if not anchor or not os.path.isfile(anchor):
            raise ClaimError(f"{label} is a frozen record; no trust anchor to embed it with")
        signer = attest.record_signer(leg, anchor)
        if signer is None:
            raise ClaimError(f"{label}'s record signature does not verify against the anchor")
        records.append({"digest": attest.record_digest(record_read(leg)), "signer": signer})

    manifest = read_manifest(m1)
    manifest["proof"] = {"kind": "crosscheck", "m2": os.path.realpath(m2) if os.path.isdir(m2) else m2,
                          "m3": os.path.realpath(m3) if os.path.isdir(m3) else m3,
                          "records": records}
    core._write_json(os.path.join(m1, core.MANIFEST), manifest)
    return {"proof_recorded": True, "crosscheck": result}


# ============================================================================
# sandbox -- the public two-arg probe the check calls
# ============================================================================


def sandbox(cmd: str, d: str):
    probe = run.sandbox()
    return (probe, probe["backend"])
