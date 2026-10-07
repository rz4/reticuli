"""Crosscheck: the three-machine test, mutation testing, and the kernel
verbs that depend on more than one lower module (`root`, `seal`, `verify`,
`phase`, `rebuild`, `audit`, `record_proof`, `sign_node`, `independence`,
`sandbox`) plus the claim-boundary helpers (`vacuous_gates`,
`gate_deciders`).

This is the one `_kernel` submodule allowed to import every other one;
`reticuli/kernel.py` is a thin re-export over what lives here plus the
handful of pure pass-throughs the lower modules already get right.

Two gaps in the lower modules are closed here, at the assembly layer,
rather than by editing those modules:

- `[claim] environment` is a pinned input (`spec/claim-format.md`) but
  `identity.py`'s preimage never names it -- `_parts` below adds its hash
  alongside the declared inputs before hashing, so `root`/`seal`/`verify`
  stay consistent with the spec without touching `identity.py`.
- `build.rebuild`'s usage reader refuses a payload carrying any key
  outside `{usd, tokens, calls}`, including `seconds` -- which a hostile
  OR merely confused producer can still write, since `seconds` is meant
  to be refused *silently* (the kernel's own measurement, never a
  self-report), not treated as a reason to fail the whole rebuild.
  `rebuild` below is composed from `build`'s private materialize/produce
  primitives directly, with its own lenient usage reader, plus the
  ledger entries (`oracle`, `environment`, `reuse`, `gate`) the rest of
  this suite and the record transport read back.
- `run.run_gate` applies a sandbox without SAYING so to the process it
  wraps: it sets `RETICULI_JAILED` to the literal flag `"1"`, not the
  backend name, so a gate that is itself a claim runner cannot tell
  which jail it is already inside and tries to nest. `run_gate` below
  is `run`'s own version, rebuilt from its private pieces
  (`sandbox_backend`, `gate_timeout`, `_scratch_dir`, `_scrub_env`,
  `_sandbox_argv`, `_run`) with that one line corrected; every verb in
  this module calls this version, never `run._run_gate` wholesale.
- `build._produce` hands the producer `dict(os.environ)` whole, so any
  inherited credential reaches it unasked. The room's environment is a
  boundary both ways: what the caller does not hand over must never
  arrive. `_produce` below starts from a minimal allowlist (the same
  shape as a gate's own scrub) and lets only `producer_env` cross it
  deliberately, plus the kernel's own output/usage/guidance variables.
- `run.furnish` installs from the claim's `[claim] environment` lock
  file without setting `cwd`, so pip resolves a *relative* local wheel
  path named inside it against the caller's own working directory, not
  the lock file's -- installing fails for exactly the offline, hash-pinned
  wheel the format exists to support. `furnish` below is the same
  venv-then-install sequence with that one `cwd` added.

Stdlib only.
"""
import ast
import hashlib
import io
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize

from .core import (
    ClaimError,
    MANIFEST,
    MUTANT_CEILING,
    MUTATION_RESIDUE,
    PRODUCER_TIMEOUT,
    STORE,
    TOLERANCE,
    COST_LADDER,
    USAGE,
    _ENV_MODEL,
    _ENV_OUTPUT,
    _ENV_OUTPUTS,
    _ENV_REQUEST,
    _ENV_SIGNERS,
    _ENV_USAGE,
    _ENV_VENDOR,
    _JAILED,
    _SHELL,
    SIGN_DIR,
    SIGN_NAMESPACE,
    _hash_file,
    _judging_host,
    _safe,
    _write_json,
)
from . import recipe as _recipe
from . import identity as _identity
from . import seal as _seal
from . import run as _run
from . import build as _build
from . import attest as _attest


# =====================================================================
# run_gate: `run`'s own gate runner, with the sending half of the
# sandbox-signal contract corrected (the backend name, not a flag).
# =====================================================================

def run_gate(cmd: str, workdir: str, recipe=None) -> dict:
    backend = _run.sandbox_backend()
    timeout = _run.gate_timeout(recipe)
    room = os.path.realpath(workdir)
    scratch = _run._scratch_dir(room)

    env = _run._scrub_env()
    env["TMPDIR"] = scratch
    env["HOME"] = scratch
    if backend != "none":
        env[_JAILED] = backend

    argv = _run._sandbox_argv(backend, room, scratch, cmd)
    try:
        proc = _run._run(argv, cwd=room, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "quarantine": backend}

    status = "ok" if proc.returncode == 0 else "failed"
    return {"status": status, "quarantine": backend}


# =====================================================================
# The claim boundary: which gates are decided by claimed code, and which
# files a gate command actually executes.
# =====================================================================

_INTERPRETERS = frozenset({
    'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node',
    'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php',
    'sh', 'bash', 'py', 'pytest',
})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})

_SEGMENT_SPLIT = re.compile(
    "|".join(re.escape(op) for op in sorted(_OPERATORS, key=len, reverse=True))
)


