"""Kernel crosscheck: the three-machine test, vacuity, and mutation.

Valid means one root across all three legs, every verdict re-earned, byte
reuse where reuse is claimed, and every condition the claim ITSELF declared.
The verdict is three-valued: a declared condition this run could not measure
is neither true nor false, so the answer is `incomplete`, which can never
accept.
"""
import ast
import json
import os
import random
import re
import shutil
import tempfile

from . import identity as _identity
from . import recipe as _recipe
from . import run as _run
from .attest import record_digest, record_read, record_signer
from .build import audit
from .core import (COST_LADDER, ClaimError, MUTANT_CEILING, MUTATION_RESIDUE,
                   TOLERANCE, _ENV_TOLERANCE, _canonical, _is_number, _now,
                   _safe, _sha256_hex, _write_json)
from .seal import read_manifest, seal, verify

#: Shell operators that separate one simple command from the next.
_OPERATORS = frozenset({"&&", "||", ";", "|", "&", "\n"})

#: Programs that run a file given to them: their first non-flag argument is
#: the thing that actually decides.
_INTERPRETERS = frozenset({
    "python", "python3", "python2", "py", "pytest", "py.test", "node", "deno",
    "ruby", "perl", "php", "lua", "Rscript", "awk", "tclsh", "sh", "bash",
    "dash", "zsh"})

#: Flags that swallow the next word, so it is not the decider.
_SKIP_VALUE = frozenset({"-m", "-c", "-e", "-p", "-X", "--module"})

#: Mutation vocabulary. Operators are mutated to alternatives of the same
#: arity, so a mutant stays syntactically valid and only its meaning moves.
_COMPARISON = (">", "<", ">=", "<=", "==", "!=")
_ARITHMETIC = ("+", "-", "*", "/", "//", "%", "**")
_OP_ALTS = {
    ">": ("<", ">=", "=="), "<": (">", "<=", "=="),
    ">=": ("<=", ">", "=="), "<=": (">=", "<", "=="),
    "==": ("!=", "<", ">"), "!=": ("==", "<", ">"),
    "+": ("-", "*"), "-": ("+", "*"), "*": ("+", "-"),
    "/": ("*", "//"), "//": ("/", "*"), "%": ("//", "*"),
    "**": ("*", "+"),
}
_OP_KIND = dict([(op, "comparison") for op in _COMPARISON]
                + [(op, "arithmetic") for op in _ARITHMETIC])
_WORD_ALTS = {"and": ("or",), "or": ("and",), "True": ("False",),
              "False": ("True",), "in": ("not in",), "is": ("is not",),
              "not in": ("in",), "is not": ("is",)}
_STRING_LITERAL = re.compile(r"""("""
                             r'"""(?:.|\n)*?"""'
                             r"|'''(?:.|\n)*?'''"
                             r'|"(?:[^"\\\n]|\\.)*"'
                             r"|'(?:[^'\\\n]|\\.)*'"
                             r")""")


# --------------------------------------------------------------------------
# which files decide a gate

def _named(command: str) -> list:
    """The simple commands inside one shell line."""
    pieces, current = [], []
    tokens = re.split(r"(\s+|&&|\|\||;|\||&|\n)", command or "")
    for token in tokens:
        if token in _OPERATORS:
            pieces.append(current)
            current = []
        elif token.strip():
            current.append(token.strip())
    pieces.append(current)
    return [p for p in pieces if p]


def gate_deciders(command: str) -> list:
    """Which workspace files decide this gate.

    Only an interpreter invocation or an explicit path counts: a gate that
    executes no workspace script decides by the recipe alone.
    """
    found = []
    for argv in _named(command):
        head = argv[0]
        base = os.path.basename(head)
        if base in _INTERPRETERS:
            skip = False
            for word in argv[1:]:
                if skip:
                    skip = False
                    continue
                if word in _SKIP_VALUE:
                    skip = True
                    continue
                if word.startswith("-"):
                    continue
                if word not in found:
                    found.append(word)
                break
        elif head.startswith("./") or head.startswith("../"):
            name = head[2:] if head.startswith("./") else head
            if name not in found:
                found.append(name)
    return found


def _reached(claim: str, start: str, seen: set) -> set:
    """One level of ordinary Python import, followed from a decider."""
    path = os.path.join(claim, start)
    if not os.path.isfile(path) or not start.endswith(".py"):
        return seen
    try:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError, UnicodeDecodeError):
        return seen
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".")[0]]
        for name in names:
            candidate = name + ".py"
            if candidate in seen:
                continue
            if os.path.isfile(os.path.join(claim, candidate)):
                seen.add(candidate)
    return seen


