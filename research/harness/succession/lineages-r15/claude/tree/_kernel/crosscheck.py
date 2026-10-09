"""The three-machine test, and the machinery it leans on: gate-decider
analysis (which workspace scripts a gate's `run` command actually executes,
so a gate whose every decider is generated code can be named VACUOUS), a
small deterministic mutation engine (mutants of generated Python code, drawn
from the claim's own root, re-audited to produce a kill rate), and the cost /
independence reporting the crosscheck's report carries.

`crosscheck(m1, m2, m3)` accepts a leg as either a claim directory (the
caller's own execution) or a record file (`spec/record.md`, a frozen
statement of someone else's execution) -- one predicate, two transports.

Stdlib only.
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

from . import attest, build, core, identity, recipe, run, seal
from .core import ClaimError

# -- Identity, with the two rules `identity.py` cannot express on its own:
# a declared path must be a regular file with a single hard link
# (`spec/identity.md`'s file-hashing rules), and a declared `[claim]
# environment` file is automatically a pinned input (`spec/claim-format.md`).
# Every verb below that recomputes identity (audit, the leg view, the
# public `kernel.root`/`seal`) shares this one computation, so a claim's
# root means the same thing wherever it is recomputed. -------------------


def _check_hashable(d: str, path: str) -> None:
    full = core._safe(d, path)
    try:
        st = os.stat(full)
    except OSError as e:
        raise ClaimError(f"cannot stat declared path {path!r}: {e}") from e
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"declared path is not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"declared path has more than one hard link: {path!r}")


def _declared_inputs(d: str, doc: dict) -> list:
    inputs = list(recipe._inputs(d, doc))
    env_file = doc.get("claim", {}).get("environment")
    if env_file and env_file not in inputs:
        inputs.append(env_file)
    return inputs


def _parts(doc: dict, d: str) -> dict:
    parts = {
        "digest": core.DIGEST,
        "recipe": identity._canonical_json(identity._preimage_recipe(doc)),
    }
    for path in _declared_inputs(d, doc):
        _check_hashable(d, path)
        parts["input:" + path] = core._hash_file(core._safe(d, path))
    for step in doc.get("step", []):
        kind = step["kind"]
        cls = step.get("class")
        if kind == "produce" and (cls if cls is not None else "generated") in ("generated", "free"):
            continue
        path = step["output"]
        _check_hashable(d, path)
        parts["pinned:" + path] = core._hash_file(core._safe(d, path))
    return parts


def root(doc: dict, d: str) -> str:
    """The claim's identity (`spec/identity.md`)."""
    preimage = identity._canonical_json(_parts(doc, d))
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


# -- Gate-decider analysis: which workspace scripts a `run` command executes,
# as opposed to data it merely reads. ------------------------------------

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})

_OP_PATTERN = re.compile(
    "|".join(re.escape(op) for op in sorted(_OPERATORS, key=len, reverse=True))
)


def _strip_local(token: str) -> str:
    return token[2:] if token.startswith("./") else token


def _machine(cmd: str) -> list:
    """Parse a gate's shell `run` command into the workspace scripts it
    executes, in invocation order -- its deciders. An interpreter
    invocation's first non-flag positional argument is the script; a bare
    local path (containing `/`) is itself the script. Flags are skipped;
    a flag in `_SKIP_VALUE` also skips the value that follows it.
    """
    deciders = []
    for piece in _OP_PATTERN.split(cmd):
        piece = piece.strip()
        if not piece:
            continue
        try:
            tokens = shlex.split(piece)
        except ValueError:
            continue
        if not tokens:
            continue
        head = tokens[0]
        if head in _INTERPRETERS:
            i = 1
            while i < len(tokens):
                tok = tokens[i]
                if tok in _SKIP_VALUE:
                    i += 2
                    continue
                if tok.startswith("-"):
                    i += 1
                    continue
                deciders.append(tok)
                break
        elif "/" in head:
            deciders.append(_strip_local(head))
    return deciders


def gate_deciders(cmd: str) -> list:
    """Which workspace files decide a gate's `run` command: scripts the
    command executes, not data it merely reads (`spec/verification.md`,
    the GATES COMPOSE clause).
    """
    return _machine(cmd)


