"""Crosscheck: the three-machine test, deep audit, records, and mutation
testing (spec/verification.md, spec/record.md).

`audit` is the only verb that re-earns a verdict: it recomputes identity,
furnishes the declared environment, regrows what a producer supplies, and
re-runs every gate cold in a fresh room. `_machine` normalizes one leg of a
crosscheck -- a claim directory (computed on the spot) or a record file
(spec/record.md's frozen transport) -- into the same shape, so `crosscheck`
reaches one verdict regardless of which transport each leg travelled by.
`record_validate`/`record_canonical`/`record_digest`/`record_read`/
`record_signer` read the record format (versions 1 and 2); this module owns
that format the way the kernel owns everything else a claim is judged by.

The mutation engine (`_mutants` and friends) draws deterministic structural
and token-level mutants of a claim's generated Python, seeded from the
claim's own root, so a claim's `mutation_floor` can be re-earned by an
independent rebuild the same way a gate can.

Stdlib only, never the network.
"""
import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import tempfile
import tomllib

from . import build, core, identity, recipe, run
from . import seal as seal_mod
from .core import ClaimError


def _validate_generated_path(d, name):
    if not isinstance(name, str):
        raise ClaimError(f"a step output must be a string: {name!r}")
    if not name:
        raise ClaimError("path name must not be empty")
    if os.path.isabs(name):
        raise ClaimError(f"path name must not be absolute: {name!r}")
    if any(p in ("", "..") for p in name.split("/")):
        raise ClaimError(f"path name must not escape the claim: {name!r}")


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe under claim directory `d`
    (spec/claim-format.md): a corrected `recipe.load_recipe`.

    That function checks every step's output for symlink-safety at PARSE
    time, `generated` outputs included -- but a generated output is never
    hashed (spec/identity.md's file-hashing rules bind pinned inputs and
    non-generated outputs only), so a symlinked *generated* output must
    still seal cleanly; only materializing it should refuse, which `audit`
    already does on its own (confining every produce-step copy through
    `core._safe` before copying). Escape safety (no absolute path, no `..`)
    still applies to every output regardless of class.
    """
    path = recipe.recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise ClaimError(f"recipe {path!r} is not valid UTF-8: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e

    if not isinstance(doc, dict) or not isinstance(doc.get("claim"), dict):
        raise ClaimError(f"recipe {path!r} has no [claim] table")
    claim = doc["claim"]
    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError(f"[claim] format must be a positive integer: {fmt!r}")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    envelope = claim.get("envelope")
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError(f"[claim] envelope must be a non-empty table: {envelope!r}")
        unknown = set(envelope.keys()) - set(core.COST_KEYS)
        if unknown:
            raise ClaimError(f"[claim] envelope has unknown unit(s): {sorted(unknown)}")
        for unit, ceiling in envelope.items():
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                raise ClaimError(f"[claim] envelope {unit} must be a positive number: {ceiling!r}")

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list):
        raise ClaimError("[claim] inputs must be a list of paths")
    for p in inputs:
        recipe._validate_path(d, p, "an [claim] inputs path")

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        recipe._validate_path(d, manifest, "[claim] inputs_manifest")

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")

    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError(f"a step must be a table: {step!r}")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise ClaimError(f"a step kind must be one of {sorted(core.KINDS)}: {kind!r}")
        output = step.get("output")
        step_class = step.get("class")
        if step_class is None:
            step_class = "generated" if kind == "produce" else "pinned"
        if step_class in ("generated", "free"):
            _validate_generated_path(d, output)
        else:
            recipe._validate_path(d, output, "a step output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"a gate step needs a string run: {step!r}")
        step["class"] = step_class

    doc[recipe._DIR_KEY] = os.path.realpath(d)
    return doc


def run_gate(cmd: str, d: str, parsed: dict = None, timeout: float = None) -> dict:
    """One gate: scrubbed env, sandboxed, bounded (spec/claim-format.md).

    A corrected `run.run_gate`: that function's own `_scrub_env` sends the
    wrapped process a literal `"1"` for `RETICULI_JAILED` regardless of which
    sandbox actually applied, so a gate that is itself a claim runner cannot
    tell which backend it is inside and tries to re-apply one, dying with
    `sandbox_apply: Operation not permitted`. This sends the backend's own
    name, the value the execution contract requires (spec/verification.md).
    """
    backend = run.sandbox_backend()
    bound = timeout if timeout is not None else run.gate_timeout(parsed)

    scratch = None
    if backend != "none":
        run_store = os.path.join(d, core.STORE, "run")
        os.makedirs(run_store, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="room-", dir=run_store)
    try:
        env = {k: os.environ[k] for k in core._KEEP_ENV if k in os.environ}
        if scratch is not None:
            env["TMPDIR"] = scratch
            env["HOME"] = scratch
        env[core._JAILED] = backend
        argv = run._sandbox_argv(backend, cmd, d, scratch)
        result = run._run(argv, cwd=d, env=env, timeout=bound)
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)

    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"
    return {"status": status, "quarantine": backend, "returncode": result["returncode"],
            "stdout": result["stdout"], "stderr": result["stderr"]}

# ---------------------------------------------------------------------------
# pinned seam values (checks/kernel_check.py verifies these by equality)
# ---------------------------------------------------------------------------
_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2',
                           'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh',
                           'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})

_ARITHMETIC = ('+', '-', '*', '/', '//', '%', '**')
_OP_ALTS = {
    '+': ['-', '*'], '-': ['+', '*'], '*': ['+', '-'],
    '/': ['*', '//'], '//': ['/', '%'], '%': ['//', '*'], '**': ['*'],
    '>': ['<', '>=', '<=', '==', '!='], '<': ['>', '<=', '>=', '==', '!='],
    '>=': ['<=', '>', '<', '==', '!='], '<=': ['>=', '<', '>', '==', '!='],
    '==': ['!=', '>', '<'], '!=': ['==', '>', '<'],
    'and': ['or'], 'or': ['and'],
}
_OP_KIND = {}
_OP_KIND.update({s: 'arithmetic' for s in _ARITHMETIC})
_OP_KIND.update({s: 'comparison' for s in _COMPARISON})
_OP_KIND.update({'and': 'boolean', 'or': 'boolean'})
_STRING_LITERAL = re.compile(
    r"'''(?:.|\n)*?'''|\"\"\"(?:.|\n)*?\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\""
)
_WORD_ALTS = {
    "True": ["False"], "False": ["True"],
    "break": ["continue"], "continue": ["break"],
    "and": ["or"], "or": ["and"],
}

_OP_SPLIT_RE = re.compile(r'\|\||&&|[&|;\n]')
_REDIRECTS = frozenset({">", "<", ">>", "2>", "2>>"})


# ---------------------------------------------------------------------------
# gate deciders / vacuous gates
# ---------------------------------------------------------------------------

def gate_deciders(cmd: str) -> list:
    """Which workspace files decide a gate's `run` command.

    Splits `cmd` on shell control operators (`_OPERATORS`); a segment whose
    first token is a known interpreter (`_INTERPRETERS`) contributes the
    first non-flag argument after it (skipping flags that consume a value,
    `_SKIP_VALUE`); a segment whose first token names a workspace path (has
    a `/`) contributes that path, `./`-prefix stripped. A segment invoking a
    bare system tool (`grep`, `printf`, ...) contributes nothing: the recipe
    text itself is the criterion.
    """
    deciders = []
    for seg in _OP_SPLIT_RE.split(cmd):
        seg = seg.strip()
        if not seg:
            continue
        try:
            tokens = shlex.split(seg)
        except ValueError:
            continue
        if not tokens:
            continue
        first = tokens[0]
        if first in _INTERPRETERS:
            rest = tokens[1:]
            i = 0
            while i < len(rest):
                tok = rest[i]
                if tok in _REDIRECTS:
                    break
                if tok in _SKIP_VALUE:
                    i += 2
                    continue
                if tok.startswith("-"):
                    i += 1
                    continue
                deciders.append(tok)
                break
        elif "/" in first:
            deciders.append(first[2:] if first.startswith("./") else first)
    return deciders


def vacuous_gates(parsed: dict) -> list:
    """Gates whose every decider is a `generated` output -- the verdict
    depends on no claim, so the root fits any implementation that prints ok."""
    steps = parsed.get("step", [])
    generated = {
        s["output"] for s in steps
        if s.get("kind") == "produce" and s.get("class", "generated") in ("generated", "free")
    }
    vacuous = []
    for step in steps:
        if step.get("kind") != "gate":
            continue
        deciders = gate_deciders(step.get("run", ""))
        if deciders and all(d in generated for d in deciders):
            vacuous.append(step["output"])
    return vacuous


# ---------------------------------------------------------------------------
# mutation engine
# ---------------------------------------------------------------------------

def _node_span(node, source: str) -> tuple:
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    return (start, end)


def _span_text(source: str, span: tuple) -> str:
    return source[span[0]:span[1]]


def _splice(source: str, span: tuple, replacement: str) -> str:
    return source[:span[0]] + replacement + source[span[1]:]


def _edit(path: str, source: str, span: tuple, replacement: str, kind: str) -> dict:
    return {"file": path, "span": list(span), "before": _span_text(source, span),
            "after": replacement, "kind": kind}


def _named(edit: dict) -> str:
    return f"{edit['file']}:{edit['span'][0]}:{edit['span'][1]}:{edit['kind']}:{edit['before']}->{edit['after']}"


def _label(edit: dict) -> str:
    return f"{edit['file']}@{edit['span'][0]}: {edit['before']!r} -> {edit['after']!r} ({edit['kind']})"


def _docstring_spans(source: str) -> list:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    spans = []
    candidates = [tree] + [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    for node in candidates:
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            spans.append(_node_span(first, source))
    return spans


_CMP_SYMBOLS = {ast.Gt: '>', ast.Lt: '<', ast.GtE: '>=', ast.LtE: '<=',
                ast.Eq: '==', ast.NotEq: '!='}
_BIN_SYMBOLS = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/',
                ast.FloorDiv: '//', ast.Mod: '%', ast.Pow: '**'}
_BOOL_SYMBOLS = {ast.And: 'and', ast.Or: 'or'}


def _operator_span(source, left_node, right_node, symbol, word=False):
    left_end = _node_span(left_node, source)[1]
    right_start = _node_span(right_node, source)[0]
    seg = source[left_end:right_start]
    pattern = r'\b' + re.escape(symbol) + r'\b' if word else re.escape(symbol)
    m = re.search(pattern, seg)
    if not m:
        return None
    return (left_end + m.start(), left_end + m.end())


def _structural_mutants(path: str, source: str) -> list:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    mutants = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            sym = _CMP_SYMBOLS.get(type(node.ops[0]))
            if sym is None:
                continue
            span = _operator_span(source, node.left, node.comparators[0], sym)
            if span is None:
                continue
            for alt in _OP_ALTS.get(sym, []):
                mutants.append(_edit(path, source, span, alt, _OP_KIND.get(sym, "comparison")))
        elif isinstance(node, ast.BinOp):
            sym = _BIN_SYMBOLS.get(type(node.op))
            if sym is None:
                continue
            span = _operator_span(source, node.left, node.right, sym)
            if span is None:
                continue
            for alt in _OP_ALTS.get(sym, []):
                mutants.append(_edit(path, source, span, alt, _OP_KIND.get(sym, "arithmetic")))
        elif isinstance(node, ast.BoolOp) and len(node.values) >= 2:
            sym = _BOOL_SYMBOLS.get(type(node.op))
            if sym is None:
                continue
            span = _operator_span(source, node.values[0], node.values[1], sym, word=True)
            if span is None:
                continue
            for alt in _OP_ALTS.get(sym, []):
                mutants.append(_edit(path, source, span, alt, "boolean"))
    return mutants


def _token_mutants(path: str, source: str) -> list:
    protected = [(m.start(), m.end()) for m in _STRING_LITERAL.finditer(source)]
    protected += _docstring_spans(source)

    def in_protected(pos):
        return any(a <= pos < b for a, b in protected)

    mutants = []
    for word, alts in _WORD_ALTS.items():
        for m in re.finditer(r'\b' + re.escape(word) + r'\b', source):
            if in_protected(m.start()):
                continue
            for alt in alts:
                mutants.append(_edit(path, source, (m.start(), m.end()), alt, "word"))
    return mutants


def _mutants(path: str, source: str) -> list:
    return _structural_mutants(path, source) + _token_mutants(path, source)


def _draw_order(candidates: list, seed: str) -> list:
    return sorted(candidates, key=lambda e: (
        hashlib.sha256((seed + "|" + _named(e)).encode("utf-8")).hexdigest(), _named(e)
    ))


def _mutant_order(candidates: list, seed: str) -> list:
    seen = set()
    ordered = []
    for edit in _draw_order(candidates, seed):
        name = _named(edit)
        if name in seen:
            continue
        seen.add(name)
        ordered.append(edit)
    return ordered


def _run_mutant(d: str, parsed: dict, output: str, mutated_source: str) -> bool:
    """Materialize a scratch room with `output` replaced by `mutated_source`
    and run every gate; returns True (mutant survives) iff all gates pass."""
    store = os.path.join(d, core.STORE)
    os.makedirs(store, exist_ok=True)
    room = tempfile.mkdtemp(prefix="mutant-", dir=store)
    try:
        for path in recipe._inputs(parsed):
            core._copy_into(os.path.join(d, path), os.path.join(room, path))
        for out in recipe.generated_outputs(parsed):
            src_path = os.path.join(d, out)
            if not os.path.isfile(src_path):
                continue
            dest = os.path.join(room, out)
            os.makedirs(os.path.dirname(dest) or room, exist_ok=True)
            if out == output:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(mutated_source)
            else:
                core._copy_into(src_path, dest)
        for step in recipe.gates(parsed):
            result = run_gate(step["run"], room, parsed)
            if result["status"] != "ok":
                return False
        return True
    finally:
        shutil.rmtree(room, ignore_errors=True)


def mutation_score(d: str, max_mutants: int = 20) -> dict:
    """Deterministic mutants of the claim's generated Python, drawn from the
    root, re-audited; the kill rate is residue (`.reticuli/mutation_score.json`)."""
    parsed = load_recipe(d)
    seed = safe_root(parsed, d)
    candidates = []
    for output in recipe.generated_outputs(parsed):
        path = os.path.join(d, output)
        if not output.endswith(".py") or not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        candidates.extend(_mutants(output, source))

    ordered = _mutant_order(candidates, seed)
    sample = ordered[:max_mutants]

    sources = {}
    survivors = []
    killed = 0
    for edit in sample:
        output = edit["file"]
        if output not in sources:
            with open(os.path.join(d, output), "r", encoding="utf-8") as f:
                sources[output] = f.read()
        mutated = _splice(sources[output], tuple(edit["span"]), edit["after"])
        if _run_mutant(d, parsed, output, mutated):
            survivors.append(_label(edit))
        else:
            killed += 1

    total = len(sample)
    result = {"mutants": total, "killed": killed,
              "rate": (killed / total) if total else 0.0, "survivors": survivors}
    core._write_json(os.path.join(d, core.MUTATION_RESIDUE), result)
    return result


# ---------------------------------------------------------------------------
# identity, guarded against filesystem aliasing the given core/identity
# modules do not themselves refuse (hardlinks, FIFOs, other special files)
# ---------------------------------------------------------------------------

def _check_regular_single_link(path: str) -> None:
    try:
        st = os.lstat(path)
    except OSError as e:
        raise ClaimError(f"cannot stat declared path {path!r}: {e}") from e
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"declared path is not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"declared path has more than one hard link: {path!r}")


def _with_environment_input(parsed: dict) -> dict:
    """`[claim] environment` names a hash-pinned file that is AUTOMATICALLY a
    pinned input (spec/claim-format.md) -- but `recipe._inputs`/`identity.root`
    only ever look at `[claim] inputs`, so a claim that declares `environment`
    without ALSO listing it in `inputs` would seal a root that never moves
    when the pin file changes. Fold it into a claim-level copy's `inputs`
    before hashing; the claim on disk, and the room `_materialize` builds,
    are untouched."""
    env_file = parsed.get("claim", {}).get("environment")
    if not env_file:
        return parsed
    inputs = list(parsed["claim"].get("inputs", []))
    if env_file in inputs:
        return parsed
    new_claim = dict(parsed["claim"])
    new_claim["inputs"] = inputs + [env_file]
    new_parsed = dict(parsed)
    new_parsed["claim"] = new_claim
    return new_parsed


def safe_root(parsed: dict, d: str) -> str:
    """`identity.root`, guarded: every pinned input and pinned/validated
    output must be a regular, single-link file (spec/identity.md's file
    hashing rules) before its bytes enter the preimage, and a declared
    `[claim] environment` file is folded in as a pinned input."""
    parsed = _with_environment_input(parsed)
    for path in recipe._inputs(parsed):
        _check_regular_single_link(os.path.join(d, path))
    for step in parsed.get("step", []):
        if step["class"] not in ("generated", "free"):
            _check_regular_single_link(os.path.join(d, step["output"]))
    try:
        return identity.root(parsed, d)
    except OSError as e:
        raise ClaimError(f"cannot compute root: {e}") from e


def read_manifest(d: str) -> dict:
    """`seal.read_manifest`, guarded against bytes that are not valid UTF-8
    -- that module catches a missing file and invalid JSON but not invalid
    encoding, which a corrupted manifest can just as easily be."""
    try:
        return seal_mod.read_manifest(d)
    except UnicodeDecodeError as e:
        raise ClaimError(f"manifest at {d!r} is not valid UTF-8: {e}") from e


def furnish(d: str, parsed: dict) -> dict:
    """`run.furnish`, guarded: that function shells out to `pip install -r
    <requirements file>` without setting the subprocess's cwd, so a locally
    pinned wheel named by a relative path in the requirements file (as
    spec/claim-format.md's own worked example writes it) resolves against
    whatever directory the *caller* happened to be running in, not the claim
    -- `pip install` follows a relative path in a requirements file against
    its own process cwd. Run it with cwd temporarily at `d`."""
    old = os.getcwd()
    os.chdir(d)
    try:
        return run.furnish(d, parsed)
    finally:
        os.chdir(old)


def _with_path(bin_dir, fn, *args, **kwargs):
    """Run `fn` with `bin_dir` prepended to PATH -- the furnished venv's own
    interpreter first, for gates and producers alike."""
    if not bin_dir:
        return fn(*args, **kwargs)
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = bin_dir + os.pathsep + old
    try:
        return fn(*args, **kwargs)
    finally:
        os.environ["PATH"] = old


# ---------------------------------------------------------------------------
# audit: the only verb that re-earns a verdict
# ---------------------------------------------------------------------------

def audit(d: str, producer=None, *, produce_from=None, shallow: bool = False,
          signers: str = None) -> dict:
    """Re-execute every gate, cold and sandboxed (spec/verification.md).

    Refuses before running anything if the bytes present no longer recompute
    the sealed root, or if the host cannot furnish what the claim declares.
    `produce_from` substitutes specific generated outputs with bytes from
    elsewhere (a dependent auditing a component's claim against its own
    shipped copy) before any gate runs; `producer` regrows every `produce`
    step the ordinary way. A gate's status is `ok` when it runs clean and its
    output byte-matches the pinned copy in `d`, `mismatch` when it runs clean
    but differs (a carried verdict), and the ordinary failure classes
    otherwise. Composed claims (`components` in the manifest) audit
    recursively unless `shallow`.
    """
    manifest = read_manifest(d)
    parsed = load_recipe(d)
    recomputed = safe_root(parsed, d)
    if recomputed != manifest["root"]:
        return {"ok": False, "name": manifest.get("name"), "root": manifest["root"],
                "recomputed": recomputed, "gates": [], "environment": []}

    gate_steps = recipe.gates(parsed)
    missing = run.preflight(parsed)
    if missing:
        return {"ok": False, "name": manifest["name"], "root": manifest["root"],
                "environment": missing,
                "gates": [{"output": s["output"], "status": "environment", "quarantine": None}
                          for s in gate_steps]}

    furnished = furnish(d, parsed)
    if not furnished["ok"]:
        return {"ok": False, "name": manifest["name"], "root": manifest["root"],
                "environment": [furnished.get("reason", "environment unavailable")],
                "gates": [{"output": s["output"], "status": "environment", "quarantine": None}
                          for s in gate_steps]}
    bin_dir = furnished.get("bin")

    for output in recipe.generated_outputs(parsed):
        src_path = os.path.join(d, output)
        if os.path.lexists(src_path):
            core._safe(d, output)

    ok = True
    component_results = {}
    components = manifest.get("components") or {}
    if components and not shallow:
        for name, rel in components.items():
            sub = audit(os.path.join(d, rel), producer, produce_from=produce_from,
                        shallow=shallow, signers=signers)
            component_results[name] = sub
            ok = ok and sub["ok"]

    store = os.path.join(d, core.STORE)
    os.makedirs(store, exist_ok=True)
    room = tempfile.mkdtemp(prefix="audit-", dir=store)
    try:
        build._materialize(parsed, d, room)
        if produce_from:
            for output, src in produce_from.items():
                dest = core._safe(room, output)
                core._copy_into(src, dest)
        if producer is not None:
            for step in recipe.produces(parsed):
                if "from" in step or (produce_from and step["output"] in produce_from):
                    continue
                _with_path(bin_dir, build._produce, step, room, producer, parsed,
                           build._step_guidance(step))

        gate_results = []
        for step in gate_steps:
            result = _with_path(bin_dir, run_gate, step["run"], room, parsed)
            status = result["status"]
            if status == "ok":
                out_path = os.path.join(room, step["output"])
                pinned_path = os.path.join(d, step["output"])
                if not build._compare_pin(out_path, pinned_path):
                    status = "mismatch"
            gate_results.append({"output": step["output"], "status": status,
                                  "quarantine": result["quarantine"]})
            if status != "ok":
                ok = False
    finally:
        shutil.rmtree(room, ignore_errors=True)

    return {
        "ok": ok,
        "name": manifest["name"],
        "root": manifest["root"],
        "environment": [],
        "gates": gate_results,
        "authorized": build._authorized(d, parsed, signers),
        **({"components": component_results} if component_results else {}),
    }


# ---------------------------------------------------------------------------
# independence (declared, never enforced)
# ---------------------------------------------------------------------------

def _declared_producer(d: str) -> dict:
    vendor = model = blind = None
    found = False
    for event in run.ledger_events(d):
        if "vendor" in event or "model" in event or "blind" in event:
            found = True
            vendor = event.get("vendor", vendor)
            model = event.get("model", model)
            blind = event.get("blind", blind)
    return {"vendor": vendor, "model": model, "blind": blind} if found else None


def independence(d: str) -> dict:
    """Declared producer independence of a single machine's redo: vendor,
    model, and whether its workspace was blind (spec/verification.md)."""
    return _declared_producer(d) or {"vendor": None, "model": None, "blind": None}


def _independence_text(producer_info) -> str:
    if not producer_info or (producer_info.get("vendor") is None
                              and producer_info.get("model") is None):
        return "unestablished (no producer declared)"
    vendor = producer_info.get("vendor") or "unknown"
    model = producer_info.get("model") or "unknown"
    tail = ", blind workspace" if producer_info.get("blind") else ""
    return f"declared: {vendor}/{model}{tail} (not proven)"


# ---------------------------------------------------------------------------
# records (spec/record.md) -- versions 1 and 2
# ---------------------------------------------------------------------------

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 2

_RECORD_BASE_MEMBERS = frozenset({"record", "name", "root", "build_digest", "gates",
                                  "cost", "producer", "environment", "when", "tool"})
_RECORD_REQUIRED_BASE = frozenset({"record", "name", "root", "build_digest",
                                   "gates", "environment", "when"})
_RECORD_GATE_KEYS = frozenset({"output", "status", "sandbox"})
_RECORD_ENV_KEYS = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER_KEYS = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_COST_KEYS = frozenset({"usd", "tokens", "calls", "seconds"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_OBLIGATIONS = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def record_validate(doc) -> None:
    """Refuse, in band, any document spec/record.md does not accept."""
    if not isinstance(doc, dict):
        raise ClaimError("a record must be a JSON object")

    version = doc.get("record")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ClaimError("record version must be an integer")
    if version > RECORD_FORMAT:
        raise ClaimError(
            f"record format {version} is newer than this reader understands "
            f"(format {RECORD_FORMAT})")
    if version < 1:
        raise ClaimError(f"record format {version} is not understood")

    members = set(_RECORD_BASE_MEMBERS)
    required = set(_RECORD_REQUIRED_BASE)
    if version >= 2:
        members.add("claim")
        required.add("claim")

    keys = set(doc.keys())
    unknown = keys - members
    if unknown:
        raise ClaimError(f"record has unknown member(s): {sorted(unknown)}")
    missing = required - keys
    if missing:
        raise ClaimError(f"record is missing required member(s): {sorted(missing)}")

    if not isinstance(doc["name"], str):
        raise ClaimError("record name must be a string")
    for key in ("root", "build_digest"):
        v = doc[key]
        if not isinstance(v, str) or not _RECORD_HEX.match(v):
            raise ClaimError(f"record {key} must be 64 lowercase hex characters")
    when = doc["when"]
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise ClaimError("record when must be YYYY-MM-DDTHH:MM:SSZ")

    environment = doc["environment"]
    if not isinstance(environment, dict) or set(environment.keys()) != _RECORD_ENV_KEYS:
        raise ClaimError("record environment must have exactly platform, machine, runtime")
    for v in environment.values():
        if not isinstance(v, str):
            raise ClaimError("record environment values must be strings")

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise ClaimError("record gates must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate.keys()) != _RECORD_GATE_KEYS:
            raise ClaimError("each gate entry must have exactly output, status, sandbox")
        if not isinstance(gate["output"], str):
            raise ClaimError("gate output must be a string")
        if gate["status"] not in _RECORD_STATUSES:
            raise ClaimError(f"gate status must be one of {sorted(_RECORD_STATUSES)}")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise ClaimError(f"gate sandbox must be one of {sorted(_RECORD_SANDBOXES)}")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict):
            raise ClaimError("record cost must be an object")
        unknown_cost = set(cost.keys()) - _RECORD_COST_KEYS
        if unknown_cost:
            raise ClaimError(f"record cost has unknown key(s): {sorted(unknown_cost)}")
        for v in cost.values():
            if not _is_number(v) or v < 0:
                raise ClaimError("record cost values must be non-negative numbers")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict):
            raise ClaimError("record producer must be an object")
        unknown_producer = set(producer.keys()) - _RECORD_PRODUCER_KEYS
        if unknown_producer:
            raise ClaimError(f"record producer has unknown key(s): {sorted(unknown_producer)}")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise ClaimError(f"record producer {key} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise ClaimError("record producer blind must be a boolean")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("record tool must be a string")

    if version >= 2:
        claim = doc["claim"]
        if not isinstance(claim, dict):
            raise ClaimError("record claim must be an object")
        unknown_claim = set(claim.keys()) - _RECORD_OBLIGATIONS
        if unknown_claim:
            raise ClaimError(f"record claim has unknown obligation(s): {sorted(unknown_claim)}")
        if "tolerance" in claim:
            t = claim["tolerance"]
            if not _is_number(t) or t < 0:
                raise ClaimError("record claim tolerance must be a non-negative number")
        if "mutation_floor" in claim:
            mf = claim["mutation_floor"]
            if not _is_number(mf) or mf < 0:
                raise ClaimError("record claim mutation_floor must be a non-negative number")
        if "envelope" in claim:
            env = claim["envelope"]
            if not isinstance(env, dict) or not env:
                raise ClaimError("record claim envelope must be a non-empty object")
            unknown_env = set(env.keys()) - _RECORD_COST_KEYS
            if unknown_env:
                raise ClaimError(f"record claim envelope has unknown unit(s): {sorted(unknown_env)}")
            for v in env.values():
                if not _is_number(v) or v <= 0:
                    raise ClaimError("record claim envelope ceilings must be positive numbers")


def record_canonical(doc) -> bytes:
    """The canonical bytes: sorted keys, default separators, ASCII-escaped."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    """Read a record file: it is its canonical bytes, or it is not a record."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read record {path!r}: {e}") from e
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ClaimError(f"malformed record at {path!r}: {e}") from e
    record_validate(doc)
    if raw != record_canonical(doc):
        raise ClaimError(f"record at {path!r} is not in canonical form")
    return doc