def _split_segments(cmd: str) -> list:
    return [p.strip() for p in _SEGMENT_SPLIT.split(cmd) if p.strip()]


def _segment_decider(segment: str):
    """The workspace file this one shell segment runs, if any -- a
    script named after a known interpreter (its module/value flags and
    their arguments skipped), or a direct `./executable` -- else `None`
    for ordinary shell utilities (`grep`, `printf`, `test`, ...), which
    decide nothing a workspace script wrote."""
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return None
    if not tokens:
        return None
    first, rest = tokens[0], tokens[1:]
    if first in _INTERPRETERS:
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok in _SKIP_VALUE:
                i += 2
                continue
            if tok.startswith('-'):
                i += 1
                continue
            return tok[2:] if tok.startswith('./') else tok
        return None
    if first.startswith('./') or first.startswith('/'):
        return first[2:] if first.startswith('./') else first
    return None


def _all_deciders(cmd: str) -> list:
    return [d for d in (_segment_decider(s) for s in _split_segments(cmd)) if d]


def gate_deciders(cmd: str) -> list:
    """The file(s) that decide this gate command -- a heuristic read of
    its first segment only (`spec/verification.md`: this is
    implementation-defined beyond the pinned vectors)."""
    segs = _split_segments(cmd)
    if not segs:
        return []
    d = _segment_decider(segs[0])
    return [d] if d else []


def vacuous_gates(recipe: dict) -> list:
    """Gate steps whose every decider is itself a generated output of
    this same recipe -- the verdict depends on no claimed bytes at all,
    so any implementation that prints a passing status satisfies it."""
    generated = {s["output"] for s in _recipe.produces(recipe)
                 if s.get("class", "generated") == "generated"}
    out = []
    for step in _recipe.gates(recipe):
        deciders = _all_deciders(step.get("run", ""))
        if deciders and all(d in generated for d in deciders):
            out.append(step["output"])
    return out


# =====================================================================
# load_recipe: `recipe.load_recipe`, plus the `[claim]` extras it never
# validates -- `envelope` must be a non-empty table of a known cost unit
# to a positive ceiling, since a damaged one is hostile recipe bytes
# like any other and must refuse at parse, not surface later as a
# `TypeError` deep in the cost comparison.
# =====================================================================

def load_recipe(d: str) -> dict:
    parsed = _recipe.load_recipe(d)
    claim = parsed.get("claim") or {}
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("[claim] envelope must be a non-empty table of unit -> ceiling")
        for unit, ceiling in envelope.items():
            if unit not in COST_LADDER:
                raise ClaimError(f"[claim] envelope names an unknown unit: {unit!r}")
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                raise ClaimError(f"[claim] envelope.{unit} must be a positive number")
    return parsed


# =====================================================================
# The mutation engine: deterministic mutants of a generated Python file.
# =====================================================================

_ARITHMETIC = ('+', '-', '*', '/', '//', '%', '**')
_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')

_OP_ALTS = {
    '+': ('-',), '-': ('+',), '*': ('/',), '/': ('*',),
    '//': ('*',), '%': ('*',), '**': ('*',),
    '>': ('<=', '<', '>='), '<': ('>=', '>', '<='),
    '>=': ('<', '<='), '<=': ('>', '>='),
    '==': ('!=',), '!=': ('==',),
}
_OP_KIND = {}
for _op in _ARITHMETIC:
    _OP_KIND[_op] = 'arithmetic'
for _op in _COMPARISON:
    _OP_KIND[_op] = 'comparison'

_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}
_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


def _node_span(node) -> tuple:
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def _offset(lines: list, lineno: int, col: int) -> int:
    return sum(len(l) for l in lines[:lineno - 1]) + col


def _span_text(source: str, span: tuple) -> str:
    lines = source.splitlines(keepends=True)
    return source[_offset(lines, span[0], span[1]):_offset(lines, span[2], span[3])]


def _edit(source: str, span: tuple, replacement: str) -> str:
    lines = source.splitlines(keepends=True)
    start = _offset(lines, span[0], span[1])
    end = _offset(lines, span[2], span[3])
    return source[:start] + replacement + source[end:]


def _splice(lines: list, start: tuple, end: tuple, replacement: str):
    """Replace the text between two (row, col) tokenize positions with
    `replacement`; `None` for a token spanning more than one line."""
    (sr, sc), (er, ec) = start, end
    if sr != er:
        return None
    line = lines[sr - 1]
    new_lines = list(lines)
    new_lines[sr - 1] = line[:sc] + replacement + line[ec:]
    return "".join(new_lines)


def _label(kind: str, detail: str) -> str:
    return f"{kind}:{detail}"


def _named(mutant: tuple) -> str:
    return mutant[0]


