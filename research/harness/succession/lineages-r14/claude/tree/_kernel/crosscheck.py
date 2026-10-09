"""The three-machine test, mutation score, signing, and the verb layer that
composes the lower kernel modules (spec/verification.md, spec/record.md).

This module is the integration point above core/recipe/identity/seal/run/
build/attest: it adds the behavior those modules leave to a caller --
`[claim] environment` as an automatically pinned input, `requires` checked
before a rebuild or an audit, tamper detection on a producer's room,
raise-on-failure verb semantics, and the three-machine test itself (which
may take a claim directory or a frozen record on any leg). It also hosts a
small deterministic mutation-testing engine: token- and AST-level mutants of
a claim's generated Python sources, drawn in an order seeded by the claim's
own root, so the sample is reproducible without being guessable in advance.
Stdlib only, never the network.
"""
import ast
import collections
import hashlib
import io
import json
import os
import platform
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
import tomllib

from . import core
from . import identity as _identity
from . import recipe as _recipe
from . import seal as _seal
from . import run as _run_mod
from . import build as _build
from . import attest as _attest
from .core import ClaimError

# ===========================================================================
# shell-command parsing: which files decide a gate (spec/claim-format.md:
# vacuous gates)
# ===========================================================================

_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2',
                           'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh',
                           'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})

_OP_SPLIT = re.compile("|".join(re.escape(op) for op in sorted(_OPERATORS, key=len, reverse=True)))


def _split_shell(run: str) -> list:
    """`run` split into subcommands on `_OPERATORS`."""
    return [s for s in _OP_SPLIT.split(run) if s.strip()]


def _scan_args(tokens: list) -> list:
    """Non-flag arguments: a flag in `_SKIP_VALUE` also consumes the token
    that follows it (its value, never a decider)."""
    result = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in _SKIP_VALUE:
            skip_next = True
            continue
        if tok.startswith("-"):
            continue
        result.append(tok)
    return result


def gate_deciders(run: str) -> list:
    """Which workspace files decide a gate command: the script named after a
    recognized interpreter, or a bare `./file` invocation. A subcommand that
    is neither (a plain builtin like `printf`) names no decider."""
    deciders = []
    for sub in _split_shell(run):
        try:
            tokens = shlex.split(sub)
        except ValueError:
            continue
        if not tokens:
            continue
        head, rest = tokens[0], tokens[1:]
        if head in _INTERPRETERS:
            deciders.extend(_scan_args(rest))
        elif head.startswith("./"):
            deciders.append(head.lstrip("./"))
    return deciders


def _in_band() -> bool:
    """Is this process already running inside a sandbox? `run.py`'s own
    `_in_band` only recognizes its literal `"1"`; the execution contract
    requires the signal to carry the backend's NAME (so a wrapped gate can
    say which jail it inherited), so the check here is any truthy value."""
    return bool(os.environ.get(core._JAILED))


def sandbox_backend() -> str:
    """Which quarantine actually applies here: `inherited` when already
    jailed, else the first platform sandbox that probes functional, else
    `none`."""
    if _in_band():
        return "inherited"
    if sys.platform == "darwin" and _run_mod._seatbelt_usable():
        return "seatbelt"
    if sys.platform.startswith("linux") and _run_mod._bwrap_usable():
        return "bubblewrap"
    return "none"


