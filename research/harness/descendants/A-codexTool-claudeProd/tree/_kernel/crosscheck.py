"""The three-machine test, gate vacuity, and the mutation score.

**M1** verifies in place, **M2** is the claim received elsewhere from the
transferred bytes alone, **M3** is an independent rebuild from the pinned
inputs.  Valid ⇔ one root across all three ∧ every gate re-earned ∧ every
condition the claim DECLARED holds.

The verdict is three-valued, under one rule.  A **hard** condition must be
true to accept and rejects on false.  A hard condition the claim declared but
this run did not measure is neither true nor false: the verdict is
`incomplete`, and incomplete can never accept, because unknown evidence is
not evidence.  An **observation** never decides — producer independence is
recorded rather than enforced (content cannot prove blindness), and an
UNDECLARED cost band is reported, never a reason to reject.  That last point
has a counterexample on record: the first real three-machine proof was
rejected by the undeclared default band for exhibiting the ordinary gap
between what discovery cost and what a redo costs.

A leg may be a claim directory or a signed record: one predicate, two
transports, and they must reach the same verdict.

`vacuous_gates` names the gates whose every decider is generated — the
verdict then depends on no claim, so the root fits any implementation that
prints ok.  `mutation_score` measures the equivalence class's WIDTH: mutants
drawn deterministically from the root, re-audited, and the kill rate reported.
"""
import ast
import hashlib
import json
import os
import re
import shutil
import tempfile

from .core import (COST_LADDER, MUTANT_CEILING, MUTATION_RESIDUE, TOLERANCE,
                   ClaimError, _ENV_TOLERANCE, _finite, _now, _write_json)
from . import attest as _attest
from . import build as _build
from . import identity as _identity
from . import recipe as _recipe
from . import run as _run_mod
from . import seal as _seal

# -- the gate-command grammar ----------------------------------------------

#: Shell operators a gate command is split on before each piece is read.
_OPERATORS = frozenset({"&&", "||", ";", "|", "&", "\n"})
#: Programs that run a file given to them, so their first non-flag argument
#: is what actually decides the gate.
_INTERPRETERS = frozenset({
    "sh", "bash", "dash", "zsh", "python", "python3", "python2", "py",
    "pytest", "py.test", "node", "deno", "ruby", "perl", "php", "lua",
    "tclsh", "awk", "Rscript"})
#: Flags that consume the token after them, so it is not the decider.
_SKIP_VALUE = frozenset({"-m", "-c", "-e", "-p", "-X", "--module"})

# -- the mutation vocabulary ------------------------------------------------

_COMPARISON = (">", "<", ">=", "<=", "==", "!=")
_ARITHMETIC = ("+", "-", "*", "/", "//", "%", "**")
#: Each operator and the alternatives a mutant may put in its place.  Every
#: substitution keeps the source SYNTACTICALLY valid, so a surviving mutant
#: is a real gap in the criteria rather than an import error.
_OP_ALTS = {
    ">": ("<", ">=", "<=", "==", "!="),
    "<": (">", "<=", ">=", "==", "!="),
    ">=": ("<=", ">", "<", "==", "!="),
    "<=": (">=", "<", ">", "==", "!="),
    "==": ("!=",),
    "!=": ("==",),
    "+": ("-", "*"),
    "-": ("+", "*"),
    "*": ("+", "-"),
    "/": ("*", "+"),
    "//": ("/", "*"),
    "%": ("*", "+"),
    "**": ("*", "+"),
}
_OP_KIND = {op: ("comparison" if op in _COMPARISON else "arithmetic")
            for op in _OP_ALTS}
#: Bare words a mutant may flip; the same syntactic-validity rule applies.
_WORD_ALTS = {"True": ("False",), "False": ("True",),
              "and": ("or",), "or": ("and",)}
#: Where a mutation must NOT reach: inside a string literal, a mutated
#: operator is a changed message rather than a changed decision.
_STRING_LITERAL = re.compile(
    r"""('''(?:.|\n)*?'''|\"\"\"(?:.|\n)*?\"\"\"|'(?:\\.|[^'\\\n])*'"""
    r"""|\"(?:\\.|[^\"\\\n])*\")""")

_AST_OPS = {
    ast.Gt: ">", ast.Lt: "<", ast.GtE: ">=", ast.LtE: "<=",
    ast.Eq: "==", ast.NotEq: "!=",
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
}


# -- which files decide a gate ---------------------------------------------