def _principals(anchor: str) -> list:
    names = []
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            first_field = line.split(None, 1)[0]
            names.extend(p for p in first_field.split(",") if p)
    return names


def record_signer(path: str, anchor: str) -> str:
    """The principal in `anchor` whose key verifies the detached signature at
    `path + '.sig'` over the record's canonical bytes, in `RECORD_NAMESPACE`."""
    doc = record_read(path)
    canon = record_canonical(doc)
    sig_path = path + ".sig"
    try:
        principals = _principals(anchor)
    except OSError as e:
        raise ClaimError(f"cannot read signer anchor {anchor!r}: {e}") from e
    for principal in principals:
        if build._ssh_verify(anchor, principal, RECORD_NAMESPACE, sig_path, canon):
            return principal
    raise ClaimError(f"no signer in {anchor!r} verifies the signature at {sig_path!r}")


# ---------------------------------------------------------------------------
# _machine: one predicate, two transports
# ---------------------------------------------------------------------------

def _obligations_of(claim: dict) -> dict:
    return {k: claim[k] for k in ("tolerance", "envelope", "mutation_floor") if k in claim}


def _machine(leg) -> dict:
    """Normalize one crosscheck leg -- a claim directory, computed on the
    spot, or a record file, a frozen statement -- into one shape."""
    if os.path.isdir(leg):
        parsed = load_recipe(leg)
        root_value = safe_root(parsed, leg)
        aud = audit(leg)
        return {
            "kind": "dir", "path": leg,
            "root": root_value,
            "build_digest": identity.build_digest(leg),
            "ok": aud["ok"],
            "cost": run.cost(leg),
            "obligations": _obligations_of(parsed.get("claim", {})),
            "producer": _declared_producer(leg),
        }
    doc = record_read(leg)
    version = doc["record"]
    return {
        "kind": "record", "path": leg,
        "root": doc["root"],
        "build_digest": doc["build_digest"],
        "ok": all(g["status"] == "ok" for g in doc["gates"]) if doc["gates"] else True,
        "cost": doc.get("cost"),
        "obligations": doc.get("claim") if version >= 2 else None,
        "producer": doc.get("producer"),
    }