def _scrub_env(d: str, backend: str) -> dict:
    """A minimal host allowlist plus the claim's own scratch, with
    `RETICULI_JAILED` carrying the BACKEND NAME -- the sending half of the
    execution contract: a kernel that applies a sandbox must tell the
    wrapped process which one, so a gate that is itself a claim runner
    inherits instead of nesting."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    scratch = os.path.join(d, core.STORE, "scratch")
    os.makedirs(scratch, exist_ok=True)
    env["HOME"] = scratch
    env["TMPDIR"] = scratch
    env[core._JAILED] = backend
    return env


def run_gate(command: str, d: str, recipe=None) -> dict:
    """Run one gate command in `d`: scrubbed environment, sandboxed,
    bounded. Reimplements `run.run_gate`'s wiring with the corrected
    `RETICULI_JAILED` signal (see `_scrub_env`)."""
    timeout = _run_mod.gate_timeout(recipe)
    backend = sandbox_backend()
    env = _scrub_env(d, backend)
    argv = _run_mod._sandbox_argv(command, d, backend)
    result = _run_mod._run(argv, d, env, timeout)
    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend, "returncode": result["returncode"],
            "stdout": result["stdout"], "stderr": result["stderr"]}


def vacuous_gates(recipe: dict) -> list:
    """Gates whose every decider is itself a `generated` output -- the
    verdict depends on no claim (spec/claim-format.md)."""
    generated = set(_recipe.generated_outputs(recipe))
    vacuous = []
    for step in _recipe.gates(recipe):
        deciders = gate_deciders(step.get("run", ""))
        if deciders and all(dec in generated for dec in deciders):
            vacuous.append(step["output"])
    return vacuous


# ===========================================================================
# the mutation-testing engine: deterministic mutants of generated Python,
# drawn from the claim's root (spec/verification.md: mutation_floor)
# ===========================================================================

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_WORD_ALTS = {'and': 'or', 'or': 'and', 'True': 'False', 'False': 'True'}

_SIMPLE_ALT = {'+': '-', '-': '+', '*': '/', '/': '*', '//': '/', '%': '*',
               '<': '<=', '>': '>=', '<=': '<', '>=': '>', '==': '!=', '!=': '=='}

_OP_ALTS = {}
for _op in _ARITHMETIC:
    _OP_ALTS[_op] = (_SIMPLE_ALT[_op],)
for _op in _COMPARISON:
    _OP_ALTS.setdefault(_op, (_SIMPLE_ALT.get(_op, _op),))
for _w, _alt in _WORD_ALTS.items():
    _OP_ALTS[_w] = (_alt,)

_OP_KIND = {}
for _op in _ARITHMETIC:
    _OP_KIND[_op] = "arithmetic"
for _op in _COMPARISON:
    _OP_KIND[_op] = "comparison"
for _w in _WORD_ALTS:
    _OP_KIND[_w] = "boolean" if _w in ("and", "or") else "literal"

_STRING_LITERAL = re.compile(
    r"(?s)('''.*?'''|\"\"\".*?\"\"\"|'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
)

_Mutant = collections.namedtuple("_Mutant", ["span", "old", "new", "kind"])


def _named(span, old, new, kind):
    """A hashable, orderable mutation candidate."""
    return _Mutant(span, old, new, kind)


def _node_span(lines: list, node) -> tuple:
    """The character span of an AST `node` within the source whose lines
    (with line endings) are `lines`."""
    start = sum(len(l) for l in lines[: node.lineno - 1]) + node.col_offset
    end = sum(len(l) for l in lines[: node.end_lineno - 1]) + node.end_col_offset
    return (start, end)


def _span_text(source: str, span: tuple) -> str:
    return source[span[0]:span[1]]


def _splice(source: str, span: tuple, replacement: str) -> str:
    return source[:span[0]] + replacement + source[span[1]:]


def _edit(source: str, mutant) -> str:
    """Apply one mutation candidate to `source`."""
    return _splice(source, mutant.span, mutant.new)


def _label(mutant) -> str:
    """A human-readable identity for a mutation candidate (residue only;
    the element type of the survivor list is not pinned)."""
    return f"{mutant.kind}:{mutant.old}->{mutant.new}@{mutant.span[0]}"


def _overlaps(span: tuple, spans: list) -> bool:
    return any(not (span[1] <= s or span[0] >= e) for s, e in spans)


def _docstring_spans(tree, source: str) -> list:
    """Spans of every module/class/function docstring literal -- excluded
    from mutation, since rewording one never changes behavior."""
    lines = source.splitlines(keepends=True)
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                spans.append(_node_span(lines, body[0]))
    return spans


def _token_mutants(source: str) -> list:
    """Operator/word-level mutation candidates, found by tokenizing (so
    string and comment contents are never mistaken for code) and excluding
    docstrings and any other string literal."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    excluded = _docstring_spans(tree, source) + [m.span() for m in _STRING_LITERAL.finditer(source)]
    lines = source.splitlines(keepends=True)
    offsets, total = [], 0
    for l in lines:
        offsets.append(total)
        total += len(l)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenizeError, IndentationError, SyntaxError):
        return []
    candidates = []
    for tok in toks:
        if tok.type not in (tokenize.OP, tokenize.NAME):
            continue
        alts = _OP_ALTS.get(tok.string)
        if not alts:
            continue
        start = offsets[tok.start[0] - 1] + tok.start[1]
        end = offsets[tok.end[0] - 1] + tok.end[1]
        span = (start, end)
        if _overlaps(span, excluded):
            continue
        for alt in alts:
            candidates.append(_named(span, tok.string, alt, _OP_KIND.get(tok.string, "token")))
    return candidates


def _structural_mutants(source: str, tree) -> list:
    """AST-level mutation candidates: numeric literals perturbed by one."""
    lines = source.splitlines(keepends=True)
    excluded = _docstring_spans(tree, source)
    candidates = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            span = _node_span(lines, node)
            if _overlaps(span, excluded):
                continue
            old = _span_text(source, span)
            candidates.append(_named(span, old, repr(node.value + 1), "constant"))
    return candidates


def _mutant_order(mutants: list) -> list:
    """A stable order over candidates, independent of discovery order."""
    return sorted(mutants, key=lambda m: (m.span[0], m.span[1], m.kind, m.old, m.new))