def vacuous_gates(parsed: dict) -> list:
    """Gate outputs whose every decider is generated code: the verdict
    depends on no claim, so the root fits any implementation that prints
    the pinned bytes (`spec/claim-format.md`). A gate with no deciders at
    all decides by its own written logic, not vacuously.
    """
    claim = parsed.get("claim", {})
    pinned_inputs = set(claim.get("inputs", []))
    generated = set()
    for step in parsed.get("step", []):
        if step.get("kind") == "produce" and \
                step.get("class", "generated") in ("generated", "free"):
            generated.add(step.get("output"))

    vacuous = []
    for step in parsed.get("step", []):
        if step.get("kind") != "gate":
            continue
        deciders = gate_deciders(step.get("run", ""))
        if deciders and all(p in generated and p not in pinned_inputs for p in deciders):
            vacuous.append(step["output"])
    return vacuous


# -- The confined gate runner: run.py's logic, with the one fix the kernel
# suite pins -- RETICULI_JAILED must name the backend, not a placeholder, so
# a gate that is itself a claim runner can tell it must inherit rather than
# nest. -------------------------------------------------------------------


def run_gate(cmd: str, workspace: str, recipe_doc=None, venv_bin=None) -> dict:
    """Run one gate: scrubbed env, sandboxed, bounded -- and, where a
    sandbox is really applied, told to the wrapped process by its own name
    (`spec/verification.md`'s execution contract).
    """
    backend = run.sandbox_backend()
    timeout = run.gate_timeout(recipe_doc)
    env = run._scrub_env()
    if venv_bin:
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")

    scratch = os.path.join(workspace, core.STORE, "room")
    os.makedirs(scratch, exist_ok=True)
    if backend not in ("none", "inherited"):
        env["TMPDIR"] = scratch
        env["HOME"] = scratch
        env[core._JAILED] = backend

    argv = run._sandbox_argv(backend, workspace, scratch, cmd)
    result = run._run(argv, workspace, env, timeout)

    if result["timed_out"]:
        status = "timeout"
    elif result["returncode"] == 0:
        status = "ok"
    else:
        status = "failed"

    return {
        "status": status,
        "quarantine": backend,
        "returncode": result["returncode"],
        "stdout": result["stdout"].decode("utf-8", "replace"),
        "stderr": result["stderr"].decode("utf-8", "replace"),
    }


# -- Cost: ledger totals, wall-clock included -- the kernel's own
# measurement, never a producer's self-report. ---------------------------


def cost(d: str):
    """Ledger totals per unit (usd/tokens/calls/seconds); `None` if nothing
    was measured. Totals carry only the keys the ledger names.
    """
    totals = {}
    for e in run.ledger_events(d):
        for key in core.COST_KEYS:
            v = e.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                totals[key] = totals.get(key, 0) + v
    return totals or None


# -- Independence: declared, never proven by content alone. --------------


def independence(d: str) -> dict:
    """Declared producer identity for the generated bytes in claim `d`:
    the last producer-kind ledger event's vendor/model, and whether the
    workspace was blind (it always is, for a kernel rebuild -- the room
    never receives pre-existing generated bytes). `None`s when nothing was
    produced here.
    """
    events = [e for e in run.ledger_events(d) if e.get("kind") == "producer"]
    if not events:
        return {"vendor": None, "model": None, "blind": None}
    last = events[-1]
    return {"vendor": last.get("vendor"), "model": last.get("model"), "blind": True}


def _independence_string(info: dict) -> str:
    vendor, model, blind = info.get("vendor"), info.get("model"), info.get("blind")
    if not vendor and not model:
        return "unestablished: producer identity not declared"
    who = f"{vendor or '?'}/{model or '?'}"
    workspace = "blind workspace" if blind else "sighted workspace"
    return f"declared: {who}, {workspace} (not proven by content alone)"