def vacuous_gates(parsed: dict) -> list:
    """Gates whose every decider is generated: the verdict depends on no claim."""
    generated = set(_recipe.generated_outputs(parsed))
    vacuous = []
    for gate in _recipe.gates(parsed):
        deciders = gate_deciders(gate.get("run") or "")
        if not deciders:
            continue
        if all(d in generated for d in deciders):
            vacuous.append(gate.get("output"))
    return vacuous


# --------------------------------------------------------------------------
# mutation: the equivalence class has a width, and it is measurable

def _docstring_spans(tree, text: str) -> list:
    """Byte spans of every docstring: prose is not behavior."""
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        if body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            spans.append(_node_span(body[0], text))
    return spans


def _node_span(node, text: str) -> tuple:
    lines = text.splitlines(keepends=True)
    offsets, total = [], 0
    for line in lines:
        offsets.append(total)
        total += len(line)
    offsets.append(total)
    start = offsets[node.lineno - 1] + node.col_offset
    end_line = getattr(node, "end_lineno", node.lineno)
    end_col = getattr(node, "end_col_offset", node.col_offset)
    end = offsets[end_line - 1] + end_col
    return (start, end)


def _span_text(text: str, span: tuple) -> str:
    return text[span[0]:span[1]]


def _splice(text: str, span: tuple, replacement: str) -> str:
    return text[:span[0]] + replacement + text[span[1]:]


def _label(path: str, span: tuple, was: str, now: str) -> str:
    return f"{path}:{span[0]}:{was}->{now}"


def _edit(text: str, span: tuple, replacement: str) -> str:
    return _splice(text, span, replacement)


def _protected(index: int, spans: list) -> bool:
    return any(start <= index < end for start, end in spans)


def _token_mutants(path: str, text: str) -> list:
    """Operator and keyword mutants, outside strings and docstrings."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    forbidden = _docstring_spans(tree, text)
    for match in _STRING_LITERAL.finditer(text):
        forbidden.append(match.span())
    candidates = []
    pattern = re.compile(
        r"(?<![\w.])(is not|not in|and|or|is|in|True|False)(?![\w])"
        r"|(\*\*|//|<=|>=|==|!=|[<>+\-*/%])")
    for match in pattern.finditer(text):
        token = match.group(0)
        if _protected(match.start(), forbidden):
            continue
        for alternative in _WORD_ALTS.get(token, _OP_ALTS.get(token, ())):
            candidates.append((path, match.span(), token, alternative))
    return candidates


def _structural_mutants(path: str, text: str) -> list:
    """Return-value and constant mutants drawn from the parse tree."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    forbidden = _docstring_spans(tree, text)
    candidates = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(
                node.value, (int, float)) and not isinstance(node.value, bool):
            span = _node_span(node, text)
            if _protected(span[0], forbidden):
                continue
            was = _span_text(text, span)
            candidates.append((path, span, was, str(node.value + 1)))
    return candidates


def _mutants(claim: str, parsed: dict) -> list:
    """Every candidate mutant of this claim's generated Python, in a stable
    order -- the order is lexicographic by (path, offset, token), so it does
    not depend on how the filesystem or the parser happened to enumerate."""
    candidates = []
    for output in _recipe.generated_outputs(parsed):
        if not output.endswith(".py"):
            continue
        path = _safe(claim, output)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        candidates.extend(_token_mutants(output, text))
        candidates.extend(_structural_mutants(output, text))
    return _mutant_order(candidates)


def _mutant_order(candidates: list) -> list:
    return sorted(candidates, key=lambda c: (c[0], c[1][0], c[1][1], c[2],
                                             c[3]))


def _draw_order(population: int, seed: str, take: int) -> list:
    """A deterministic sample drawn from the ROOT: the same claim always
    draws the same mutants, on every host and every interpreter."""
    picker = random.Random(seed)
    order = list(range(population))
    picker.shuffle(order)
    return order[:take]