def _mutants(source: str) -> list:
    """Every mutation candidate for one source file, stably ordered."""
    tree = ast.parse(source)
    return _mutant_order(_token_mutants(source) + _structural_mutants(source, tree))


def _machine(seed) -> random.Random:
    """The deterministic generator mutants are drawn from -- seeded by the
    claim's own root, so the sample is reproducible, never guessable from
    the claim's criteria alone."""
    return random.Random(seed)


def _draw_order(seed, count: int, k: int) -> list:
    """`k` indices out of `range(count)`, in draw order, seeded by `seed`."""
    rng = _machine(seed)
    idx = list(range(count))
    rng.shuffle(idx)
    return idx[:k]


def mutation_score(d: str, max_mutants: int = core.MUTANT_CEILING) -> dict:
    """Mutate `d`'s generated Python outputs, deterministically drawn from
    the sealed root, and measure how many the gates kill. Residue only."""
    parsed = load_recipe(d)
    manifest = _seal.read_manifest(d)
    seed = manifest["root"]

    pool, sources = [], {}
    for output in sorted(_recipe.generated_outputs(parsed)):
        if not output.endswith(".py"):
            continue
        full = core._safe(d, output)
        if not os.path.isfile(full):
            continue
        with open(full, "r", encoding="utf-8") as f:
            text = f.read()
        sources[output] = text
        try:
            candidates = _mutants(text)
        except SyntaxError:
            continue
        pool.extend((output, m) for m in candidates)

    total = len(pool)
    k = min(total, max_mutants)
    sample = [pool[i] for i in _draw_order(seed, total, k)] if total else []

    survivors, killed = [], 0
    for output, mutant in sample:
        room = tempfile.mkdtemp(prefix="reticuli-mutant-")
        try:
            _build._materialize(d, parsed, room, include_generated=True)
            mutated = _edit(sources[output], mutant)
            with open(core._safe(room, output), "w", encoding="utf-8") as f:
                f.write(mutated)
            earned = True
            for step in _recipe.gates(parsed):
                res = run_gate(step["run"], room, parsed)
                if res["status"] != "ok":
                    earned = False
                    break
            if earned:
                survivors.append(_label(mutant))
            else:
                killed += 1
        finally:
            shutil.rmtree(room, ignore_errors=True)

    rate = (killed / k) if k else 0.0
    floor = parsed.get("claim", {}).get("mutation_floor")
    result = {"mutants": k, "killed": killed, "rate": rate, "survivors": survivors,
              "ok": True if floor is None else rate >= floor}
    core._write_json(os.path.join(d, core.MUTATION_RESIDUE), result)
    return result


# ===========================================================================
# the recipe's `[claim]` extras: envelope / tolerance / mutation_floor
# (spec/claim-format.md -- validated here, on top of recipe.py's own rules)
# ===========================================================================

def _validate_claim_extras(parsed: dict) -> None:
    claim = parsed.get("claim", {})

    envelope = claim.get("envelope")
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("[claim] envelope must be a non-empty table")
        for unit, ceiling in envelope.items():
            if unit not in core.COST_UNITS:
                raise ClaimError(f"[claim] envelope unit {unit!r} is unknown")
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                raise ClaimError(f"[claim] envelope.{unit} must be a positive number")

    tolerance = claim.get("tolerance")
    if tolerance is not None:
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance <= 0:
            raise ClaimError("[claim] tolerance must be a positive number")

    mutation_floor = claim.get("mutation_floor")
    if mutation_floor is not None:
        if isinstance(mutation_floor, bool) or not isinstance(mutation_floor, (int, float)) or mutation_floor < 0:
            raise ClaimError("[claim] mutation_floor must be a non-negative number")


def _check_no_dotdot(path, what: str) -> None:
    """Refuse a raw declared path with a `..` component. `core._safe`
    resolves via `os.path.normpath`, which COLLAPSES `a/../b` to `b` before
    its own `..`-component check ever sees it -- so `real/../g.txt` reads
    as plain `g.txt` and a path that only LOOKS confined slips through.
    Checked here against the recipe's own (unnormalized) string."""
    if path is None:
        return
    if any(part == ".." for part in str(path).split("/")):
        raise ClaimError(f"refused {what}: {path!r} contains a '..' component")