def furnish(doc: dict, d: str):
    """`run.furnish`, run with the claim directory as cwd: a `requirements.lock`
    naming a LOCAL wheel by a relative path (`./probe-1.0-....whl`) is resolved
    by pip relative to the process's cwd, not the lock file's own directory --
    so a caller whose cwd is elsewhere (the common case) sees a furnish that
    cannot find a wheel sitting right next to the lock file.
    """
    claim = (doc or {}).get("claim", {})
    env_file = claim.get("environment")
    if not env_file:
        return run.furnish(doc, d)
    full = core._safe(d, env_file)
    cwd = os.getcwd()
    os.chdir(os.path.dirname(full) or d)
    try:
        return run.furnish(doc, d)
    finally:
        os.chdir(cwd)


# -- Audit: deep re-earning, with the shapes this suite pins -- an
# environment failure names itself on every gate row, and substituted
# generated bytes (produce_from) are judged by this claim's own gate. ----


def audit(d: str, shallow: bool = False, produce_from=None) -> dict:
    doc = recipe.load_recipe(d)

    gate_steps = recipe.gates(doc)
    missing = run.preflight(doc)
    if missing:
        gates_report = [{"output": s["output"], "status": "environment",
                         "quarantine": None} for s in gate_steps]
        return {"ok": False, "verdict": "environment", "environment": missing,
                "gates": gates_report}

    try:
        venv_bin = furnish(doc, d)
    except ClaimError as e:
        gates_report = [{"output": s["output"], "status": "environment",
                         "quarantine": None} for s in gate_steps]
        return {"ok": False, "verdict": "environment", "environment": [str(e)],
                "gates": gates_report}

    manifest = seal.read_manifest(d)
    recomputed = root(doc, d)

    if recomputed != manifest["root"]:
        return {"ok": False, "verdict": "broken", "root": recomputed,
                "reason": "identity does not hold: pinned bytes changed",
                "gates": [], "environment": []}

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        build._materialize(doc, d, room, include_generated=True)
        if produce_from:
            for rel, src_path in produce_from.items():
                target = core._safe(room, rel)
                os.makedirs(os.path.dirname(target) or room, exist_ok=True)
                shutil.copy2(src_path, target)

        gate_results = []
        earned = True
        for step in gate_steps:
            result = run_gate(step["run"], room, doc, venv_bin=venv_bin)
            output = step["output"]
            if result["status"] != "ok":
                status = result["status"]
            elif not os.path.isfile(core._safe(room, output)):
                status = "mismatch"
            elif build._compare_pin(d, room, output):
                status = "ok"
            else:
                status = "mismatch"
            if status != "ok":
                earned = False
            gate_results.append({"output": output, "status": status,
                                 "quarantine": result["quarantine"]})

        sub_ok = True
        if not shallow:
            for _name, rel in build._components(manifest).items():
                sub = audit(core._safe(d, rel), shallow=False)
                if not sub.get("ok"):
                    sub_ok = False
        earned = earned and sub_ok

        return {"ok": earned, "verdict": "earned" if earned else "broken",
                "root": recomputed, "gates": gate_results, "environment": []}
    finally:
        shutil.rmtree(room, ignore_errors=True)


# -- Mutation score: deterministic mutants of generated Python code, drawn
# from the claim's own root, re-audited; the kill rate is residue. -------

_ARITHMETIC = ('+', '-', '*', '/', '//', '%', '**')

_CMP_AST = {'>': ast.Gt, '<': ast.Lt, '>=': ast.GtE, '<=': ast.LtE,
            '==': ast.Eq, '!=': ast.NotEq}
_CMP_SYM = {v: k for k, v in _CMP_AST.items()}

_ARITH_AST = {'+': ast.Add, '-': ast.Sub, '*': ast.Mult, '/': ast.Div,
              '//': ast.FloorDiv, '%': ast.Mod, '**': ast.Pow}
_ARITH_SYM = {v: k for k, v in _ARITH_AST.items()}

_OP_KIND = {}
for _sym in _COMPARISON:
    _OP_KIND[_sym] = "comparison"
for _sym in _ARITHMETIC:
    _OP_KIND[_sym] = "arithmetic"

_OP_ALTS = {}
for _sym in _COMPARISON:
    _OP_ALTS[_sym] = tuple(s for s in _COMPARISON if s != _sym)