# ---------------------------------------------------------------------------
# crosscheck: the three-machine test
# ---------------------------------------------------------------------------

def crosscheck(m1, m2, m3, *, mutants: int = None, signers: str = None) -> dict:
    """The three-machine test (spec/verification.md): one root across all
    three, byte reuse between M1 and M2, every gate re-earned, the cost band
    and every condition the claim itself declares. The verdict is
    three-valued: `accept`, `reject`, or `incomplete` -- a declared
    condition nobody measured is neither true nor false."""
    reals = [os.path.realpath(p) for p in (m1, m2, m3)]
    if len(set(reals)) < 3:
        raise ClaimError("crosscheck requires three distinct machines")

    legs = {"M1": _machine(m1), "M2": _machine(m2), "M3": _machine(m3)}
    roots = {k: v["root"] for k, v in legs.items()}
    equivalence = len(set(roots.values())) == 1
    reuse = (legs["M1"]["build_digest"] == legs["M2"]["build_digest"]) if equivalence else False
    audited = {k: v["ok"] for k, v in legs.items()}

    rejected = []
    incomplete = []
    if not equivalence:
        rejected.append("equivalence")
    if equivalence and not reuse:
        rejected.append("reuse")
    if not all(audited.values()):
        rejected.append("audited")

    m1_obligations = legs["M1"]["obligations"]
    obligations_unknown = m1_obligations is None

    cost1, cost3 = legs["M1"]["cost"], legs["M3"]["cost"]
    tolerance_declared = (not obligations_unknown) and ("tolerance" in m1_obligations)
    tol = m1_obligations["tolerance"] if tolerance_declared else None
    tol_env = os.environ.get(core._ENV_TOLERANCE)
    if tol_env is not None:
        tol = float(tol_env)
    if tol is None:
        tol = core.TOLERANCE

    comparable = None
    if cost1 and cost3:
        unit = next((u for u in core.COST_LADDER if u in cost1 and u in cost3), None)
        if unit is not None and cost1[unit] and cost3[unit]:
            ratio = cost3[unit] / cost1[unit]
            comparable = (1.0 / tol) <= ratio <= tol

    if obligations_unknown:
        incomplete.append("declared conditions")
    elif tolerance_declared:
        if comparable is None:
            incomplete.append("cost band")
        elif not comparable:
            rejected.append("cost band")

    envelope_report = {}
    if not obligations_unknown:
        envelope = m1_obligations.get("envelope")
        if envelope:
            for unit, ceiling in envelope.items():
                measured = (cost3 or {}).get(unit)
                if measured is None:
                    within = None
                    incomplete.append(f"envelope {unit}")
                else:
                    within = measured <= ceiling
                    if not within:
                        rejected.append(f"envelope {unit}")
                envelope_report[unit] = {"within": within, "ceiling": ceiling, "measured": measured}

    mutation_result = None
    if not obligations_unknown:
        floor = m1_obligations.get("mutation_floor")
        if floor is not None:
            if mutants is None or legs["M3"]["kind"] != "dir":
                incomplete.append("mutation floor")
            else:
                score = mutation_score(legs["M3"]["path"], max_mutants=mutants)
                ok = score["rate"] >= floor
                mutation_result = {**score, "ok": ok}
                if not ok:
                    rejected.append("mutation floor")

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
        "reuse": reuse,
        "audited": audited,
        "cost": {"comparable": comparable, "tolerance": tol,
                 **({"envelope": envelope_report} if envelope_report else {})},
        "mutation_score": mutation_result,
        "independence": _independence_text(legs["M3"]["producer"]),
    }


def record_proof(m1, m2, m3, signers: str = None) -> dict:
    """Run the crosscheck; on a pass, seal the proof onto M1 as residue
    (never phase). M1 must be a directory; a record leg must verify against
    `signers` (else a proof from an unanchored record refuses), and each
    record's digest and signer identity are embedded in the proof."""
    if not os.path.isdir(m1):
        raise ClaimError("a recorded proof can only land on a directory (M1)")
    signers = signers or os.environ.get(core._ENV_SIGNERS)
    trail = []
    for leg in (m2, m3):
        if os.path.isdir(leg):
            continue
        if not signers:
            raise ClaimError("a proof from an unanchored record must refuse")
        doc = record_read(leg)
        signer = record_signer(leg, signers)
        trail.append({"signer": signer, "digest": record_digest(doc)})

    result = crosscheck(m1, m2, m3)
    proof_recorded = bool(result["satisfied"])
    if proof_recorded:
        manifest = read_manifest(m1)
        proof = {"kind": "crosscheck", "roots": result["roots"]}
        if trail:
            proof["records"] = trail
        manifest["proof"] = proof
        core._write_json(os.path.join(m1, core.MANIFEST), manifest)
    return {**result, "proof_recorded": proof_recorded}