def _parse_recipe_doc(d: str) -> dict:
    """Parse and validate `d`'s recipe (spec/claim-format.md), confining
    every declared path EXCEPT a `generated` step's own output. A
    `generated` output is outside the root and may not even exist yet at
    parse time; confinement for it is enforced where its bytes are actually
    read -- materializing a room (audit, rebuild) -- not here. (The lower
    `recipe.load_recipe` confines every step output unconditionally, which
    refuses `seal` on a claim whose generated output happens to be a
    symlink, when only a later `audit` should.)"""
    path = _recipe.recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ClaimError(f"recipe {path!r} is not valid UTF-8: {e}") from e
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e

    claim = doc.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} is missing a [claim] table")
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

    inputs = claim.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
            raise ClaimError("[claim] inputs must be a list of strings")
        for p in inputs:
            _check_no_dotdot(p, "input path")
            core._safe(d, p)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        _check_no_dotdot(manifest, "inputs_manifest path")
        core._safe(d, manifest)

    env_file = claim.get("environment")
    if env_file is not None:
        if not isinstance(env_file, str):
            raise ClaimError("[claim] environment must be a string")
        _check_no_dotdot(env_file, "environment path")
        core._safe(d, env_file)

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError(f"recipe {path!r}: [[step]] must be an array of tables")

    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError(f"recipe {path!r}: each step must be a table")

        kind = step.get("kind")
        if kind not in core.KINDS:
            raise ClaimError(
                f"recipe {path!r}: step kind must be one of "
                f"{sorted(core.KINDS)}, got {kind!r}"
            )

        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"recipe {path!r}: every step needs an 'output'")
        _check_no_dotdot(output, "step output path")
        cls = step.get("class")
        if cls is None:
            cls = "generated" if kind == "produce" else "pinned"
        if cls != "generated":
            core._safe(d, output)

        if kind == "gate":
            run = step.get("run")
            if not isinstance(run, str) or not run:
                raise ClaimError(f"recipe {path!r}: a gate step needs a 'run' command")

        source = step.get("from")
        if source is not None:
            if not isinstance(source, str) or not source:
                raise ClaimError(f"recipe {path!r}: a step's 'from' must be a string")
            _check_no_dotdot(source, "step from path")
            core._safe(d, source)

    return doc


def load_recipe(d: str) -> dict:
    """Parse and validate `d`'s recipe, including the `[claim]` extras and
    the confinement/`..` rules the lower recipe parser leaves incomplete
    (see `_parse_recipe_doc`, `_check_no_dotdot`)."""
    parsed = _parse_recipe_doc(d)
    _validate_claim_extras(parsed)
    return parsed


# ===========================================================================
# identity: `[claim] environment` is automatically a pinned input
# ===========================================================================

def _parts_with_environment(parsed: dict, d: str) -> dict:
    parts = _identity._parts(parsed, d)
    env_file = parsed.get("claim", {}).get("environment")
    if env_file and f"input:{env_file}" not in parts:
        parts[f"input:{env_file}"] = _identity._hashed(d, env_file)
    return parts


def root(recipe: dict, d: str) -> str:
    """The claim's identity (spec/identity.md), with the declared
    `environment` file folded in as a pinned input."""
    parts = _parts_with_environment(recipe, d)
    return _identity._sha256_text(_identity._canonical_json(parts))


def build_digest(d: str) -> str:
    return _identity.build_digest(d)


# ===========================================================================
# seal / verify / phase: identity only, raise on anything that prevents
# recomputing it at all (spec/verification.md)
# ===========================================================================

def seal(d: str) -> dict:
    parsed = load_recipe(d)
    name = parsed.get("claim", {}).get("name")
    parts = _parts_with_environment(parsed, d)
    computed = _identity._sha256_text(_identity._canonical_json(parts))
    manifest = {"name": name, "root": computed}
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    core._write_json(os.path.join(d, _seal._PARTS_RESIDUE), parts)
    return manifest


def read_manifest(d: str) -> dict:
    """`_seal.read_manifest`, but refusing non-UTF-8 bytes in band too (the
    lower reader only catches a bad JSON parse, not a bad decode)."""
    try:
        return _seal.read_manifest(d)
    except UnicodeDecodeError as e:
        raise ClaimError(f"malformed manifest in {d!r}: not valid UTF-8: {e}") from e


def verify(d: str) -> dict:
    """Recompute `d`'s root and compare it with the sealed manifest. Any
    refusal that prevents recomputing at all (a missing/escaping input, a
    corrupt manifest or recipe) raises; a legitimate recomputation that
    simply differs is reported as an ordinary mismatch."""
    manifest = read_manifest(d)
    parsed = load_recipe(d)
    parts = _parts_with_environment(parsed, d)
    recomputed = _identity._sha256_text(_identity._canonical_json(parts))
    ok = recomputed == manifest["root"]
    result = {"ok": ok, "root": manifest["root"], "recomputed": recomputed,
              "name": manifest.get("name")}
    if not ok:
        result["changed"] = _seal._changed_parts(_seal._read_parts_residue(d), parts)
    return result