def _pieces(command: str) -> list:
    """Split a gate command into the sub-commands the shell would run."""
    out, buffer, i = [], "", 0
    text = command or ""
    while i < len(text):
        two = text[i:i + 2]
        if two in _OPERATORS:
            out.append(buffer)
            buffer, i = "", i + 2
            continue
        if text[i] in _OPERATORS:
            out.append(buffer)
            buffer, i = "", i + 1
            continue
        buffer += text[i]
        i += 1
    out.append(buffer)
    return [piece.strip() for piece in out if piece.strip()]


def _tokens(piece: str) -> list:
    """Tokenize one sub-command, dropping redirections and their targets."""
    import shlex
    try:
        raw = shlex.split(piece)
    except ValueError:
        raw = piece.split()
    out, skip = [], False
    for token in raw:
        if skip:
            skip = False
            continue
        if token in (">", ">>", "<", "2>", "2>>", "&>"):
            skip = True
            continue
        if re.match(r"^\d?>>?", token) and len(token) > 2:
            continue
        out.append(token)
    return out


def gate_deciders(command: str) -> list:
    """Which workspace files decide this gate.

    A sub-command run through an INTERPRETER names its decider as its first
    non-flag argument; a sub-command that is itself a path in the workspace
    names itself.  Anything else — `grep`, `printf`, a plain shell builtin —
    decides by the recipe's own text, which is already inside the root, and
    contributes no decider.  The heuristic beyond these shapes is
    deliberately unpinned.
    """
    found = []
    for piece in _pieces(command):
        tokens = _tokens(piece)
        if not tokens:
            continue
        program, rest = tokens[0], tokens[1:]
        base = program.rsplit("/", 1)[-1]
        if base in _INTERPRETERS:
            index = 0
            while index < len(rest):
                token = rest[index]
                if token in _SKIP_VALUE:
                    index += 2
                    continue
                if token.startswith("-"):
                    index += 1
                    continue
                found.append(token)
                break
            continue
        if program.startswith("./"):
            found.append(program[2:])
        elif "/" in program and not program.startswith("/"):
            found.append(program)
    out = []
    for name in found:
        if name not in out:
            out.append(name)
    return out


def vacuous_gates(parsed: dict) -> list:
    """Gates whose every decider is generated — a verdict depending on no claim.

    The root would then fit any implementation that prints ok.  The kernel
    NAMES such gates; authoring refuses them, because class is declared and
    never inferred from provenance.
    """
    generated = set(_recipe.generated_outputs(parsed))
    out = []
    for gate in _recipe.gates(parsed):
        deciders = gate_deciders(gate.get("run", "") or "")
        if deciders and all(d in generated for d in deciders):
            out.append(gate["output"])
    return out


# -- the signature chain ----------------------------------------------------


def sign_node(root: str, digest: str, links) -> str:
    """One node of the signature chain: a layer's root, its bytes, and below.

    The build digest binds the concrete bytes the root ignores, and the fold
    binds the SET of signatures beneath — enumeration order is not identity,
    so a DAG folds the same however it is walked.
    """
    payload = {"root": root, "build_digest": digest,
               "below": sorted(links or [])}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# -- mutation ---------------------------------------------------------------


def _offsets(text: str) -> list:
    out = [0]
    for line in text.splitlines(keepends=True):
        out.append(out[-1] + len(line))
    return out


def _node_span(node, offsets: list):
    """A source span for an AST node, as (start, end) character offsets."""
    try:
        start = offsets[node.lineno - 1] + node.col_offset
        end = offsets[node.end_lineno - 1] + node.end_col_offset
    except (AttributeError, IndexError, TypeError):
        return None
    return (start, end)


def _span_text(text: str, span) -> str:
    return text[span[0]:span[1]] if span else ""


def _splice(text: str, start: int, end: int, replacement: str) -> str:
    return text[:start] + replacement + text[end:]


def _edit(text: str, span, replacement: str) -> str:
    """One textual edit — the whole of what a mutant is."""
    return _splice(text, span[0], span[1], replacement)


def _label(path: str, kind: str, before: str, after: str, offset: int) -> str:
    """A mutant's name: stable across runs, so a survivor list is comparable."""
    return f"{path}@{offset}:{kind}:{before}->{after}"


