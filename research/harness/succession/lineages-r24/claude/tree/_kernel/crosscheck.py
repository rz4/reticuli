"""Crosscheck: the three-machine test, audit's room-level rules, rebuild's
tamper and provenance rules, phase's authorization, and the kernel's own
mutation-testing engine (spec/verification.md, spec/claim-format.md,
spec/record.md).

This module completes what the lower layers (core/recipe/identity/seal/run/
build/attest) leave as primitives: `audit` adds environment furnishing,
confinement of generated outputs, and substituted-bytes judging; `rebuild`
adds component reuse, threaded inputs, the producer tamper watch, and
provenance ledgering; `phase` adds the signed-authorization check; and
`crosscheck`/`record_proof` compose all of it into the three-valued verdict.
Stdlib only, never the network.
"""
import ast
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import tempfile

from reticuli._kernel import attest, build, core, identity, recipe, run
from reticuli._kernel import seal as _seal

# ==== mutation-testing vocabulary (pinned seam values) =====================
_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2',
                           'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh',
                           'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})

_ARITHMETIC = ("+", "-", "*", "/")
_OP_ALTS = {
    "+": "-", "-": "+", "*": "/", "/": "*",
    ">": "<", "<": ">", ">=": "<=", "<=": ">=", "==": "!=", "!=": "==",
}
_OP_KIND = {
    "+": "arithmetic", "-": "arithmetic", "*": "arithmetic", "/": "arithmetic",
    ">": "comparison", "<": "comparison", ">=": "comparison",
    "<=": "comparison", "==": "comparison", "!=": "comparison",
}
_WORD_ALTS = {"True": "False", "False": "True", "and": "or", "or": "and"}
_STRING_LITERAL = re.compile(r'("(?:[^"\\\n]|\\.)*")|(\'(?:[^\'\\\n]|\\.)*\')')

_AST_ARITH = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_AST_CMP = {ast.Gt: ">", ast.Lt: "<", ast.GtE: ">=", ast.LtE: "<=",
            ast.Eq: "==", ast.NotEq: "!="}
_WORD_PATTERN = re.compile(r'\b(?:' + '|'.join(re.escape(w) for w in _WORD_ALTS) + r')\b')

_OP_PATTERN = re.compile("|".join(re.escape(op) for op in sorted(_OPERATORS, key=len, reverse=True)))


# ==== the mutation engine ===================================================

def _node_span(node, src: str) -> tuple:
    """The (start, end) byte offsets of `node`'s own text within `src`."""
    lines = src.splitlines(keepends=True)
    prefix = [0]
    for line in lines:
        prefix.append(prefix[-1] + len(line))
    start = prefix[node.lineno - 1] + node.col_offset
    end = prefix[node.end_lineno - 1] + node.end_col_offset
    return start, end


def _span_text(src: str, span: tuple) -> str:
    return src[span[0]:span[1]]


def _docstring_spans(tree, src: str) -> list:
    """Every docstring's own span -- excluded from token-level mutation."""
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                spans.append(_node_span(body[0], src))
    return spans


def _structural_mutants(tree, src: str) -> list:
    """One-point arithmetic/comparison operator flips, found via the AST."""
    out = []
    for node in ast.walk(tree):
        sym = None
        if isinstance(node, ast.BinOp) and type(node.op) in _AST_ARITH:
            sym = _AST_ARITH[type(node.op)]
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 \
                and type(node.ops[0]) in _AST_CMP:
            sym = _AST_CMP[type(node.ops[0])]
        if sym is None:
            continue
        span = _node_span(node, src)
        text = _span_text(src, span)
        idx = text.find(sym)
        if idx == -1:
            continue
        start = span[0] + idx
        end = start + len(sym)
        out.append({"span": (start, end), "find": sym, "replace": _OP_ALTS[sym],
                    "kind": _OP_KIND[sym], "line": node.lineno})
    return out