def phase(d: str) -> str:
    """`draft` / `sealed` / `signed` (spec/verification.md)."""
    manifest_path = os.path.join(d, core.MANIFEST)
    if not os.path.isfile(manifest_path):
        load_recipe(d)
        return "draft"

    manifest = read_manifest(d)
    v = verify(d)
    if not v["ok"]:
        raise ClaimError(f"claim at {d!r} does not verify against its sealed manifest")

    proof = manifest.get("proof")
    if not proof:
        return "sealed"

    signers_file = os.environ.get(core._ENV_SIGNERS)
    if not signers_file or not os.path.isfile(signers_file):
        return "sealed"

    sign_dir = os.path.join(d, core.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return "sealed"

    current_root = v["root"]
    current_digest = build_digest(d)

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
        if not isinstance(stmt, dict):
            continue

        identity = stmt.get("identity")
        if not _build._ssh_verify(stmt_bytes, sig_path, core.SIGN_NAMESPACE, signers_file, identity):
            continue
        if not stmt.get("proof_recorded"):
            continue
        if stmt.get("root") != current_root:
            continue

        packet_name = fname[: -len(".sign.json")] + ".packet.json"
        packet_path = os.path.join(sign_dir, packet_name)
        try:
            with open(packet_path, "rb") as f:
                packet_bytes = f.read()
        except OSError:
            continue
        if hashlib.sha256(packet_bytes).hexdigest() != stmt.get("packet_digest"):
            continue
        try:
            packet = json.loads(packet_bytes)
        except json.JSONDecodeError:
            continue
        if not isinstance(packet, dict):
            continue
        if packet.get("root") != current_root or packet.get("build_digest") != current_digest:
            continue
        if not packet.get("proof"):
            continue
        return "signed"

    return "sealed"


# ===========================================================================
# sign_node: the signature-chain fold (spec/claim-format.md)
# ===========================================================================

def record_read(path: str) -> dict:
    """Parse and validate the record at `path`, additionally refusing a
    file whose bytes are not its OWN canonical serialization -- a record is
    its canonical bytes or it is not a record (`attest.record_read` parses
    any valid JSON structurally and does not check this)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read record {path!r}: {e}") from e
    doc = _attest.record_read(path)
    if _attest.record_canonical(doc) != raw:
        raise ClaimError(f"record {path!r} is not its own canonical bytes")
    return doc


def sign_node(root_value: str, digest: str, links) -> str:
    """A deterministic fold over a layer's root, build digest, and the
    signatures beneath it -- order-independent over the set of links."""
    payload = {"root": root_value, "build_digest": digest, "links": sorted(set(links))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ===========================================================================
# audit: trust nothing already on record (spec/verification.md)
# ===========================================================================

def _gate_entries_for(parsed: dict, status: str) -> list:
    return [{"output": s["output"], "status": status, "quarantine": None}
            for s in _recipe.gates(parsed)]


def furnish(d: str, path: str) -> str:
    """Build (or reuse) a private venv from a hash-pinned requirements file;
    return its `bin` directory. Reimplements `run.furnish`'s wiring with the
    install run in the CLAIM's own directory: `run.furnish` omits `cwd`, so
    pip resolves a relative wheel path (e.g. `./probe-1.0-....whl`) against
    the caller's cwd rather than the requirements file's own directory, and
    furnishing fails with "file does not exist" whenever those differ."""
    full = core._safe(d, path)
    try:
        digest = core._hash_file(full)
    except OSError as e:
        raise ClaimError(f"cannot read environment file {path!r}: {e}") from e

    key = "-".join([digest, platform.python_implementation(), platform.python_version(),
                     sys.platform, platform.machine()])
    venv_dir = os.path.join(_run_mod._env_cache_dir(), key)
    bin_dir = os.path.join(venv_dir, "bin")
    if os.path.isdir(bin_dir):
        return bin_dir

    try:
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True,
                        capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
        subprocess.run(
            [os.path.join(bin_dir, "python3"), "-m", "pip", "install",
             "--require-hashes", "--only-binary=:all:", "-r", full],
            check=True, capture_output=True, text=True,
            timeout=core.FURNISH_TIMEOUT, cwd=d)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise ClaimError(f"could not furnish environment from {path!r}: {e}") from e
    return bin_dir


def audit(d: str, produce_from: dict = None, shallow: bool = False) -> dict:
    """Re-earn every gate of `d`, cold (spec/verification.md). Supports
    judging SUBSTITUTED generated bytes (`produce_from`) -- how a
    dependent's shipped code is re-earned by its component's check."""
    parsed = load_recipe(d)
    verified = verify(d)
    if not verified["ok"]:
        return {"ok": False, "verdict": "mismatch", "gates": [], "root": verified["root"]}

    missing = _run_mod.preflight(parsed)
    if missing:
        return {"ok": False, "verdict": "environment",
                "gates": _gate_entries_for(parsed, "environment"),
                "root": verified["root"], "environment": missing}

    bin_dir = None
    env_file = parsed.get("claim", {}).get("environment")
    if env_file:
        try:
            bin_dir = furnish(d, env_file)
        except ClaimError:
            return {"ok": False, "verdict": "environment",
                    "gates": _gate_entries_for(parsed, "environment"),
                    "root": verified["root"], "environment": [env_file]}

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        _build._materialize(d, parsed, room, include_generated=True)
        if produce_from:
            for output, src in produce_from.items():
                target = core._safe(room, output)
                os.makedirs(os.path.dirname(target) or room, exist_ok=True)
                shutil.copy2(src, target)

        gate_results = []
        earned = True
        for step in _recipe.gates(parsed):
            run_cmd = step["run"]
            if bin_dir:
                run_cmd = f'PATH="{bin_dir}:$PATH" ' + run_cmd
            res = run_gate(run_cmd, room, parsed)
            status = res["status"]
            if status == "ok" and step.get("class", "pinned") != "generated":
                if not _build._compare_pin(d, room, step["output"]):
                    status = "mismatch"
            gate_results.append({"output": step["output"], "status": status,
                                  "quarantine": res["quarantine"]})
            if status != "ok":
                earned = False
        return {"ok": earned, "verdict": "earned" if earned else "broken",
                "gates": gate_results, "root": verified["root"]}
    finally:
        shutil.rmtree(room, ignore_errors=True)


# ===========================================================================
# the producer: a scrubbed room, never the caller's whole environment
# (spec/kernel-api.md: `rebuild`'s `guidance`/`producer_env`)
# ===========================================================================

def _produce(command: str, room: str, outputs, step: dict, parsed: dict,
             guidance: bool = True, producer_env: dict = None) -> dict:
    """Run `command` once in `room` to earn `step`'s output. Unlike
    `build._produce`, the producer does NOT inherit the caller's whole
    environment: an inherited credential reaches it only if the caller
    deliberately hands it over via `producer_env` -- the only road one may
    travel (what the caller does not hand over never arrives)."""
    env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env[core._ENV_OUTPUT] = os.path.join(os.path.realpath(room), step.get("output"))
    env[core._ENV_OUTPUTS] = json.dumps(list(outputs))
    if guidance:
        hint = _build._step_guidance(step)
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
                "usage": _build._read_usage(env[core._ENV_USAGE])}
    except subprocess.TimeoutExpired as e:
        return {"returncode": None, "stdout": e.stdout or "", "stderr": e.stderr or "",
                "seconds": time.time() - start, "usage": {}}


# ===========================================================================
# rebuild: regrow, judge, seal -- raises on any failure (timeout, mismatch,
# tamper, missing environment), returns normally only on a pass
# ===========================================================================

def rebuild(d: str, producer: str, into: str, produce_from: dict = None,
            input_from: dict = None, guidance: bool = True,
            producer_env: dict = None) -> dict:
    parsed = load_recipe(d)

    missing = _run_mod.preflight(parsed)
    if missing:
        raise ClaimError(f"environment: host is missing {sorted(missing)}")

    if os.path.exists(into):
        if os.listdir(into):
            raise ClaimError(f"refuses to rebuild into a non-empty directory: {into!r}")
    else:
        os.makedirs(into)

    if not _build._authorized(d, parsed):
        raise ClaimError("producer is not authorized for this claim")

    _build._materialize(d, parsed, into, include_generated=False)
    if input_from:
        for name, src in input_from.items():
            target = core._safe(into, name)
            os.makedirs(os.path.dirname(target) or into, exist_ok=True)
            shutil.copy2(src, target)
    os.makedirs(os.path.join(into, core.STORE), exist_ok=True)

    # snapshot pinned bytes and the recipe itself: a producer may not
    # rewrite either (a producer cannot change the question)
    pinned_paths = list(_recipe._inputs(d, parsed))
    recipe_rel = os.path.basename(_recipe.recipe_path(into))
    snapshot = {}
    for p in pinned_paths + [recipe_rel]:
        full = core._safe(into, p)
        if os.path.isfile(full):
            snapshot[p] = core._hash_file(full)

    generated_steps = [s for s in _recipe.produces(parsed)
                        if s.get("class", "generated") == "generated" and not s.get("from")]
    all_outputs = [s["output"] for s in generated_steps]

    for step in generated_steps:
        output = step["output"]
        if produce_from and output in produce_from:
            carried = produce_from[output]
            if os.path.isfile(carried):
                target = core._safe(into, output)
                os.makedirs(os.path.dirname(target) or into, exist_ok=True)
                shutil.copy2(carried, target)
                _run_mod.ledger(into, {"event": "reuse", "output": output})
                continue

        result = _produce(producer, into, all_outputs, step, parsed, guidance, producer_env)
        entry = {"kind": "produce", "output": output, "seconds": result["seconds"], "calls": 1}
        entry.update(result.get("usage") or {})
        entry.update(core._judging_host())
        _run_mod.ledger(into, entry)
        if result["returncode"] != 0:
            raise ClaimError(f"producer failed for {output!r}: {(result['stderr'] or '')[-500:]}")

    for p, old_hash in snapshot.items():
        full = core._safe(into, p)
        if not os.path.isfile(full) or core._hash_file(full) != old_hash:
            raise ClaimError(f"producer rewrote pinned bytes: {p!r}")

    gate_results = []
    quarantine = None
    ok = True
    for step in _recipe.gates(parsed):
        res = run_gate(step["run"], into, parsed)
        quarantine = res["quarantine"]
        gate_results.append({"output": step["output"], "status": res["status"],
                              "quarantine": quarantine})
        _run_mod.ledger(into, {"kind": "gate", "output": step["output"],
                               "status": res["status"], "quarantine": quarantine})
        if res["status"] != "ok":
            ok = False

    env_entry = {"event": "environment", "python": platform.python_version(),
                 "quarantine": quarantine}
    env_entry.update(core._judging_host())
    _run_mod.ledger(into, env_entry)

    if not ok:
        raise ClaimError(f"rebuild's gate did not earn: {gate_results!r}")

    manifest = seal(into)

    vendor = os.environ.get(core._ENV_VENDOR)
    model = os.environ.get(core._ENV_MODEL)
    if vendor or model:
        _run_mod.ledger(into, {"event": "independence", "vendor": vendor,
                               "model": model, "blind": True})

    return {"ok": True, "root": manifest["root"], "verdict": "ok",
            "gates": gate_results, "quarantine": quarantine}


# ===========================================================================
# independence: declared, never enforced (spec/verification.md)
# ===========================================================================

def independence(d: str) -> dict:
    """The producer independence declared on `d`'s ledger, if any."""
    events = [e for e in _run_mod.ledger_events(d) if e.get("event") == "independence"]
    if not events:
        return {"vendor": None, "model": None, "blind": None}
    last = events[-1]
    return {"vendor": last.get("vendor"), "model": last.get("model"), "blind": last.get("blind")}


def _independence_string(declared: dict) -> str:
    vendor, model, blind = declared.get("vendor"), declared.get("model"), declared.get("blind")
    if vendor and model:
        workspace = "blind workspace" if blind else "workspace"
        return f"declared: {vendor}/{model}, {workspace} (not proven)"
    return f"unestablished: no producer declaration recorded"


# ===========================================================================
# crosscheck: the three-machine test, over directories or frozen records
# (spec/verification.md, spec/record.md)
# ===========================================================================

def _leg_kind(leg: str) -> str:
    return "dir" if os.path.isdir(leg) else "record"


def _leg_root_digest(leg: str):
    if _leg_kind(leg) == "dir":
        return read_manifest(leg)["root"], build_digest(leg)
    doc = record_read(leg)
    return doc["root"], doc["build_digest"]


def _leg_audited(leg: str) -> bool:
    if _leg_kind(leg) == "dir":
        return audit(leg)["ok"]
    doc = record_read(leg)
    return bool(doc.get("gates")) and all(g.get("status") == "ok" for g in doc["gates"])


def _leg_cost(leg: str):
    if _leg_kind(leg) == "dir":
        return _run_mod.cost(leg)
    doc = record_read(leg)
    return doc.get("cost")


def _leg_declared(leg: str):
    """The recipe's declared obligations relayed by `leg`; `None` means
    unknown (a version-1 record), never "none declared"."""
    if _leg_kind(leg) == "dir":
        parsed = load_recipe(leg)
        claim = parsed.get("claim", {})
        return {k: claim[k] for k in ("tolerance", "envelope", "mutation_floor") if k in claim}
    doc = record_read(leg)
    if doc.get("record", 1) < 2:
        return None
    return doc.get("claim", {})


def _leg_independence(leg: str) -> dict:
    if _leg_kind(leg) == "dir":
        return independence(leg)
    doc = record_read(leg)
    producer = doc.get("producer") or {}
    return {"vendor": producer.get("vendor"), "model": producer.get("model"),
            "blind": producer.get("blind")}


def _cost_band(cost1, cost3, tolerance) -> dict:
    """The strongest unit both machines measured decides (usd > tokens >
    calls > seconds); a weaker shared unit may never veto it."""
    tol = tolerance if tolerance is not None else core.TOLERANCE
    if not cost1 or not cost3:
        return {"comparable": None}
    for unit in core.COST_LADDER:
        if unit in cost1 and unit in cost3:
            c1v, c3v = cost1[unit], cost3[unit]
            if not c1v:
                return {"comparable": None, "unit": unit}
            ratio = c3v / c1v
            within = (1.0 / tol) <= ratio <= tol
            return {"comparable": within, "unit": unit, "ratio": ratio}
    return {"comparable": None}


def _envelope_check(cost3, envelope: dict) -> dict:
    result = {}
    for unit, ceiling in envelope.items():
        if not cost3 or unit not in cost3:
            result[unit] = {"ceiling": ceiling, "within": None}
        else:
            result[unit] = {"ceiling": ceiling, "within": cost3[unit] <= ceiling,
                             "measured": cost3[unit]}
    return result


def crosscheck(m1: str, m2: str, m3: str, mutants: int = None) -> dict:
    """The three-machine test (spec/verification.md). Each leg is a claim
    directory or a frozen record file; the verdict is `accept`, `reject`,
    or `incomplete` -- a hard condition the claim declared but this run
    never measured is incomplete, never a silent accept."""
    legs = {"M1": m1, "M2": m2, "M3": m3}
    idents = {k: os.path.realpath(v) for k, v in legs.items()}
    if len(set(idents.values())) < 3:
        raise ClaimError("crosscheck requires three distinct machines")

    roots, digests = {}, {}
    for k, leg in legs.items():
        roots[k], digests[k] = _leg_root_digest(leg)

    equivalence = len(set(roots.values())) == 1
    reuse = (digests["M1"] == digests["M2"]) if equivalence else None
    audited = {k: _leg_audited(leg) for k, leg in legs.items()}

    declared = _leg_declared(m1)
    cost1, cost3 = _leg_cost(m1), _leg_cost(m3)

    rejected, incomplete = [], []

    if not equivalence:
        rejected.append("equivalence")
    if reuse is False:
        rejected.append("reuse")
    for k, ok in audited.items():
        if not ok:
            rejected.append(f"audited {k}")

    band = _cost_band(cost1, cost3, None if declared is None else declared.get("tolerance"))
    if declared is not None and "tolerance" in declared:
        if band["comparable"] is False:
            rejected.append("cost band")
        elif band["comparable"] is None:
            incomplete.append("cost band")

    envelope_result = {}
    if declared is not None and declared.get("envelope"):
        envelope_result = _envelope_check(cost3, declared["envelope"])
        for unit, info in envelope_result.items():
            if info["within"] is False:
                rejected.append(f"envelope {unit}")
            elif info["within"] is None:
                incomplete.append(f"envelope {unit}")

    mscore = None
    if declared is not None and declared.get("mutation_floor") is not None:
        if mutants is not None and equivalence and _leg_kind(m3) == "dir":
            mscore = mutation_score(m3, max_mutants=mutants)
            if not mscore["ok"]:
                rejected.append("mutation_floor")
        else:
            incomplete.append("mutation_floor")

    if declared is None:
        incomplete.append("declared conditions")

    if rejected:
        verdict = "reject"
    elif incomplete:
        verdict = "incomplete"
    else:
        verdict = "accept"

    result = {
        "satisfied": verdict == "accept",
        "verdict": verdict,
        "rejected": rejected,
        "incomplete": incomplete,
        "roots": roots,
        "equivalence": equivalence,
        "reuse": reuse,
        "audited": audited,
        "cost": {"comparable": band["comparable"]},
        "independence": _independence_string(_leg_independence(m3)),
        "mutation_score": mscore,
    }
    if envelope_result:
        result["cost"]["envelope"] = envelope_result
    return result


# ===========================================================================
# record_proof: freeze the crosscheck's verdict onto M1 (spec/record.md)
# ===========================================================================

def record_proof(m1: str, m2: str, m3: str) -> dict:
    """Run the crosscheck; on a pass, seal the proof onto M1's manifest as
    residue. M1 must be a directory; a record leg must be anchored by a
    trusted signature, and the proof then names its signer and digest."""
    if _leg_kind(m1) != "dir":
        raise ClaimError("a proof cannot land on a frozen record: M1 must be a directory")

    anchor = os.environ.get(core._ENV_SIGNERS)
    trail = []
    for label, leg in (("m2", m2), ("m3", m3)):
        if _leg_kind(leg) == "record":
            signer = _attest.record_signer(leg, anchor) if anchor else None
            if not signer:
                raise ClaimError(f"record leg {leg!r} is not anchored by a trusted signature")
            trail.append({"signer": signer, "digest": _attest.record_digest(record_read(leg))})

    result = crosscheck(m1, m2, m3)
    proof_recorded = result["verdict"] == "accept"
    if not proof_recorded:
        return {"proof_recorded": False, "crosscheck": result}

    proof = {"kind": "crosscheck", "m2": os.path.realpath(m2), "m3": os.path.realpath(m3)}
    if trail:
        proof["records"] = trail

    manifest = read_manifest(m1)
    manifest["proof"] = proof
    core._write_json(os.path.join(m1, core.MANIFEST), manifest)
    return {"proof_recorded": True, "crosscheck": result}