def mutation_score(claim: str, max_mutants: int = MUTANT_CEILING,
                   strict: bool = True) -> dict:
    """Deterministic mutants of the generated code, re-audited; the kill rate."""
    parsed = _recipe.load_recipe(claim)
    checked = verify(claim)
    candidates = _mutants(claim, parsed)
    take = min(int(max_mutants), len(candidates))
    chosen = [candidates[i] for i in
              _draw_order(len(candidates), checked["recomputed"], take)]
    survivors, killed = [], 0
    for output, span, was, now in chosen:
        work = tempfile.mkdtemp(prefix="reticuli-mutant-")
        try:
            copy = os.path.join(work, "claim")
            shutil.copytree(claim, copy, symlinks=False,
                            ignore=shutil.ignore_patterns("__pycache__"))
            path = _safe(copy, output)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(_edit(text, span, now))
            try:
                outcome = audit(copy, strict=strict)
                alive = bool(outcome["ok"])
            except ClaimError:
                alive = False
            if alive:
                survivors.append(_label(output, span, was, now))
            else:
                killed += 1
        finally:
            shutil.rmtree(work, ignore_errors=True)
    total = len(chosen)
    residue = {"mutants": total, "killed": killed,
               "rate": (killed / total) if total else 0.0,
               "survivors": survivors, "root": checked["recomputed"],
               "candidates": len(candidates)}
    try:
        _write_json(os.path.join(claim, MUTATION_RESIDUE), residue)
    except OSError:
        pass
    return residue


# --------------------------------------------------------------------------
# the signature chain

def sign_node(root: str, digest: str, links) -> str:
    """One node of the bottom-anchored signature chain.

    The fold binds the SET of signatures below, so enumeration order is not
    identity.
    """
    payload = {"root": root, "build_digest": digest,
               "links": sorted(str(x) for x in (links or []))}
    return _sha256_hex(_canonical(payload))


# --------------------------------------------------------------------------
# a machine: a claim directory, or a frozen record

def _machine(leg: str, name: str) -> dict:
    """Normalize one leg. A record is an input to the comparison, never a
    second definition of it."""
    if os.path.isdir(leg):
        parsed = _recipe.load_recipe(leg)
        checked = verify(leg)
        outcome = audit(leg)
        declared = {k: v for k, v in (parsed.get("claim") or {}).items()
                    if k in ("tolerance", "envelope", "mutation_floor")}
        return {"name": name, "kind": "directory", "path": leg,
                "root": checked["recomputed"] if checked["ok"]
                        else checked["recomputed"],
                "sealed_root": checked["root"],
                "build_digest": _identity.build_digest(leg),
                "audited": bool(outcome["ok"]), "audit": outcome,
                "cost": _run.cost(leg), "discovery": _run.discovery(leg),
                "declared": declared, "declared_known": True,
                "independence": _run.independence(leg)}
    if os.path.isfile(leg):
        document = record_read(leg)
        gates = document.get("gates") or []
        return {"name": name, "kind": "record", "path": leg,
                "root": document["root"], "sealed_root": document["root"],
                "build_digest": document["build_digest"],
                "audited": bool(gates) and all(
                    g["status"] == "ok" for g in gates),
                "audit": None,
                "cost": document.get("cost") or None, "discovery": None,
                "declared": document.get("claim") or {},
                "declared_known": document.get("record", 1) >= 2,
                "independence": document.get("producer") or {},
                "document": document}
    raise ClaimError(f"{name} is neither a claim directory nor a record: {leg}")


def _shared_unit(left: dict | None, right: dict | None):
    if not left or not right:
        return None
    for unit in COST_LADDER:
        if _is_number(left.get(unit)) and _is_number(right.get(unit)):
            return unit
    return None