def _token_mutants(src: str, tree) -> list:
    """Boolean-word flips and string-literal mutations, found by text,
    outside any docstring span."""
    doc_spans = _docstring_spans(tree, src)

    def _shadowed(pos):
        return any(a <= pos < b for a, b in doc_spans)

    out = []
    for m in _WORD_PATTERN.finditer(src):
        if _shadowed(m.start()):
            continue
        word = m.group(0)
        out.append({"span": (m.start(), m.end()), "find": word,
                    "replace": _WORD_ALTS[word], "kind": "word",
                    "line": src.count("\n", 0, m.start()) + 1})
    for m in _STRING_LITERAL.finditer(src):
        if _shadowed(m.start()):
            continue
        lit = m.group(0)
        replacement = (lit[0] + "MUTATED" + lit[-1]) if len(lit) > 2 else (lit[0] + "x" + lit[-1])
        out.append({"span": (m.start(), m.end()), "find": lit, "replace": replacement,
                    "kind": "string", "line": src.count("\n", 0, m.start()) + 1})
    return out


def _mutants(d: str, parsed: dict) -> list:
    """Every candidate mutant across the claim's generated python files."""
    out = []
    for output in recipe.generated_outputs(parsed):
        if not output.endswith(".py"):
            continue
        path = core._safe(d, output)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for m in _structural_mutants(tree, src) + _token_mutants(src, tree):
            m = dict(m)
            m["file"] = output
            out.append(m)
    return out


def _named(mutant: dict) -> str:
    """The mutant's qualified name: file, line, and operator kind."""
    return f"{mutant['file']}:{mutant['line']}:{mutant['kind']}"


def _label(mutant: dict) -> str:
    """A full, human-readable identifier for one mutant."""
    return f"{_named(mutant)}:{mutant['find']}->{mutant['replace']}"


def _mutant_order(mutants: list, root: str) -> list:
    """A canonical, root-seeded ordering over candidate mutants: the draw
    is reproducible for the same generated bytes and the same root."""
    return sorted(mutants, key=lambda m: hashlib.sha256((root + "|" + _label(m)).encode()).hexdigest())


def _draw_order(mutants: list, root: str, k: int) -> list:
    """The first `k` mutants of the canonical order: the deterministic sample."""
    return _mutant_order(mutants, root)[:k]


def _edit(src: str, mutant: dict) -> str:
    """`src` with one mutant's span replaced."""
    start, end = mutant["span"]
    return src[:start] + mutant["replace"] + src[end:]