for _sym in _ARITHMETIC:
    _OP_ALTS[_sym] = tuple(s for s in _ARITHMETIC if s != _sym)

_WORD_ALTS = {"True": ("False",), "False": ("True",)}

_STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', re.DOTALL)


def _node_span(source: str, node) -> tuple:
    """The (start, end) character offsets of `node` within `source`."""
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    start = starts[node.lineno - 1] + node.col_offset
    end = starts[node.end_lineno - 1] + node.end_col_offset
    return (start, end)


def _span_text(source: str, span: tuple) -> str:
    return source[span[0]:span[1]]


def _splice(source: str, span: tuple, text: str) -> str:
    return source[:span[0]] + text + source[span[1]:]


def _edit(source: str, span: tuple, text: str) -> str:
    """Apply one candidate mutation (a `_mutants` span/text pair) to `source`."""
    return _splice(source, span, text)


def _named(node) -> str:
    """A stable textual label for an AST node, by kind and position."""
    return f"{type(node).__name__}@{getattr(node, 'lineno', 0)}:{getattr(node, 'col_offset', 0)}"


def _label(node, before, after) -> str:
    return f"{_named(node)} {before!r}->{after!r}"


def _docstring_spans(tree, source: str) -> list:
    """Spans of module/function/class docstrings -- excluded from mutation,
    since a docstring cannot decide a gate's verdict.
    """
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                spans.append(_node_span(source, body[0]))
    return spans


def _in_any(span, skip) -> bool:
    return any(s <= span[0] < e for s, e in skip)