def _docstring_spans(tree, text: str) -> list:
    """Spans a mutation must not reach: every string literal in the source."""
    spans = [(m.start(), m.end()) for m in _STRING_LITERAL.finditer(text)]
    offsets = _offsets(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            span = _node_span(node, offsets)
            if span:
                spans.append(span)
    return sorted(set(spans))


def _named(tree) -> list:
    """Every name this module defines, in source order."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            out.append(node.name)
    return out


def _structural_mutants(text: str, path: str) -> list:
    """Operator mutants located through the AST, so a string is never touched.

    An operator's span is read between its operands, which is why this walks
    the tree rather than the token stream: `a - b` inside a message is a
    message, and mutating it would measure nothing.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    offsets = _offsets(text)
    out = []
    for node in ast.walk(tree):
        pairs = []
        if isinstance(node, ast.Compare) and len(node.ops) == 1 \
                and len(node.comparators) == 1:
            pairs.append((node.ops[0], node.left, node.comparators[0]))
        elif isinstance(node, ast.BinOp):
            pairs.append((node.op, node.left, node.right))
        for op, left, right in pairs:
            symbol = _AST_OPS.get(type(op))
            if symbol is None:
                continue
            left_span = _node_span(left, offsets)
            right_span = _node_span(right, offsets)
            if not left_span or not right_span:
                continue
            region = text[left_span[1]:right_span[0]]
            where = region.find(symbol)
            if where < 0:
                continue
            start = left_span[1] + where
            span = (start, start + len(symbol))
            for alternative in _OP_ALTS.get(symbol, ()):
                out.append({
                    "path": path, "span": span, "offset": start,
                    "kind": _OP_KIND.get(symbol, "operator"),
                    "before": symbol, "after": alternative,
                    "label": _label(path, _OP_KIND.get(symbol, "operator"),
                                    symbol, alternative, start),
                })
    return out


def _token_mutants(text: str, path: str) -> list:
    """Bare-word mutants, skipping every string literal."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    blocked = _docstring_spans(tree, text)

    def inside(position: int) -> bool:
        return any(start <= position < end for start, end in blocked)

    out = []
    for word, alternatives in _WORD_ALTS.items():
        for match in re.finditer(rf"\b{re.escape(word)}\b", text):
            if inside(match.start()):
                continue
            for alternative in alternatives:
                out.append({
                    "path": path, "span": (match.start(), match.end()),
                    "offset": match.start(), "kind": "word",
                    "before": word, "after": alternative,
                    "label": _label(path, "word", word, alternative,
                                    match.start()),
                })
    return out


def _mutant_order(candidates: list) -> list:
    """The canonical base order: by file, then offset, then label."""
    return sorted(candidates,
                  key=lambda c: (c["path"], c["offset"], c["label"]))


def _mutants(sources: dict) -> list:
    """Every candidate mutant of a claim's generated Python sources."""
    out = []
    for path in sorted(sources):
        text = sources[path]
        out.extend(_structural_mutants(text, path))
        out.extend(_token_mutants(text, path))
    return _mutant_order(out)


def _draw_order(root: str, count: int) -> list:
    """A deterministic permutation drawn from the claim's own root.

    Drawn from the ROOT so the sample is a function of the claim: the same
    claim measured twice reports the same survivors, and two different claims
    over the same code are sampled differently.
    """
    order = list(range(count))
    try:
        state = int((root or "0")[:16], 16) or 1
    except ValueError:
        state = 1
    for index in range(count - 1, 0, -1):
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        pick = state % (index + 1)
        order[index], order[pick] = order[pick], order[index]
    return order


def mutation_score(claimdir: str, max_mutants: int = None) -> dict:
    """How much of the equivalence class the criteria actually pin down.

    Mutants of the generated code are drawn deterministically from the root
    and re-audited; a mutant the gates still accept is a SURVIVOR, and the
    kill rate is the measure.  The score is residue, so measuring never
    touches the root.
    """
    parsed = _recipe.load_recipe(claimdir)
    checked = _seal.verify(claimdir)
    sources = {}
    for name in _recipe.generated_outputs(parsed):
        if not name.endswith(".py"):
            continue
        path = os.path.join(claimdir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                sources[name] = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
    candidates = _mutants(sources)
    ceiling = int(max_mutants or MUTANT_CEILING)
    order = _draw_order(checked["recomputed"], len(candidates))
    drawn = [candidates[i] for i in order[:min(ceiling, len(candidates))]]
    drawn = _mutant_order(drawn)

    survivors, killed = [], 0
    scratch = tempfile.mkdtemp(prefix="reticuli-mutants-")
    try:
        for mutant in drawn:
            text = sources[mutant["path"]]
            mutated = _edit(text, mutant["span"], mutant["after"])
            if mutated == text:
                continue
            where = os.path.join(scratch, os.path.basename(mutant["path"]))
            with open(where, "w", encoding="utf-8") as handle:
                handle.write(mutated)
            try:
                verdict = _build.audit(
                    claimdir, produce_from={mutant["path"]: where})
                alive = bool(verdict.get("ok"))
            except ClaimError:
                alive = False
            if alive:
                survivors.append(mutant["label"])
            else:
                killed += 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    total = len(drawn)
    rate = (killed / total) if total else 0.0
    floor = parsed.get("claim", {}).get("mutation_floor")
    result = {"mutants": total, "killed": killed, "rate": rate,
              "survivors": survivors, "root": checked["recomputed"],
              "floor": floor, "when": _now(),
              "ok": True if floor is None else rate >= floor}
    _write_json(os.path.join(claimdir, MUTATION_RESIDUE), result)
    return result


# -- the three machines -----------------------------------------------------


def _machine(leg: str) -> dict:
    """Normalize one leg — a claim directory or a frozen record — to facts.

    A record is a frozen INPUT to the existing comparison, not a second
    definition of it, so both transports reduce to the same handful of
    fields here and everything downstream is transport-blind.
    """
    if os.path.isdir(leg):
        parsed = _recipe.load_recipe(leg)
        checked = _seal.verify(leg)
        return {
            "kind": "directory", "path": leg, "name": checked["name"],
            "root": checked["recomputed"],
            "build_digest": _identity.build_digest(leg),
            "cost": _run_mod.cost(leg),
            "declared": dict(parsed.get("claim") or {}),
            "record_version": None, "gates": None, "verifies": checked["ok"],
        }
    doc = _attest.record_read(leg)
    return {
        "kind": "record", "path": leg, "name": doc["name"],
        "root": doc["root"], "build_digest": doc["build_digest"],
        "cost": doc.get("cost"),
        "declared": dict(doc["claim"]) if doc["record"] >= 2 else None,
        "record_version": doc["record"], "gates": doc["gates"],
        "verifies": True,
    }


def _audited(machine: dict) -> bool:
    """Were this leg's verdicts EARNED on the bytes it holds?"""
    if machine["kind"] == "directory":
        try:
            return bool(_build.audit(machine["path"])["ok"])
        except ClaimError:
            return False
    gates = machine.get("gates") or []
    return bool(gates) and all(g.get("status") == "ok" for g in gates)


def crosscheck(m1: str, m2: str, m3: str, tolerance: float = None,
               mutants: int = None, **_ignored) -> dict:
    """The three-machine test, over directories, records, or a mix of both."""
    legs = (m1, m2, m3)
    resolved = [os.path.realpath(leg) for leg in legs]
    if len(set(resolved)) < 3:
        raise ClaimError(
            "the three machines must be three: one claim presented thrice "
            "agrees with itself and proves nothing")
    machines = {label: _machine(leg)
                for label, leg in zip(("M1", "M2", "M3"), legs)}
    one, two, three = machines["M1"], machines["M2"], machines["M3"]

    roots = {label: m["root"] for label, m in machines.items()}
    equivalence = len(set(roots.values())) == 1
    reuse = bool(one["build_digest"] == two["build_digest"])
    audited = {label: _audited(m) for label, m in machines.items()}

    declared = one["declared"]
    declared_tolerance = None
    ceilings, floor = {}, None
    if declared is not None:
        declared_tolerance = declared.get("tolerance")
        ceilings = dict(declared.get("envelope") or {})
        floor = declared.get("mutation_floor")

    # -- the cost band: exactly ONE unit decides, the strongest both
    # machines measured.  A weaker shared unit must never veto a comparison
    # a stronger one can make (wall-clock measures the host's load as much
    # as the work), and the strongest must be DECISIVE, so agreement on a
    # weaker one cannot rescue it.
    c1 = {k: v for k, v in (one["cost"] or {}).items() if k in COST_LADDER}
    c3 = {k: v for k, v in (three["cost"] or {}).items() if k in COST_LADDER}
    unit = next((u for u in COST_LADDER
                 if _finite(c1.get(u)) and _finite(c3.get(u))), None)

    band = float(declared_tolerance) if declared_tolerance is not None \
        else float(os.environ.get(_ENV_TOLERANCE) or TOLERANCE)
    tightened = False
    if tolerance is not None:
        if declared_tolerance is None:
            band = float(tolerance)
        elif float(tolerance) < float(declared_tolerance):
            # A verifier may TIGHTEN a declared band, never loosen it: the
            # declared value is recipe text, inside the root, and a caller
            # who could widen it would be loosening the claim's condition on
            # the claim's behalf with the root unmoved.
            band, tightened = float(tolerance), True
    comparable = None
    ratio = None
    if unit is not None:
        ratio = (c3[unit] / c1[unit]) if c1[unit] else None
        comparable = _run_mod._in_band(c3[unit], c1[unit], band)

    envelope = {}
    for key, ceiling in ceilings.items():
        paid = c3.get(key)
        envelope[key] = {
            "ceiling": ceiling, "paid": paid if _finite(paid) else None,
            "within": (paid <= ceiling) if _finite(paid) else None,
        }

    score = None
    if floor is not None and mutants:
        target = three if three["kind"] == "directory" else one
        if target["kind"] == "directory":
            score = mutation_score(target["path"], max_mutants=mutants)
            score = dict(score, ok=score["rate"] >= floor)

    rejected, incomplete = [], []
    if not equivalence:
        rejected.append("one root across all three")
    if not reuse:
        rejected.append("byte reuse between M1 and M2")
    for label in ("M1", "M2", "M3"):
        if not audited[label]:
            rejected.append(f"verdicts re-earned on {label}")
    if declared is None:
        incomplete.append(
            "the declared conditions: a version-1 record cannot say what the "
            "claim declared, and unknown is not 'none declared'")
    else:
        if declared_tolerance is not None:
            if comparable is None:
                incomplete.append(
                    "the declared tolerance could not be measured: M1 and M3 "
                    "share no cost unit")
            elif comparable is False:
                rejected.append("cost band")
        for key, row in sorted(envelope.items()):
            if row["within"] is False:
                rejected.append(f"envelope {key}")
            elif row["within"] is None:
                incomplete.append(
                    f"the declared envelope ceiling on {key} was not measured")
        if floor is not None:
            if score is None:
                incomplete.append(
                    "the declared mutation_floor was not measured: no "
                    "mutation run was asked for")
            elif not score["ok"]:
                rejected.append("mutation floor")

    verdict = "reject" if rejected else ("incomplete" if incomplete
                                         else "accept")
    discovery = (three["cost"] or {}).get("discovery") \
        or (one["cost"] or {}).get("discovery")
    return {
        "satisfied": verdict == "accept",
        "verdict": verdict,
        "rejected": rejected,
        "incomplete": incomplete,
        "roots": roots,
        "equivalence": equivalence,
        "reuse": reuse,
        "audited": audited,
        "transports": {label: m["kind"] for label, m in machines.items()},
        "name": one["name"],
        "cost": {
            "comparable": comparable, "unit": unit, "ratio": ratio,
            "tolerance": band, "declared_tolerance": declared_tolerance,
            "tightened": tightened, "envelope": envelope,
            "m1": c1 or None, "m3": c3 or None, "discovery": discovery,
        },
        "mutation_score": score,
        "independence": _run_mod._independence_line(
            _run_mod.independence(three["path"])
            if three["kind"] == "directory" else
            {"vendor": None, "model": None, "blind": False}),
    }


def record_proof(m1: str, m2: str, m3: str, **kwargs) -> dict:
    """Run the crosscheck and, on a pass, seal the proof onto M1 as residue.

    A proof is residue on M1's manifest, so M1 must be a DIRECTORY.  The
    boundary is the transport: directory legs are the caller's own
    executions and need no anchor, while record legs are relayed statements
    whose only provenance is a signature — so a durable proof refuses a
    record the verifier's anchor does not verify, then embeds each record's
    digest and signer identity, and a reader can walk from the verdict to
    the statements beneath it.
    """
    if not os.path.isdir(m1):
        raise ClaimError(
            "a recorded proof lands on M1's manifest, so M1 must be a claim "
            "directory, not a frozen record")
    trail = []
    for leg in (m2, m3):
        if os.path.isdir(leg):
            continue
        doc = _attest.record_read(leg)
        signer = _attest.record_signer(leg)
        if not signer:
            raise ClaimError(
                f"{leg}: a durable proof refuses a record whose signature "
                f"this verifier's anchor does not verify — a record from a "
                f"key you have not anchored is a document, not evidence")
        trail.append({"signer": signer, "digest": _attest.record_digest(doc),
                      "path": os.path.basename(leg)})
    result = crosscheck(m1, m2, m3, **kwargs)
    if not result["satisfied"]:
        return dict(result, proof_recorded=False)
    proof = {"kind": "crosscheck", "when": _now(),
             "m2": result["roots"]["M2"], "m3": result["roots"]["M3"],
             "verdict": result["verdict"],
             "transports": result["transports"]}
    if trail:
        proof["records"] = trail
    _seal.seal(m1, proof=proof)
    return dict(result, proof_recorded=True, proof=proof)