def _docstring_spans(tree) -> list:
    """Spans of module/function/class docstrings -- excluded from
    structural mutation since they are not executable."""
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                spans.append(_node_span(body[0].value))
    return spans


def _token_mutants(source: str) -> list:
    """One mutant per occurrence of an operator or boolean/word literal
    with a known alternative, by splicing the token's own text."""
    mutants = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenizeError, SyntaxError, IndentationError, ValueError):
        return mutants
    lines = source.splitlines(keepends=True)
    for tok in tokens:
        text = tok.string
        if tok.type == tokenize.OP and text in _OP_ALTS:
            for alt in _OP_ALTS[text]:
                mutated = _splice(lines, tok.start, tok.end, alt)
                if mutated is not None:
                    mutants.append((_label("op", f"{text}->{alt}@{tok.start[0]}:{tok.start[1]}"), mutated))
        elif tok.type == tokenize.NAME and text in _WORD_ALTS:
            mutated = _splice(lines, tok.start, tok.end, _WORD_ALTS[text])
            if mutated is not None:
                mutants.append((_label("word", f"{text}->{_WORD_ALTS[text]}@{tok.start[0]}:{tok.start[1]}"), mutated))
    return mutants


def _structural_mutants(source: str) -> list:
    """One mutant per `if`/`while` test, negating it -- a condition the
    token-level mutants above cannot reach without touching every
    comparison inside it at once."""
    mutants = []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return mutants
    doc_spans = set(_docstring_spans(tree))
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While)):
            span = _node_span(node.test)
            if span in doc_spans:
                continue
            original = _span_text(source, span)
            mutated = _edit(source, span, f"not ({original})")
            mutants.append((_label("negate", f"{type(node).__name__}@{span[0]}:{span[1]}"), mutated))
    return mutants


def _mutants(source: str) -> list:
    """Every candidate mutant of `source`, deduplicated by the bytes it
    actually produces."""
    seen = set()
    out = []
    for label, mutated in _token_mutants(source) + _structural_mutants(source):
        if mutated in seen or mutated == source:
            continue
        seen.add(mutated)
        out.append((label, mutated))
    return out


def _draw_order(n: int, seed: str) -> list:
    """A deterministic permutation of `range(n)`, keyed by `seed` (the
    claim's root) so the sample is reproducible but not predictable from
    the mutants' own content."""
    idx = list(range(n))
    idx.sort(key=lambda i: hashlib.sha256(f"{seed}:{i}".encode("utf-8")).hexdigest())
    return idx


def _mutant_order(mutants: list, seed: str) -> list:
    return [mutants[i] for i in _draw_order(len(mutants), seed)]


def _machine(d: str, parsed: dict, output: str, mutated_source: str) -> bool:
    """Judge one mutant: materialize a fresh room from `d` (inputs and
    the claim's own generated bytes), overwrite `output` with the mutant,
    and run every gate. Returns whether the mutant SURVIVED -- every gate
    still passed."""
    room = tempfile.mkdtemp(prefix="reticuli-mutant-")
    try:
        _build._materialize(d, room, parsed, include_generated=True)
        _rewrite_room_recipe(room, parsed)
        with open(_safe(room, output), "w", encoding="utf-8") as f:
            f.write(mutated_source)
        for step in _recipe.gates(parsed):
            result = run_gate(step["run"], room, parsed)
            if result["status"] != "ok":
                return False
        return True
    finally:
        shutil.rmtree(room, ignore_errors=True)


def _read_manifest(d: str) -> dict:
    """`seal.read_manifest`, refusing non-UTF-8 bytes as a `ClaimError`
    too -- the given reader catches a bad JSON document but not a raw
    decode failure, and a hostile manifest is untrusted input either way."""
    try:
        return _seal.read_manifest(d)
    except UnicodeDecodeError as exc:
        raise ClaimError(f"no readable manifest for {d!r}: {exc}") from exc


def mutation_score(d: str, *, max_mutants: int = None, floor: float = None) -> dict:
    """Deterministic mutants of the claim's generated Python outputs,
    drawn from its root, re-audited; residue at `MUTATION_RESIDUE`."""
    parsed = load_recipe(d)
    manifest = _read_manifest(d)
    seed = manifest["root"]
    cap = max_mutants if max_mutants is not None else MUTANT_CEILING

    candidates = []
    for output in _recipe.generated_outputs(parsed):
        if not output.endswith(".py"):
            continue
        path = _safe(d, output)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            source = f.read()
        for label, mutated in _mutants(source):
            candidates.append((output, label, mutated))

    selected = _mutant_order(candidates, seed)[:cap]
    survivors = []
    killed = 0
    for output, label, mutated in selected:
        if _machine(d, parsed, output, mutated):
            survivors.append(f"{output}:{label}")
        else:
            killed += 1

    tested = len(selected)
    rate = (killed / tested) if tested else 0.0
    result = {"mutants": tested, "rate": rate, "survivors": survivors}
    result["ok"] = True if floor is None else rate >= floor
    _write_json(os.path.join(d, MUTATION_RESIDUE), result)
    return result