def _token_mutants(tree, source: str) -> list:
    """Candidate mutants from single operators and boolean literals:
    comparisons, arithmetic, `True`/`False`.
    """
    mutants = []
    skip = _docstring_spans(tree, source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            sym = _CMP_SYM.get(type(node.ops[0]))
            if sym is None:
                continue
            span = _node_span(source, node)
            if _in_any(span, skip):
                continue
            left = _span_text(source, _node_span(source, node.left))
            right = _span_text(source, _node_span(source, node.comparators[0]))
            for alt in _OP_ALTS[sym]:
                mutants.append({"span": span, "text": f"{left} {alt} {right}",
                                "label": _label(node, sym, alt)})
        elif isinstance(node, ast.BinOp):
            sym = _ARITH_SYM.get(type(node.op))
            if sym is None:
                continue
            span = _node_span(source, node)
            if _in_any(span, skip):
                continue
            left = _span_text(source, _node_span(source, node.left))
            right = _span_text(source, _node_span(source, node.right))
            for alt in _OP_ALTS[sym]:
                mutants.append({"span": span, "text": f"{left} {alt} {right}",
                                "label": _label(node, sym, alt)})
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            word = "True" if node.value else "False"
            span = _node_span(source, node)
            if _in_any(span, skip):
                continue
            for alt in _WORD_ALTS.get(word, ()):
                mutants.append({"span": span, "text": alt,
                                "label": _label(node, word, alt)})
    return mutants


def _structural_mutants(tree, source: str) -> list:
    """Candidate mutants from control-flow structure: a negated `if` test,
    an early `return None`, a swapped `break`/`continue`.
    """
    mutants = []
    skip = _docstring_spans(tree, source)
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            span = _node_span(source, node.test)
            if _in_any(span, skip):
                continue
            text = _span_text(source, span)
            mutants.append({"span": span, "text": f"not ({text})",
                            "label": _label(node, "if", "not if")})
        elif isinstance(node, ast.Return) and node.value is not None:
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                continue
            span = _node_span(source, node.value)
            if _in_any(span, skip):
                continue
            mutants.append({"span": span, "text": "None",
                            "label": _label(node, "return", "return None")})
        elif isinstance(node, (ast.Break, ast.Continue)):
            span = _node_span(source, node)
            alt = "continue" if isinstance(node, ast.Break) else "break"
            mutants.append({"span": span, "text": alt,
                            "label": _label(node, type(node).__name__, alt)})
    return mutants


def _mutants(source: str) -> list:
    """Every candidate mutant of `source` -- token-level and structural."""
    tree = ast.parse(source)
    return _token_mutants(tree, source) + _structural_mutants(tree, source)


def _draw_order(n: int, seed: str) -> list:
    """A deterministic permutation of `range(n)`, seeded by `seed`."""
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        h = hashlib.sha256(f"{seed}:{i}".encode("utf-8")).digest()
        j = int.from_bytes(h[:8], "big") % (i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def _mutant_order(mutants: list, root: str) -> list:
    """`mutants`, drawn into a deterministic order seeded by `root` -- the
    claim's own identity decides the sample, not an implementation's whim.
    """
    order = _draw_order(len(mutants), root)
    return [mutants[i] for i in order]


def _run_mutant(d: str, doc: dict, path: str, mutated_source: str, venv_bin) -> bool:
    """Materialize a fresh room from claim `d` with `path` replaced by
    `mutated_source`, run the gates, and report killed (`True`) or survived
    (`False`) -- every gate `ok` and every pinned byte reproduced counts as
    survived.
    """
    room = tempfile.mkdtemp(prefix="reticuli-mutant-")
    try:
        build._materialize(doc, d, room, include_generated=True)
        full = core._safe(room, path)
        with open(full, "w", encoding="utf-8") as f:
            f.write(mutated_source)
        for step in recipe.gates(doc):
            result = run_gate(step["run"], room, doc, venv_bin=venv_bin)
            output = step["output"]
            if result["status"] != "ok":
                return True
            if not os.path.isfile(core._safe(room, output)):
                return True
            if not build._compare_pin(d, room, output):
                return True
        return False
    finally:
        shutil.rmtree(room, ignore_errors=True)


def mutation_score(d: str, max_mutants=None) -> dict:
    """Deterministic mutants of claim `d`'s generated Python code, drawn
    from the root, re-audited; the kill rate is residue
    (`spec/verification.md`).
    """
    doc = recipe.load_recipe(d)
    manifest = seal.read_manifest(d)
    root_hex = manifest["root"]
    cap = max_mutants if max_mutants is not None else core.MUTANT_CEILING
    venv_bin = furnish(doc, d)

    candidates = []
    for path in recipe.generated_outputs(doc):
        if not path.endswith(".py"):
            continue
        full = core._safe(d, path)
        if not os.path.isfile(full):
            continue
        with open(full, "r", encoding="utf-8") as f:
            source = f.read()
        try:
            for m in _mutants(source):
                m = dict(m)
                m["path"] = path
                m["source"] = source
                candidates.append(m)
        except SyntaxError:
            continue

    ordered = _mutant_order(candidates, root_hex)
    chosen = ordered[:cap] if cap else ordered

    killed = 0
    survivors = []
    for m in chosen:
        mutated = _edit(m["source"], m["span"], m["text"])
        if _run_mutant(d, doc, m["path"], mutated, venv_bin):
            killed += 1
        else:
            survivors.append(m["label"])

    total = len(chosen)
    rate = (killed / total) if total else 1.0
    survivors.sort()
    result = {"mutants": total, "killed": killed, "rate": rate, "survivors": survivors}
    core._write_json(os.path.join(d, core.MUTATION_RESIDUE), result)
    return result


# -- The three-machine test ------------------------------------------------


def _leg_view(path: str) -> dict:
    """Everything `crosscheck` needs from one leg, uniformly whether it is
    a claim directory (a live execution) or a record file (a frozen one).
    """
    if os.path.isdir(path):
        doc = recipe.load_recipe(path)
        claim = doc.get("claim", {})
        declared = {k: claim[k] for k in ("tolerance", "envelope", "mutation_floor")
                    if k in claim}
        return {
            "root": root(doc, path),
            "build_digest": identity.build_digest(path),
            "audited": build.audit(path)["ok"],
            "cost": cost(path),
            "declared": declared,
            "declared_known": True,
            "independence": independence(path),
            "path_is_dir": True,
            "dir": path,
        }

    doc = attest.record_read(path)
    declared_known = "claim" in doc
    declared = doc.get("claim") or {}
    gates = doc.get("gates", [])
    audited = bool(gates) and all(g["status"] == "ok" for g in gates)
    producer = doc.get("producer") or {}
    return {
        "root": doc["root"],
        "build_digest": doc["build_digest"],
        "audited": audited,
        "cost": doc.get("cost"),
        "declared": declared,
        "declared_known": declared_known,
        "independence": {"vendor": producer.get("vendor"),
                         "model": producer.get("model"),
                         "blind": producer.get("blind")},
        "path_is_dir": False,
        "dir": None,
    }


def _comparable(c1, c3, tolerance: float):
    """Is M3's cost within `tolerance` of M1's, on the strongest unit both
    measured (usd > tokens > calls > seconds)? `None` if no shared unit.
    """
    if not c1 or not c3:
        return None
    for unit in core.COST_LADDER:
        if unit in c1 and unit in c3:
            v1, v3 = c1[unit], c3[unit]
            if v1 <= 0:
                return None
            ratio = v3 / v1
            return (1.0 / tolerance) <= ratio <= tolerance
    return None


def _envelope_check(envelope, c3) -> dict:
    report = {}
    for unit, ceiling in (envelope or {}).items():
        measured = (c3 or {}).get(unit)
        if measured is None:
            report[unit] = {"within": None, "ceiling": ceiling, "measured": None}
        else:
            report[unit] = {"within": measured <= ceiling, "ceiling": ceiling,
                            "measured": measured}
    return report


def _mutation_for_leg(leg: dict, mutants, floor):
    if not mutants or not leg.get("path_is_dir") or not leg.get("dir"):
        return None
    result = dict(mutation_score(leg["dir"], max_mutants=mutants))
    if floor is not None:
        result["ok"] = result["rate"] >= floor
    return result


def crosscheck(m1: str, m2: str, m3: str, mutants=None) -> dict:
    """The three-machine test (`spec/verification.md`): valid iff one root
    across all three, every verdict re-earned, byte reuse between M1 and
    M2, and the cost envelope holds. Each leg is a claim directory or a
    record file; the predicate is the same either way.
    """
    legs = (m1, m2, m3)
    resolved = [os.path.realpath(p) for p in legs]
    if len(set(resolved)) < 3:
        raise ClaimError("crosscheck requires three distinct machines")

    leg1, leg2, leg3 = (_leg_view(p) for p in legs)

    roots = {"M1": leg1["root"], "M2": leg2["root"], "M3": leg3["root"]}
    equivalence = roots["M1"] == roots["M2"] == roots["M3"]
    reuse = leg1["build_digest"] == leg2["build_digest"]
    audited = {"M1": leg1["audited"], "M2": leg2["audited"], "M3": leg3["audited"]}

    declared = leg1["declared"]
    declared_known = leg1["declared_known"]

    rejected = []
    incomplete = []

    if not equivalence:
        rejected.append("root")
    if not reuse:
        rejected.append("reuse")
    if not all(audited.values()):
        rejected.append("audited")

    tolerance = declared.get("tolerance", core.TOLERANCE)
    comparable = _comparable(leg1["cost"], leg3["cost"], tolerance)
    if "tolerance" in declared:
        if comparable is False:
            rejected.append("tolerance")
        elif comparable is None:
            incomplete.append("tolerance")

    envelope_report = _envelope_check(declared.get("envelope"), leg3["cost"])
    for unit, info in envelope_report.items():
        if info["within"] is False:
            rejected.append(f"envelope {unit}")
        elif info["within"] is None:
            incomplete.append(f"envelope {unit}")

    mscore = None
    if "mutation_floor" in declared:
        if mutants:
            mscore = _mutation_for_leg(leg3, mutants, declared["mutation_floor"])
            if mscore is not None and not mscore["ok"]:
                rejected.append("mutation_floor")
            elif mscore is None:
                incomplete.append("mutation_floor")
        else:
            incomplete.append("mutation_floor")
    elif mutants:
        mscore = _mutation_for_leg(leg3, mutants, None)

    if not declared_known:
        incomplete.append("declared-conditions")

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
        "mutation_score": mscore,
        "independence": _independence_string(leg3["independence"]),
    }