def _splice(path: str, text: str) -> None:
    """Write `text` to `path`, replacing its contents."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _clear_pycache(d: str) -> None:
    """Drop every `__pycache__` under `d` -- a gate that imports a mutated
    module must not run a stale cached bytecode left over from an earlier
    (correct) splice of the same file within the same wall-clock second."""
    for base, dirs, _files in os.walk(d):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(base, "__pycache__"), ignore_errors=True)


def _machine(d: str, parsed: dict, mutant: dict) -> bool:
    """Apply one mutant, run every gate, restore the file; report whether
    the mutant SURVIVED (every gate still passed)."""
    path = core._safe(d, mutant["file"])
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()
    try:
        _splice(path, _edit(original, mutant))
        _clear_pycache(d)
        for step in recipe.gates(parsed):
            res = run_gate(step["run"], d, parsed)
            if res["status"] != "ok":
                return False
        return True
    finally:
        _splice(path, original)
        _clear_pycache(d)


def mutation_score(d: str, max_mutants: int = 20) -> dict:
    """Mutants of the generated code, drawn deterministically from the
    root, re-audited; the kill rate is residue (spec/verification.md)."""
    parsed = load_recipe(d)
    root_hex = identity.root(parsed, d)
    candidates = _mutants(d, parsed)
    chosen = _draw_order(candidates, root_hex, max_mutants)
    survivors = []
    killed = 0
    for m in chosen:
        if _machine(d, parsed, m):
            survivors.append(_label(m))
        else:
            killed += 1
    total = len(chosen)
    rate = (killed / total) if total else 0.0
    result = {"mutants": total, "killed": killed, "rate": rate,
              "survivors": sorted(survivors)}
    core._write_json(os.path.join(d, core.MUTATION_RESIDUE), result)
    return result


# ==== run_gate: the sending half of the sandbox-signal contract ============

def run_gate(cmd: str, d: str, parsed=None) -> dict:
    """One gate, run the way `run.run_gate` does -- scrubbed, sandboxed,
    bounded -- except that the sending half of the sandbox-signal contract
    is fixed here: a kernel that APPLIES a sandbox must tell the wrapped
    process WHICH jail it is inside (the backend name), not merely that one
    is applied. `run._scrub_env` sets a bare flag; this corrects it to the
    backend before the gate ever runs, so a gate that is itself a claim
    runner inherits correctly instead of nesting."""
    backend = run.sandbox_backend()
    timeout = run.gate_timeout(parsed)
    real_d = os.path.realpath(d)
    env = run._scrub_env(backend)
    scratch = None
    if backend in ("seatbelt", "bubblewrap"):
        env[core._JAILED] = backend
        store_dir = os.path.join(d, core.STORE)
        os.makedirs(store_dir, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="scratch-", dir=store_dir)
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
    argv = run._sandbox_argv(cmd, real_d, scratch, backend)
    status = run._run(argv, d, env, timeout)
    return {"status": status, "quarantine": backend}


# ==== the claim boundary: vacuous gates and their deciders ==================

def gate_deciders(cmd: str) -> list:
    """Which workspace files a gate command's own execution delegates its
    decision to (an interpreter's positional targets, or a directly
    executed `./script`) -- not every file the command merely names."""
    deciders = []
    for sub in _OP_PATTERN.split(cmd):
        try:
            tokens = shlex.split(sub, comments=False)
        except ValueError:
            continue
        if not tokens:
            continue
        head, rest = tokens[0], tokens[1:]
        if head.startswith("./"):
            deciders.append(head[2:])
            continue
        if head not in _INTERPRETERS:
            continue
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok in (">", ">>", "<", "2>", "2>>", "&>"):
                break
            if tok in _SKIP_VALUE:
                i += 2
                continue
            if tok.startswith("-"):
                i += 1
                continue
            deciders.append(tok)
            i += 1
    seen, out = set(), []
    for dd in deciders:
        if dd not in seen:
            seen.add(dd)
            out.append(dd)
    return out


def vacuous_gates(parsed: dict) -> list:
    """Gates whose every decider is itself generated code -- the verdict
    depends on no pinned claim (spec/verification.md)."""
    generated = set(recipe.generated_outputs(parsed))
    out = []
    for step in recipe.gates(parsed):
        deciders = gate_deciders(step.get("run", "") or "")
        if deciders and all(dec in generated for dec in deciders):
            out.append(step["output"])
    return out


# ==== load_recipe / seal / verify: generated-output confinement is an ======
# ==== audit-time concern, not a parse-time one ==============================

def _validate_step_lenient(d: str, step) -> None:
    """Like `recipe._validate_step`, except a declared output's own path
    is confinement-checked only when it is NOT generated. A generated
    output does not enter the root (spec/identity.md), and it may not
    exist yet (or may be hostile bytes a producer left behind) at the
    moment a claim is merely being PARSED; the one place that matters --
    judging in place -- is `audit`, which checks every produce output's
    confinement itself before running any gate."""
    if not isinstance(step, dict):
        raise core.ClaimError("malformed recipe: a step must be a table")
    kind = step.get("kind")
    if kind not in core.KINDS:
        raise core.ClaimError(f"malformed recipe: unknown step kind {kind!r}")
    output = step.get("output")
    if not isinstance(output, str) or output == "":
        raise core.ClaimError("malformed recipe: a step needs a string output")
    if identity._effective_class(step) != "generated":
        core._safe(d, output)
    cls = step.get("class")
    if cls is not None and cls not in recipe.STEP_CLASSES:
        raise core.ClaimError(f"malformed recipe: unknown step class {cls!r}")
    if kind == "gate" and not isinstance(step.get("run"), str):
        raise core.ClaimError("malformed recipe: a gate step needs a string run")


def load_recipe(d: str) -> dict:
    """Like `recipe.load_recipe`, with the lenient generated-output check
    above in place of the strict one."""
    path = recipe.recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise core.ClaimError(f"cannot read recipe {path!r}: {e}") from e
    import tomllib
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise core.ClaimError(f"malformed recipe {path!r}: {e}") from e
    if not isinstance(parsed, dict):
        raise core.ClaimError("malformed recipe: not a table")
    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError("malformed recipe: missing [claim] table")
    name = claim.get("name")
    if not isinstance(name, str):
        raise core.ClaimError("malformed recipe: [claim] name is required and must be a string")
    fmt = claim.get("format", 1)
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise core.ClaimError("malformed recipe: [claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise core.ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")
    for p in claim.get("inputs", []) or []:
        core._safe(d, p)
    manifest_name = claim.get("inputs_manifest")
    if manifest_name is not None:
        core._safe(d, manifest_name)
    environment = claim.get("environment")
    if environment is not None:
        core._safe(d, environment)
    envelope = claim.get("envelope")
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise core.ClaimError("malformed recipe: [claim] envelope must be a non-empty table")
        for unit, ceiling in envelope.items():
            if unit not in core.COST_UNITS:
                raise core.ClaimError(f"malformed recipe: unknown envelope unit {unit!r}")
            if not isinstance(ceiling, (int, float)) or isinstance(ceiling, bool) or ceiling <= 0:
                raise core.ClaimError(f"malformed recipe: envelope {unit!r} must be a positive number")
    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("malformed recipe: [[step]] must be an array of tables")
    for step in steps:
        _validate_step_lenient(d, step)
    return parsed


def _furnish(d: str, parsed: dict):
    """Like `run.furnish`, except run with the claim directory as cwd:
    `[claim] environment` may name its artifacts by a path relative to the
    claim (`./probe-1.0-...whl`), and pip resolves a requirements file's
    relative entries against the CURRENT WORKING DIRECTORY, not against
    the file's own location -- `run.furnish` never sets one."""
    cwd0 = os.getcwd()
    os.chdir(os.path.realpath(d))
    try:
        return run.furnish(".", parsed)
    finally:
        os.chdir(cwd0)