def crosscheck(m1: str, m2: str, m3: str, tolerance=None, mutants=None,
               strict: bool = True) -> dict:
    """The three-machine test. One predicate, two transports."""
    legs = [m1, m2, m3]
    real = []
    for leg in legs:
        real.append(os.path.realpath(leg))
    if len(set(real)) != 3:
        raise ClaimError(
            "the three machines must be distinct: one claim presented three "
            "times agrees with itself and proves nothing")
    machines = {"M1": _machine(m1, "M1"), "M2": _machine(m2, "M2"),
                "M3": _machine(m3, "M3")}

    roots = {name: machine["root"] for name, machine in machines.items()}
    equivalence = len(set(roots.values())) == 1
    reuse = machines["M1"]["build_digest"] == machines["M2"]["build_digest"]
    audited = {name: machine["audited"] for name, machine in machines.items()}

    declared = machines["M1"]["declared"] or {}
    declared_known = machines["M1"]["declared_known"]

    caller = tolerance
    if caller is None and os.environ.get(_ENV_TOLERANCE):
        try:
            caller = float(os.environ[_ENV_TOLERANCE])
        except ValueError:
            caller = None
    declared_tol = declared.get("tolerance")
    if declared_tol is not None and caller is not None:
        band = min(float(declared_tol), float(caller))
    elif declared_tol is not None:
        band = float(declared_tol)
    elif caller is not None:
        band = float(caller)
    else:
        band = float(TOLERANCE)

    unit = _shared_unit(machines["M1"]["cost"], machines["M3"]["cost"])
    if unit is None:
        comparable, ratio = None, None
    else:
        c1 = machines["M1"]["cost"][unit]
        c3 = machines["M3"]["cost"][unit]
        ratio = (float(c3) / float(c1)) if c1 else None
        comparable = _run._in_band(c3, c1, band)

    cost = {"comparable": comparable, "unit": unit, "ratio": ratio,
            "tolerance": band, "declared_tolerance": declared_tol,
            "tightened": declared_tol is not None and caller is not None
                         and float(caller) < float(declared_tol),
            "m1": machines["M1"]["cost"], "m3": machines["M3"]["cost"],
            "discovery": machines["M1"]["discovery"], "envelope": {}}

    rejected, incomplete = [], []
    if not equivalence:
        rejected.append("one root across all three")
    if not reuse:
        rejected.append("byte reuse between M1 and M2")
    for name, ok in audited.items():
        if not ok:
            rejected.append(f"{name} did not re-earn its verdicts")

    if not declared_known:
        incomplete.append(
            "the declared conditions are unknown: a version-1 record cannot "
            "say what the claim declared")

    if declared_tol is not None:
        if comparable is None:
            incomplete.append(
                "the declared tolerance could not be measured: the two "
                "ledgers share no cost unit")
        elif comparable is False:
            rejected.append("cost band")

    envelope = declared.get("envelope") or {}
    for ceiling_unit, ceiling in envelope.items():
        measured = (machines["M3"]["cost"] or {}).get(ceiling_unit)
        if not _is_number(measured):
            cost["envelope"][ceiling_unit] = {"ceiling": ceiling,
                                              "measured": None,
                                              "within": None}
            incomplete.append(f"envelope {ceiling_unit} was not measured")
            continue
        within = float(measured) <= float(ceiling)
        cost["envelope"][ceiling_unit] = {"ceiling": ceiling,
                                          "measured": measured,
                                          "within": within}
        if not within:
            rejected.append(f"envelope {ceiling_unit}")

    score = None
    floor = declared.get("mutation_floor")
    if floor is not None:
        if mutants and machines["M3"]["kind"] == "directory":
            score = mutation_score(machines["M3"]["path"],
                                   max_mutants=mutants, strict=strict)
            score["floor"] = float(floor)
            score["ok"] = score["rate"] >= float(floor)
            if not score["ok"]:
                rejected.append("mutation floor")
        else:
            incomplete.append(
                "the declared mutation floor was not measured: no mutation "
                "run on this crosscheck")

    if rejected:
        verdict = "reject"
    elif incomplete:
        verdict = "incomplete"
    else:
        verdict = "accept"

    return {"satisfied": verdict == "accept", "verdict": verdict,
            "rejected": rejected, "incomplete": incomplete,
            "roots": roots, "equivalence": equivalence, "reuse": reuse,
            "audited": audited, "cost": cost, "mutation_score": score,
            "independence": _run._independence_line(
                machines["M3"]["independence"]),
            "transports": {name: machine["kind"]
                           for name, machine in machines.items()}}


def record_proof(m1: str, m2: str, m3: str, tolerance=None, mutants=None,
                 signers: str | None = None) -> dict:
    """Run the crosscheck and, on a pass, seal the proof onto M1 as residue."""
    if not os.path.isdir(m1):
        raise ClaimError(
            "a recorded proof lands on M1's manifest, so M1 must be a claim "
            "directory, never a frozen record")
    from .build import _anchor
    anchor = _anchor(signers)
    trail = []
    for leg in (m2, m3):
        if os.path.isdir(leg):
            continue
        document = record_read(leg)
        signer = record_signer(leg, anchor)
        if not signer:
            raise ClaimError(
                f"a durable proof refuses a record whose signature this "
                f"verifier's anchor does not verify: {leg}")
        trail.append({"leg": os.path.basename(leg), "signer": signer,
                      "digest": record_digest(document)})
    outcome = crosscheck(m1, m2, m3, tolerance=tolerance, mutants=mutants)
    if not outcome["satisfied"]:
        return {"proof_recorded": False, "crosscheck": outcome}
    proof = {"kind": "crosscheck", "when": _now(),
             "m2": outcome["roots"]["M2"], "m3": outcome["roots"]["M3"],
             "verdict": outcome["verdict"], "records": trail}
    seal(m1, proof=proof)
    return {"proof_recorded": True, "crosscheck": outcome, "proof": proof}