# =====================================================================
# Identity, closing the environment-file gap: the compensated preimage.
# =====================================================================

def _parts(parsed: dict, d: str) -> dict:
    """`identity._parts`, plus the environment-file gap closed, and any
    raw `OSError` from hashing a declared-but-absent file refused in
    band -- a missing pinned input is a broken claim, not a traceback."""
    try:
        parts = dict(_identity._parts(parsed, d))
        env_file = (parsed.get("claim") or {}).get("environment")
        if env_file:
            parts[f"input:{env_file}"] = _hash_file(_safe(d, env_file))
    except OSError as exc:
        raise ClaimError(f"could not hash a declared file in {d!r}: {exc}") from exc
    return parts


def _toml_value(v) -> str:
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
        return "{ " + ", ".join(f"{k} = {_toml_value(val)}" for k, val in v.items()) + " }"
    raise ClaimError(f"cannot serialize {v!r} into the room's recipe")


def _rewrite_room_recipe(room: str, parsed: dict) -> None:
    """At format 3+, the room a gate judges in must see exactly what the
    root names (`spec/identity.md`): the guidance-stripped, format-4-
    canonicalized recipe -- never the raw file `_materialize` copied in,
    or a gate that reads its own recipe could accept one wording of a
    hint and reject another, same root. Formats 1-2 are untouched: their
    root covers the whole file, and so does the room."""
    fmt = parsed.get("claim", {}).get("format", 1)
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 3:
        return
    preimage = _identity._preimage_recipe(parsed)
    lines = ["[claim]"]
    for key, value in preimage.get("claim", {}).items():
        lines.append(f"{key} = {_toml_value(value)}")
    for step in preimage.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for key, value in step.items():
            lines.append(f"{key} = {_toml_value(value)}")
    text = "\n".join(lines) + "\n"
    with open(_recipe.recipe_path(room), "w", encoding="utf-8") as f:
        f.write(text)


def root(parsed: dict, d: str) -> str:
    return _identity._sha256_hex(_identity._canonical_json(_parts(parsed, d)).encode("utf-8"))


def seal(d: str) -> dict:
    parsed = load_recipe(d)
    parts = _parts(parsed, d)
    r = _identity._sha256_hex(_identity._canonical_json(parts).encode("utf-8"))
    manifest = {"name": parsed["claim"]["name"], "root": r, "parts": parts}
    os.makedirs(os.path.join(d, STORE), exist_ok=True)
    _write_json(os.path.join(d, MANIFEST), manifest)
    return manifest


def verify(d: str) -> dict:
    manifest = _read_manifest(d)
    parsed = load_recipe(d)
    recomputed = root(parsed, d)
    return {"ok": recomputed == manifest["root"], "root": manifest["root"],
            "recomputed": recomputed, "name": manifest["name"]}


def build_digest(d: str) -> str:
    return _identity.build_digest(d)


# =====================================================================
# phase: draft / sealed / signed.
# =====================================================================