def seal(d: str, **kwargs) -> dict:
    """Like `seal.seal`, parsing via the lenient `load_recipe` above."""
    parsed = load_recipe(d)
    name = parsed["claim"]["name"]
    r = identity.root(parsed, d)
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    manifest = {"name": name, "root": r}
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    core._write_json(os.path.join(d, _seal.PARTS_RESIDUE), identity._parts(parsed, d))
    return manifest


def verify(d: str) -> dict:
    """Like `seal.verify`, parsing via the lenient `load_recipe` above."""
    manifest = _seal.read_manifest(d)
    parsed = load_recipe(d)
    recomputed = identity.root(parsed, d)
    return {"ok": recomputed == manifest["root"], "root": manifest["root"],
            "recomputed": recomputed, "name": manifest["name"]}


# ==== audit: furnishing, confinement, substitution ==========================

def audit(d: str, produce_from=None) -> dict:
    """Deep re-earning (spec/verification.md): identity first, generated
    outputs confined, the environment furnished, then every gate re-run
    cold and classified. `produce_from` judges substituted generated bytes
    by this claim without touching `d` itself."""
    if produce_from:
        tmp = tempfile.mkdtemp()
        try:
            shutil.copytree(d, tmp, dirs_exist_ok=True)
            for output, src in produce_from.items():
                core._copy_into(src, core._safe(tmp, output))
            return audit(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    parsed = load_recipe(d)
    v = verify(d)
    gate_steps = recipe.gates(parsed)
    if not v["ok"]:
        return {"ok": False, "verdict": "mismatch", "root": v["root"], "gates": []}

    for step in recipe.produces(parsed):
        core._safe(d, step["output"])

    missing = run.preflight(parsed)
    if missing:
        return {"ok": False, "environment": missing, "root": v["root"],
                "gates": [{"output": g["output"], "status": "environment", "quarantine": None}
                          for g in gate_steps]}

    try:
        bin_dir = _furnish(d, parsed)
    except core.ClaimError:
        return {"ok": False, "root": v["root"],
                "gates": [{"output": g["output"], "status": "environment", "quarantine": None}
                          for g in gate_steps]}

    sealed_parts = build._sealed_parts(d)

    # THE ROOM MATCHES THE NAME: at format >= 3 the root preimage strips
    # producer guidance from the recipe, so a gate judged in place must see
    # exactly that -- not the authored file with guidance still in it, or
    # two claims sharing one root could earn different verdicts by reading
    # their own recipe text (spec/identity.md). Swap the on-disk recipe for
    # its guidance-stripped form only while the gates run, then restore it.
    recipe_file = recipe.recipe_path(d)
    fmt = parsed.get("claim", {}).get("format", 1)
    original_recipe_bytes = None
    if fmt >= 3:
        with open(recipe_file, "rb") as f:
            original_recipe_bytes = f.read()
        build._write_toml_recipe(recipe_file, identity._preimage_recipe(parsed))

    try:
        gates_out, ok = [], True
        for step in gate_steps:
            cmd = step["run"]
            if bin_dir:
                cmd = f'export PATH="{bin_dir}:$PATH"; {cmd}'
            res = run_gate(cmd, d, parsed)
            status = res["status"]
            if status == "ok":
                status = "ok" if build._compare_pin(d, step, sealed_parts) else "mismatch"
            if status != "ok":
                ok = False
            gates_out.append({"output": step["output"], "status": status, "quarantine": res["quarantine"]})
    finally:
        if original_recipe_bytes is not None:
            with open(recipe_file, "wb") as f:
                f.write(original_recipe_bytes)
    return {"ok": ok, "root": v["root"], "gates": gates_out}


# ==== rebuild: component reuse, threaded inputs, the tamper watch ==========

def _room_snapshot(into: str, parsed: dict) -> dict:
    """A hash of every pinned input, pinned produce output, and the room's
    own recipe -- taken right after materialization (and any deliberate
    produce_from/input_from substitution), to be checked again after the
    producer runs."""
    snap = {}
    paths = list(recipe._inputs(into, parsed))
    for step in recipe.produces(parsed):
        if identity._effective_class(step) == "pinned":
            paths.append(step["output"])
    for path in paths:
        try:
            snap[path] = core._hash_file(core._safe(into, path))
        except core.ClaimError:
            snap[path] = None
    snap["__recipe__"] = core._hash_file(recipe.recipe_path(into))
    return snap


def rebuild(d: str, producer: str, into: str, produce_from=None, input_from=None,
            guidance: bool = True, producer_env=None) -> dict:
    """Regrow `d`'s generated outputs in a fresh room at `into`, earn the
    gates there, and seal the result (spec/kernel-api.md)."""
    parsed = load_recipe(d)
    missing = run.preflight(parsed)
    if missing:
        raise core.ClaimError(f"missing environment requirements: {missing}")

    build._materialize(d, into, parsed)
    os.makedirs(os.path.join(into, core.STORE), exist_ok=True)

    if produce_from:
        for output, src in produce_from.items():
            core._copy_into(src, core._safe(into, output))
            run.ledger(into, {"event": "reuse", "output": output})

    if input_from:
        for name, src in input_from.items():
            core._copy_into(src, core._safe(into, name))

    snapshot = _room_snapshot(into, parsed)

    build._produce(into, parsed, producer, guidance=guidance, producer_env=producer_env)

    if _room_snapshot(into, parsed) != snapshot:
        raise core.ClaimError("producer rewrote pinned bytes or the recipe")

    usage = build._read_usage(into)
    entry = {"kind": "rebuild", "calls": 1}
    if usage:
        entry.update(usage)
    run.ledger(into, entry)

    vendor = os.environ.get(core._ENV_VENDOR)
    model = os.environ.get(core._ENV_MODEL)
    if vendor or model:
        run.ledger(into, {"event": "producer", "vendor": vendor, "model": model, "blind": True})

    bin_dir = _furnish(into, parsed)

    quarantine = None
    for step in recipe.gates(parsed):
        cmd = step["run"]
        if bin_dir:
            cmd = f'export PATH="{bin_dir}:$PATH"; {cmd}'
        res = run_gate(cmd, into, parsed)
        quarantine = res["quarantine"]
        run.ledger(into, {"event": "gate", "output": step["output"],
                           "status": res["status"], "quarantine": quarantine})
        if res["status"] != "ok":
            raise core.ClaimError(f"gate {step['output']!r} did not pass: {res['status']}")

    run.ledger(into, {"event": "environment", "python": platform.python_version(),
                       "quarantine": quarantine or "none"})

    manifest = seal(into)
    return {"root": manifest["root"], "name": manifest["name"], "quarantine": quarantine}


# ==== phase: signed authorization ===========================================

def _signed(d: str, manifest: dict) -> bool:
    """Whether `manifest`'s recorded proof is authorized by a signature
    this process trusts, over a packet that still matches the live claim."""
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):
        return False
    sign_dir = os.path.join(d, core.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return False
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
        identity_name = stmt.get("identity")
        stmt_root = stmt.get("root")
        packet_digest = stmt.get("packet_digest")
        if not isinstance(identity_name, str) or not isinstance(stmt_root, str) \
                or not isinstance(packet_digest, str):
            continue
        if stmt_root != manifest.get("root"):
            continue
        if not build._ssh_verify(anchor, core.SIGN_NAMESPACE, identity_name, sig_path, stmt_bytes):
            continue
        prefix = fname[: -len(".sign.json")]
        packet_path = os.path.join(sign_dir, prefix + ".packet.json")
        if not os.path.isfile(packet_path):
            continue
        with open(packet_path, "rb") as f:
            packet_bytes = f.read()
        if hashlib.sha256(packet_bytes).hexdigest() != packet_digest:
            continue
        try:
            packet = json.loads(packet_bytes)
        except json.JSONDecodeError:
            continue
        if packet.get("root") != manifest.get("root"):
            continue
        if not packet.get("proof") or packet["proof"] != manifest.get("proof"):
            continue
        if packet.get("build_digest") != identity.build_digest(d):
            continue
        return True
    return False


def phase(d: str) -> str:
    """`draft` / `sealed` / `signed` (spec/verification.md)."""
    manifest_path = os.path.join(d, core.MANIFEST)
    if not os.path.isfile(manifest_path):
        load_recipe(d)
        return "draft"
    manifest = _seal.read_manifest(d)
    v = verify(d)
    if not v["ok"]:
        raise core.ClaimError(f"phase: claim at {d!r} does not verify")
    if not manifest.get("proof"):
        return "sealed"
    if _signed(d, manifest):
        return "signed"
    return "sealed"


# ==== records as crosscheck legs ============================================

def record_read(path: str) -> dict:
    """A record, refused unless its bytes are exactly its own canonical
    form (spec/record.md)."""
    with open(path, "rb") as f:
        raw = f.read()
    doc = attest.record_read(path)
    if attest.record_canonical(doc) != raw:
        raise core.ClaimError(f"record {path!r} is not its own canonical bytes")
    return doc


# ==== independence (declared, never proven) =================================

def _producer_declared(leg: str):
    if os.path.isdir(leg):
        for e in reversed(run.ledger_events(leg)):
            if e.get("event") == "producer":
                return {"vendor": e.get("vendor"), "model": e.get("model"), "blind": e.get("blind")}
        return None
    try:
        doc = record_read(leg)
    except core.ClaimError:
        return None
    p = doc.get("producer")
    if not p:
        return None
    return {"vendor": p.get("vendor"), "model": p.get("model"), "blind": p.get("blind")}


def independence(d: str) -> dict:
    """What this leg's producer declared about itself -- a declaration,
    never proof (spec/verification.md)."""
    return _producer_declared(d) or {"vendor": None, "model": None, "blind": None}


def _independence_line(p1, p3) -> str:
    if p3 and (p3.get("vendor") or p3.get("model")):
        vendor = p3.get("vendor") or "unknown"
        model = p3.get("model") or "unknown"
        workspace = "blind" if p3.get("blind") else "sighted"
        return f"declared: {vendor}/{model}, {workspace} workspace (not proven)"
    return "unestablished (no producer declared)"


# ==== sign_node: the bottom-anchored signature chain ========================

def sign_node(root: str, digest: str, links) -> str:
    """One signature-chain node: deterministic over the root, the build
    digest, and the SET of signatures beneath it."""
    payload = {"root": root, "build_digest": digest, "links": sorted(set(links))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ==== sandbox: a convenience probe/run ======================================

def sandbox(cmd=None, d="."):
    if cmd is None:
        probe = run.sandbox()
        return (probe["functional"], probe["backend"])
    res = run_gate(cmd, d, None)
    return (res["status"], res["quarantine"])


# ==== the three-machine test and the recorded proof =========================

def _leg_info(path: str) -> dict:
    if os.path.isdir(path):
        v = verify(path)
        a = audit(path)
        return {
            "directory": True,
            "root": v["root"],
            "build_digest": identity.build_digest(path),
            "ok": a["ok"],
            "cost": run.cost(path),
            "producer": _producer_declared(path),
            "record_version": None,
            "claim": None,
        }
    doc = record_read(path)
    ok = all(g["status"] == "ok" for g in doc["gates"])
    return {
        "directory": False,
        "root": doc["root"],
        "build_digest": doc["build_digest"],
        "ok": ok,
        "cost": doc.get("cost"),
        "producer": doc.get("producer"),
        "record_version": doc["record"],
        "claim": doc.get("claim") if doc["record"] >= 2 else None,
    }


def _cost_comparable(c1, c3, tolerance):
    """The strongest shared cost unit's ratio, within `[1/tol, tol]`, or
    `None` when nothing is measurable on both sides."""
    if not c1 or not c3:
        return None
    tol = tolerance if tolerance is not None else core.TOLERANCE
    for unit in core.COST_LADDER:
        if unit in c1 and unit in c3:
            v1, v3 = c1[unit], c3[unit]
            if v1 == 0:
                return v3 == 0
            ratio = v3 / v1
            return (1.0 / tol) <= ratio <= tol
    return None


def crosscheck(m1: str, m2: str, m3: str, mutants=None) -> dict:
    """The three-machine test: one root, every verdict earned, byte reuse
    on transfer, and every condition the claim itself declares
    (spec/verification.md)."""
    legs = (m1, m2, m3)
    if len({os.path.realpath(p) for p in legs}) < 3:
        raise core.ClaimError("crosscheck requires three distinct legs")

    L1, L2, L3 = (_leg_info(p) for p in legs)
    roots = {"M1": L1["root"], "M2": L2["root"], "M3": L3["root"]}
    equivalence = len(set(roots.values())) == 1
    reuse = L1["build_digest"] == L2["build_digest"]
    audited = {"M1": L1["ok"], "M2": L2["ok"], "M3": L3["ok"]}

    rejected, incomplete = [], []
    if not equivalence:
        rejected.append("root")
    for key, ok in audited.items():
        if not ok:
            rejected.append(f"audit:{key}")
    if equivalence and not reuse:
        rejected.append("reuse")

    if L1["directory"]:
        parsed1 = load_recipe(m1)
        declared = {k: v for k, v in parsed1.get("claim", {}).items()
                    if k in ("tolerance", "envelope", "mutation_floor")}
    elif L1["record_version"] == 1:
        declared = None
        incomplete.append("declared_conditions")
    else:
        declared = L1["claim"] or {}

    c1, c3 = L1["cost"], L3["cost"]
    tol_declared = declared.get("tolerance") if declared is not None else None
    comparable = _cost_comparable(c1, c3, tol_declared)

    envelope_report = {}
    mutation_result = None
    if declared is not None:
        if tol_declared is not None:
            if comparable is None:
                incomplete.append("tolerance")
            elif comparable is False:
                rejected.append("tolerance")

        for unit, ceiling in (declared.get("envelope") or {}).items():
            measured = (c3 or {}).get(unit)
            if measured is None:
                envelope_report[unit] = {"ceiling": ceiling, "measured": None, "within": None}
                incomplete.append(f"envelope {unit}")
            else:
                within = measured <= ceiling
                envelope_report[unit] = {"ceiling": ceiling, "measured": measured, "within": within}
                if not within:
                    rejected.append(f"envelope {unit}")

        floor = declared.get("mutation_floor")
        if floor is not None:
            if mutants is None:
                incomplete.append("mutation_floor")
            else:
                ms = mutation_score(m3, max_mutants=mutants)
                mutation_result = dict(ms)
                mutation_result["ok"] = ms["rate"] >= floor
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
        "reuse": reuse,
        "audited": audited,
        "cost": {"comparable": comparable, "envelope": envelope_report},
        "mutation_score": mutation_result,
        "independence": _independence_line(L1["producer"], L3["producer"]),
    }


def record_proof(m1: str, m2: str, m3: str) -> dict:
    """Run the crosscheck; on a pass, seal the proof onto M1 as residue
    (spec/kernel-api.md). M1 must be a directory; record legs must verify
    against the anchor, and their digests and signer identities are
    embedded in the proof (spec/verification.md)."""
    if not os.path.isdir(m1):
        raise core.ClaimError("a proof can only be recorded on a directory leg (M1)")
    result = crosscheck(m1, m2, m3)
    if result["verdict"] != "accept":
        return {"proof_recorded": False, **result}

    anchor = os.environ.get(core._ENV_SIGNERS)
    records_meta = []
    for label, leg in (("M2", m2), ("M3", m3)):
        if os.path.isdir(leg):
            continue
        doc = record_read(leg)
        signer = attest.record_signer(leg, anchor) if anchor and os.path.isfile(anchor) else None
        if signer is None:
            raise core.ClaimError(
                f"{label} record is unanchored or unsigned: refusing to record a proof")
        records_meta.append({"leg": label, "digest": attest.record_digest(doc), "signer": signer})

    proof = {"kind": "crosscheck", "m2": result["roots"]["M2"], "m3": result["roots"]["M3"]}
    if records_meta:
        proof["records"] = records_meta

    manifest = _seal.read_manifest(m1)
    manifest["proof"] = proof
    core._write_json(os.path.join(m1, core.MANIFEST), manifest)
    return {"proof_recorded": True, **result}