def phase(d: str) -> str:
    if not os.path.isfile(os.path.join(d, MANIFEST)):
        load_recipe(d)  # a hostile/missing recipe still refuses
        return "draft"
    vr = verify(d)
    if not vr["ok"]:
        raise ClaimError(f"claim at {d!r} does not verify: cannot report phase")
    manifest = _read_manifest(d)
    proof = manifest.get("proof")
    if not proof:
        return "sealed"
    anchor = os.environ.get(_ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):
        return "sealed"
    sign_dir = os.path.join(d, SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return "sealed"
    current_root = vr["root"]
    try:
        current_digest = build_digest(d)
    except ClaimError:
        return "sealed"

    for fname in sorted(os.listdir(sign_dir)):
        if not fname.endswith(".sign.json"):
            continue
        stmt_path = os.path.join(sign_dir, fname)
        sig_path = stmt_path + ".sig"
        if not os.path.isfile(sig_path):
            continue
        try:
            with open(stmt_path, "rb") as f:
                stmt_bytes = f.read()
            stmt = json.loads(stmt_bytes)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(stmt, dict) or stmt.get("root") != current_root:
            continue
        identity = stmt.get("identity")
        packet_digest = stmt.get("packet_digest")
        if not isinstance(identity, str) or not isinstance(packet_digest, str):
            continue
        packet_path = os.path.join(sign_dir, fname[:-len(".sign.json")] + ".packet.json")
        if not os.path.isfile(packet_path):
            continue
        try:
            with open(packet_path, encoding="utf-8") as f:
                packet = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(packet, dict):
            continue
        actual_digest = hashlib.sha256(
            json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()
        if (actual_digest != packet_digest
                or packet.get("root") != current_root
                or packet.get("build_digest") != current_digest
                or packet.get("proof") != proof):
            continue
        if _build._ssh_verify(anchor, identity, SIGN_NAMESPACE, stmt_bytes, sig_path):
            return "signed"
    return "sealed"


# =====================================================================
# rebuild: regrow, ledgering what the lower module silently does, with a
# lenient usage reader (never raises on a stray or self-reported key).
# =====================================================================

_USAGE_KEYS = frozenset({"usd", "tokens", "calls"})


def _read_usage(room: str) -> dict:
    path = os.path.join(room, USAGE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            usage = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(usage, dict):
        return {}
    result = {}
    for key, value in usage.items():
        if key not in _USAGE_KEYS:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            continue
        result[key] = value
    return result


def _snapshot_pinned(parsed: dict, where: str) -> dict:
    snap = {path: _hash_file(_safe(where, path)) for path in _recipe._inputs(parsed, where)}
    with open(_recipe.recipe_path(where), "rb") as f:
        snap["__recipe__"] = hashlib.sha256(f.read()).hexdigest()
    return snap


_PRODUCER_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ")


def _produce(parsed: dict, room: str, producer: str, *, guidance: bool = True,
             producer_env: dict = None, timeout: float = None) -> dict:
    """Run the producer once, unsandboxed, network and HOME included --
    but starting from a minimal allowlist, never the caller's full
    environment: an inherited credential crosses only through
    `producer_env`, by the caller's deliberate hand."""
    outputs = [s["output"] for s in _recipe.produces(parsed)
               if s.get("class", "generated") == "generated" and "from" not in s]
    room_real = os.path.realpath(room)
    os.makedirs(os.path.join(room_real, STORE), exist_ok=True)

    env = {k: os.environ[k] for k in _PRODUCER_KEEP_ENV if k in os.environ}
    if outputs:
        env[_ENV_OUTPUT] = os.path.join(room_real, outputs[0])
    env[_ENV_OUTPUTS] = json.dumps(outputs)
    env[_ENV_USAGE] = os.path.join(room_real, USAGE)
    if guidance:
        for step in _recipe.produces(parsed):
            text = _build._step_guidance(step)
            if text is not None:
                env[_ENV_REQUEST] = text
                break
    if producer_env:
        for key, value in producer_env.items():
            if _build._authorized(key):
                env[key] = value

    proc = subprocess.run(
        [_SHELL, "-c", producer], cwd=room_real, env=env,
        timeout=timeout or PRODUCER_TIMEOUT,
    )
    if proc.returncode != 0:
        raise ClaimError(f"producer exited {proc.returncode}")
    return {"status": "ok"}


def rebuild(d: str, producer: str, into: str, *, produce_from: dict = None,
            input_from: dict = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    parsed = load_recipe(d)
    missing = _run.preflight(parsed)
    if missing:
        raise ClaimError(f"environment contract unmet: missing {missing!r}")

    _build._materialize(d, into, parsed, include_generated=False)
    _rewrite_room_recipe(into, parsed)
    if input_from:
        for name, src in input_from.items():
            dst = _safe(into, name)
            os.makedirs(os.path.dirname(dst) or into, exist_ok=True)
            shutil.copy2(src, dst)

    reused = []
    if produce_from:
        for output, src in produce_from.items():
            if os.path.isfile(src):
                dst = _safe(into, output)
                os.makedirs(os.path.dirname(dst) or into, exist_ok=True)
                shutil.copy2(src, dst)
                reused.append(output)

    before = _snapshot_pinned(parsed, into)
    start = time.time()
    _produce(parsed, into, producer, guidance=guidance, producer_env=producer_env)
    elapsed = time.time() - start
    after = _snapshot_pinned(parsed, into)
    if before != after:
        raise ClaimError("a producer must not rewrite pinned inputs or the recipe")

    usage = _read_usage(into)
    oracle_event = dict(usage)
    oracle_event["event"] = "oracle"
    oracle_event["calls"] = usage.get("calls", 1)
    _run.ledger(into, oracle_event)
    _run.ledger(into, {"event": "timing", "seconds": elapsed})

    env_event = {"event": "environment", **_judging_host()}
    vendor, model = os.environ.get(_ENV_VENDOR), os.environ.get(_ENV_MODEL)
    if vendor or model:
        env_event["vendor"] = vendor
        env_event["model"] = model
        env_event["blind"] = not bool(produce_from)
    _run.ledger(into, env_event)

    for output in reused:
        _run.ledger(into, {"event": "reuse", "output": output})

    quarantine = _run.sandbox_backend()
    gate_rows = []
    for step in _recipe.gates(parsed):
        result = run_gate(step["run"], into, parsed)
        gate_rows.append({"output": step["output"], "status": result["status"],
                           "quarantine": result["quarantine"]})
        _run.ledger(into, {"event": "gate", "output": step["output"],
                            "status": result["status"], "quarantine": result["quarantine"]})
        if result["status"] != "ok":
            raise ClaimError(f"gate {step['output']!r} did not pass: {result['status']}")

    manifest = seal(into)
    return {"root": manifest["root"], "name": manifest["name"],
            "quarantine": quarantine, "gates": gate_rows}


def furnish(d: str, recipe: dict):
    """`run.furnish`, with `cwd` set for the install so a lock file's own
    relative local wheel reference resolves against ITS directory, not
    the caller's. Returns the venv directory, or `None` when the claim
    declares no `[claim] environment`."""
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    env_file = claim.get("environment")
    if not env_file:
        return None
    path = _safe(d, env_file)
    digest = _hash_file(path)
    cache_root = _run._env_cache_dir()
    key = f"{digest}-{platform.python_version()}-{platform.machine()}"
    venv_dir = os.path.join(cache_root, key)
    if os.path.isdir(venv_dir):
        return venv_dir
    os.makedirs(cache_root, exist_ok=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", venv_dir],
            check=True, timeout=_run.FURNISH_TIMEOUT, capture_output=True,
        )
        pip = os.path.join(venv_dir, "bin", "pip")
        subprocess.run(
            [pip, "install", "--require-hashes", "--only-binary=:all:", "-r", path],
            check=True, timeout=_run.FURNISH_TIMEOUT, capture_output=True,
            cwd=os.path.dirname(path) or d,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise ClaimError(f"could not furnish environment from {env_file!r}: {exc}") from exc
    return venv_dir


# =====================================================================
# audit: re-earn cold -- produce_from substitution, environment furnish.
# =====================================================================

def audit(d: str, *, deep: bool = True, produce_from: dict = None) -> dict:
    vr = verify(d)
    if not vr["ok"]:
        return {"ok": False, "verdict": "mismatch", "root": vr["root"], "gates": [], "environment": []}

    parsed = load_recipe(d)
    missing = _run.preflight(parsed)
    if missing:
        gate_rows = [{"output": s["output"], "status": "environment", "quarantine": None}
                     for s in _recipe.gates(parsed)]
        return {"ok": False, "verdict": "environment", "root": vr["root"],
                "gates": gate_rows, "environment": missing}

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    old_path = os.environ.get("PATH")
    venv_dir = None
    try:
        _build._materialize(d, room, parsed, include_generated=True)
        _rewrite_room_recipe(room, parsed)
        if produce_from:
            for output, src in produce_from.items():
                dst = _safe(room, output)
                os.makedirs(os.path.dirname(dst) or room, exist_ok=True)
                shutil.copy2(src, dst)

        claim = parsed.get("claim") or {}
        env_file = claim.get("environment")
        if env_file:
            try:
                _build._copy_rel(d, room, env_file)
                venv_dir = furnish(room, parsed)
            except ClaimError:
                gate_rows = [{"output": s["output"], "status": "environment", "quarantine": None}
                             for s in _recipe.gates(parsed)]
                return {"ok": False, "verdict": "environment", "root": vr["root"],
                        "gates": gate_rows, "environment": ["environment"]}
            if venv_dir:
                os.environ["PATH"] = os.path.join(venv_dir, "bin") + os.pathsep + (old_path or "")

        gate_rows = []
        ok = True
        for step in _recipe.gates(parsed):
            result = run_gate(step["run"], room, parsed)
            status = result["status"]
            if status == "ok" and step.get("class", "pinned") != "generated":
                produced = _safe(room, step["output"])
                reference = _safe(d, step["output"])
                if not _build._compare_pin(produced, reference):
                    status = "mismatch"
            gate_rows.append({"output": step["output"], "status": status,
                               "quarantine": result["quarantine"]})
            if status != "ok":
                ok = False
        return {"ok": ok, "verdict": "ok" if ok else "mismatch", "root": vr["root"],
                "gates": gate_rows, "environment": []}
    finally:
        if venv_dir is not None:
            if old_path is not None:
                os.environ["PATH"] = old_path
            else:
                os.environ.pop("PATH", None)
        shutil.rmtree(room, ignore_errors=True)


# =====================================================================
# sandbox: a functional probe that runs one command and ledgers it.
# =====================================================================

def sandbox(cmd: str, workdir: str):
    try:
        parsed = load_recipe(workdir)
    except ClaimError:
        parsed = None
    result = run_gate(cmd, workdir, parsed)
    _run.ledger(workdir, {"event": "gate", "status": result["status"],
                           "quarantine": result["quarantine"]})
    return (result["status"], result["quarantine"])


# =====================================================================
# independence: declared producer identity, per machine and as a string.
# =====================================================================

def independence(d: str) -> dict:
    for event in reversed(_run.ledger_events(d)):
        if event.get("event") == "environment" and ("vendor" in event or "model" in event):
            return {"vendor": event.get("vendor"), "model": event.get("model"),
                    "blind": event.get("blind")}
    return {"vendor": None, "model": None, "blind": None}


def _independence_string(producer1: dict, producer3: dict) -> str:
    vendor, model, blind = producer3.get("vendor"), producer3.get("model"), producer3.get("blind")
    if not vendor:
        return "unestablished (no producer declared)"
    status = "blind workspace" if blind else "workspace not blind"
    if vendor == producer1.get("vendor") and model == producer1.get("model"):
        note = "same vendor/model as the original, not proven independent"
    else:
        note = "not proven independent"
    return f"declared: {vendor}/{model}, {status} -- {note}"


# =====================================================================
# sign_node: the bottom-anchored signature-chain fold.
# =====================================================================

def sign_node(root_value: str, build_digest_value: str, links: list) -> str:
    payload = {"root": root_value, "build_digest": build_digest_value,
               "links": sorted(set(links))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# =====================================================================
# The record transport, extended to version 2 (`spec/record.md`): the
# recipe's declared obligations, carried so a frozen leg enforces what
# the directory transport would. `attest.py` implements version 1 only
# (its member set has no room for `claim`); the functions below handle
# both versions and delegate everything version-1 already gets right to
# `attest.record_validate` itself, on a `claim`-stripped, version-1-
# relabeled copy of the document.
# =====================================================================

_RECORD_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})


def _validate_claim_obligations(claim) -> None:
    if not isinstance(claim, dict) or not set(claim) <= _RECORD_CLAIM_KEYS:
        raise ClaimError("a record's claim must hold only tolerance/envelope/mutation_floor")
    for key in ("tolerance", "mutation_floor"):
        if key in claim:
            v = claim[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise ClaimError(f"a record's claim.{key} must be a non-negative number")
    if "envelope" in claim:
        env = claim["envelope"]
        if not isinstance(env, dict) or not env:
            raise ClaimError("a record's claim.envelope must be a non-empty object")
        for unit, ceiling in env.items():
            if unit not in COST_LADDER:
                raise ClaimError(f"a record's claim.envelope names an unknown unit: {unit!r}")
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                raise ClaimError("a record's claim.envelope ceiling must be a positive number")


def record_validate(doc) -> None:
    if not isinstance(doc, dict):
        raise ClaimError("a record must be a JSON object")
    version = doc.get("record")
    if version == 1:
        if "claim" in doc:
            raise ClaimError("a record's claim member is refused at version 1")
        _attest.record_validate(doc)
        return
    if version == 2:
        if "claim" not in doc:
            raise ClaimError("a version 2 record requires the claim member")
        _validate_claim_obligations(doc["claim"])
        probe = dict(doc)
        del probe["claim"]
        probe["record"] = 1
        _attest.record_validate(probe)
        return
    raise ClaimError(
        f"record version {version!r} is newer than this kernel understands "
        f"(versions 1, 2); upgrade reticuli to read it"
    )


def record_read(path: str) -> dict:
    """Read and validate a record, refusing a document whose on-disk
    bytes are not its own canonical form -- a record is its canonical
    bytes or it is not a record (`spec/record.md`), so a signature over
    the canonical form still covers exactly the file on disk."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ClaimError(f"no readable record at {path!r}: {exc}") from exc
    record_validate(doc)
    if raw != _attest.record_canonical(doc):
        raise ClaimError(f"record at {path!r} is not its own canonical bytes")
    return doc


def record_digest(doc) -> str:
    return _attest.record_digest(doc)


def record_signer(path: str, anchor: str):
    doc = record_read(path)
    data = _attest.record_canonical(doc)
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path):
        raise ClaimError(f"no detached signature at {sig_path!r}")
    for identity in _attest._allowed_identities(anchor):
        if _build._ssh_verify(anchor, identity, _attest.RECORD_NAMESPACE, data, sig_path):
            return identity
    return None


# =====================================================================
# crosscheck: the three-machine test, over directories and/or records.
# =====================================================================

def _directory_leg(d: str) -> dict:
    vr = verify(d)
    aud = audit(d)
    parsed = load_recipe(d)
    claim = parsed.get("claim") or {}
    obligations = {k: claim[k] for k in ("tolerance", "envelope", "mutation_floor") if k in claim}
    return {
        "root": vr["root"],
        "build_digest": build_digest(d),
        "audited": aud["ok"],
        "cost": _run.cost(d),
        "claim": obligations,
        "claim_known": True,
        "producer": independence(d),
        "dirpath": d,
    }


def _record_leg(path: str) -> dict:
    doc = record_read(path)
    audited = bool(doc["gates"]) and all(g["status"] == "ok" for g in doc["gates"])
    if doc["record"] >= 2:
        obligations, known = doc.get("claim", {}), True
    else:
        obligations, known = {}, False
    producer_doc = doc.get("producer", {})
    return {
        "root": doc["root"],
        "build_digest": doc["build_digest"],
        "audited": audited,
        "cost": doc.get("cost"),
        "claim": obligations,
        "claim_known": known,
        "producer": {"vendor": producer_doc.get("vendor"), "model": producer_doc.get("model"),
                     "blind": producer_doc.get("blind")},
        "dirpath": None,
    }


def _leg_view(path: str) -> dict:
    return _directory_leg(path) if os.path.isdir(path) else _record_leg(path)


def _strongest_shared_unit(c1: dict, c3: dict):
    for unit in COST_LADDER:
        if unit in c1 and unit in c3:
            return unit
    return None


def _cost_band(c1, c3, tolerance: float):
    c1, c3 = c1 or {}, c3 or {}
    unit = _strongest_shared_unit(c1, c3)
    if unit is None or c1[unit] <= 0:
        return None
    ratio = c3[unit] / c1[unit]
    return (1.0 / tolerance) <= ratio <= tolerance


def _envelope_report(envelope: dict, c3) -> dict:
    c3 = c3 or {}
    report = {}
    for unit, ceiling in envelope.items():
        measured = c3.get(unit)
        if measured is None:
            report[unit] = {"within": None, "ceiling": ceiling, "measured": None}
        else:
            report[unit] = {"within": measured <= ceiling, "ceiling": ceiling, "measured": measured}
    return report


def crosscheck(m1: str, m2: str, m3: str, *, mutants: int = None) -> dict:
    resolved = []
    for leg in (m1, m2, m3):
        try:
            resolved.append(os.path.realpath(leg))
        except OSError:
            resolved.append(str(leg))
    if len(set(resolved)) < 3:
        raise ClaimError("crosscheck requires three distinct machines; "
                          "a claim compared against itself proves nothing")

    v1, v2, v3 = _leg_view(m1), _leg_view(m2), _leg_view(m3)

    roots = {"M1": v1["root"], "M2": v2["root"], "M3": v3["root"]}
    equivalence = len(set(roots.values())) == 1
    audited = {"M1": v1["audited"], "M2": v2["audited"], "M3": v3["audited"]}
    reuse = v1["build_digest"] == v2["build_digest"]

    rejected, incomplete = [], []
    if not equivalence:
        rejected.append("roots")
    for key in ("M1", "M2", "M3"):
        if not audited[key]:
            rejected.append(f"audited:{key}")
    if not reuse:
        rejected.append("reuse")

    if not v1["claim_known"]:
        incomplete.append("declared conditions (v1 record)")

    declared = v1["claim"]
    tol_declared = declared.get("tolerance") is not None
    tolerance = declared.get("tolerance") if tol_declared else TOLERANCE
    comparable = _cost_band(v1["cost"], v3["cost"], tolerance)
    if tol_declared:
        if comparable is None:
            incomplete.append("tolerance")
        elif comparable is False:
            rejected.append("tolerance")

    env_report = _envelope_report(declared.get("envelope") or {}, v3["cost"])
    for unit, info in env_report.items():
        if info["within"] is None:
            incomplete.append(f"envelope {unit}")
        elif info["within"] is False:
            rejected.append(f"envelope {unit}")

    mutation_floor = declared.get("mutation_floor")
    mutation_result = None
    if mutation_floor is not None:
        if mutants is None or v3["dirpath"] is None:
            incomplete.append("mutation_floor")
        else:
            mutation_result = mutation_score(v3["dirpath"], max_mutants=mutants, floor=mutation_floor)
            if not mutation_result["ok"]:
                rejected.append("mutation_floor")

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
        "roots": roots,
        "equivalence": equivalence,
        "audited": audited,
        "reuse": reuse,
        "independence": _independence_string(v1["producer"], v3["producer"]),
        "cost": {"comparable": comparable, "envelope": env_report},
        "mutation_score": mutation_result,
    }


def record_proof(m1: str, m2: str, m3: str) -> dict:
    if not os.path.isdir(m1):
        raise ClaimError("a recorded proof must land on a directory (M1)")
    result = crosscheck(m1, m2, m3)
    if not result["satisfied"]:
        return {"proof_recorded": False}

    anchor = os.environ.get(_ENV_SIGNERS)
    records_trail = []
    for label, leg in (("M2", m2), ("M3", m3)):
        if os.path.isdir(leg):
            continue
        if not anchor or not os.path.isfile(anchor):
            raise ClaimError(f"a proof from an unanchored record ({label}) must refuse")
        doc = record_read(leg)
        identity = record_signer(leg, anchor)
        if identity is None:
            raise ClaimError(f"a proof from an unanchored record ({label}) must refuse")
        records_trail.append({"digest": record_digest(doc), "signer": identity})

    proof = {"kind": "crosscheck", "roots": result["roots"]}
    if records_trail:
        proof["records"] = records_trail

    manifest = _read_manifest(m1)
    manifest["proof"] = proof
    _write_json(os.path.join(m1, MANIFEST), manifest)
    return {"proof_recorded": True, "proof": proof}
