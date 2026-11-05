"""The three-machine test, the claim boundary, and the mutation score.

M1 verifies in place, M2 arrives by transfer and verifies from the received
bytes alone, M3 is an independent rebuild from the pinned inputs. Valid means
one root across all three, every verdict re-earned, and every condition the
claim DECLARED holding.

The verdict is three-valued. A HARD condition must be true to accept and
rejects on false; a hard condition the claim declared but this run did not
measure is neither, and the verdict is `incomplete`, which can never accept,
because unknown evidence is not evidence. An OBSERVATION never decides:
producer independence is recorded (content cannot prove blindness), and a
cost band nobody could measure is reported unmeasured.
"""
import ast
import hashlib
import json
import os
import re
import shutil
import tempfile

from . import attest as _attest
from . import build as _build
from . import identity as _identity
from . import recipe as _recipe
from . import run as _run_layer
from . import seal as _seal
from .core import (COST_LADDER, MUTANT_CEILING, MUTANT_FLOOR,
                   MUTANT_HEADROOM, MUTATION_RESIDUE, TOLERANCE, ClaimError,
                   _ENV_SIGNERS, _ENV_TOLERANCE, _finite, _now, _write_json)

# -- the gate's read set ---------------------------------------------------
#: shell constructs that separate one simple command from the next
_OPERATORS = frozenset({"&&", "||", ";", "|", "&", "\n"})
#: a leading word that runs the NEXT word rather than deciding anything
_INTERPRETERS = frozenset({
    "sh", "bash", "dash", "zsh", "python", "python3", "python2", "py",
    "pytest", "py.test", "node", "deno", "ruby", "perl", "php", "lua",
    "awk", "tclsh", "Rscript"})
#: options that consume the following word, so it is not a decider either
_SKIP_VALUE = frozenset({"-m", "-c", "-e", "-p", "-X", "--module"})
_REDIRECTS = frozenset({">", ">>", "<", "2>", "2>>", "&>"})


def _split_commands(command: str) -> list:
    """One shell string into its simple commands, lexically."""
    pieces, current = [], []
    tokens = re.split(r"(\s+|&&|\|\||;|\||&|\n)", command or "")
    for token in tokens:
        if token in _OPERATORS:
            pieces.append(" ".join(current))
            current = []
        elif token.strip():
            current.append(token)
    pieces.append(" ".join(current))
    return [p for p in pieces if p.strip()]


def gate_deciders(command: str) -> list:
    """Which files in the workspace decide this gate.

    A gate that executes no workspace script decides by the recipe alone
    (`grep -q hello g.txt` asserts something about a file but is not itself
    a decider that could be regrown), so such a command names nothing.
    """
    import shlex
    found = []
    for piece in _split_commands(command):
        try:
            words = shlex.split(piece)
        except ValueError:
            words = piece.split()
        clean, skip = [], False
        for word in words:
            if skip:
                skip = False
                continue
            if word in _REDIRECTS or any(word.startswith(r)
                                         for r in (">", "<")):
                skip = True
                continue
            clean.append(word)
        if not clean:
            continue
        head, rest = clean[0], clean[1:]
        base = os.path.basename(head)
        if base in _INTERPRETERS:
            skip = False
            for word in rest:
                if skip:
                    skip = False
                    continue
                if word in _SKIP_VALUE:
                    skip = True
                    continue
                if word.startswith("-"):
                    continue
                found.append(word)
                break
        elif head.startswith("./") or head.startswith("../") or "/" in head:
            found.append(head)
    deciders, seen = [], set()
    for name in found:
        name = name[2:] if name.startswith("./") else name
        if name and name not in seen:
            seen.add(name)
            deciders.append(name)
    return deciders


def vacuous_gates(parsed: dict) -> list:
    """Gates whose every decider is generated.

    Such a verdict depends on no claim at all, so the root would fit any
    implementation that prints ok. The kernel NAMES them; authoring refuses
    them.
    """
    table = (parsed or {}).get("claim") or {}
    declared = set(table.get("inputs") or [])
    if table.get("environment"):
        declared.add(table["environment"])
    if table.get("inputs_manifest"):
        declared.add(table["inputs_manifest"])
    generated = set(_recipe.generated_outputs(parsed))
    vacuous = []
    for gate in _recipe.gates(parsed):
        deciders = gate_deciders(gate.get("run") or "")
        if not deciders:
            continue
        def claimed(name):
            if name in declared:
                return True
            prefix = name.rstrip("/") + "/"
            return any(d == name or d.startswith(prefix) for d in declared)
        if all(d in generated and not claimed(d) for d in deciders):
            vacuous.append(gate["output"])
    return vacuous


# -- the signature chain ---------------------------------------------------
def sign_node(root: str, digest: str, links) -> str:
    """One node of the bottom-anchored signature chain.

    The fold binds the SET of signatures below, so enumeration order is not
    identity; the root and the build digest both bind, so a regenerated
    implementation moves the node even though the claim holds.
    """
    payload = {"root": root, "build_digest": digest,
               "links": sorted(links or [])}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# -- mutation: the equivalence class has a width ---------------------------
_STRING_LITERAL = re.compile(
    r"""(?P<q>'''|\"\"\"|'|")(?:\\.|(?!\1).)*?(?P=q)""", re.DOTALL)
_COMPARISON = (">", "<", ">=", "<=", "==", "!=")
_ARITHMETIC = ("+", "-", "*", "//", "/", "%")
#: what each operator may become. A mutant must stay SYNTACTICALLY VALID, or
#: a loose check kills it by failing to import and the score measures syntax
#: rather than the criteria.
_OP_ALTS = {
    ">": ("<", ">=", "<=", "=="),
    "<": (">", "<=", ">=", "=="),
    ">=": ("<=", ">", "<", "=="),
    "<=": (">=", "<", ">", "=="),
    "==": ("!=",),
    "!=": ("==",),
    "+": ("-", "*"),
    "-": ("+", "*"),
    "*": ("+", "-"),
    "//": ("*", "+"),
    "/": ("*", "+"),
    "%": ("*", "+"),
}
_OP_KIND = dict([(op, "comparison") for op in _COMPARISON]
                + [(op, "arithmetic") for op in _ARITHMETIC])
_WORD_ALTS = {
    "True": ("False",),
    "False": ("True",),
    "and": ("or",),
    "or": ("and",),
    "is": ("is not",),
    "in": ("not in",),
    "not ": ("",),
}


def _docstring_spans(source: str) -> list:
    """Where the prose is. A mutant that edits a docstring changes no
    behavior, so it would survive every honest check and dilute the score."""
    spans = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return spans
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        if body and isinstance(body[0], ast.Expr) and \
                isinstance(body[0].value, ast.Constant) and \
                isinstance(body[0].value.value, str):
            spans.append(_node_span(source, body[0]))
    return spans


def _node_span(source: str, node) -> tuple:
    """A node's (start, end) byte offsets in the source text."""
    lines = source.splitlines(keepends=True)
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line)
    try:
        begin = starts[node.lineno - 1] + node.col_offset
        end = starts[node.end_lineno - 1] + node.end_col_offset
    except (AttributeError, IndexError, TypeError):
        return (0, 0)
    return (begin, end)


def _span_text(source: str, span: tuple) -> str:
    return source[span[0]:span[1]]


def _splice(source: str, span: tuple, replacement: str) -> str:
    return source[:span[0]] + replacement + source[span[1]:]


def _label(path: str, span: tuple, what: str) -> str:
    return f"{path}:{span[0]}:{what}"


def _named(spans: list, offset: int) -> bool:
    return any(start <= offset < end for start, end in spans)


def _edit(source: str, mutant: dict) -> str:
    """Apply one mutant to a source text."""
    return _splice(source, mutant["span"], mutant["replacement"])


def _token_mutants(source: str, path: str) -> list:
    """Operator and word swaps, outside prose and string literals."""
    skip = list(_docstring_spans(source))
    skip += [(m.start(), m.end()) for m in _STRING_LITERAL.finditer(source)]
    out = []
    for word, alternatives in _WORD_ALTS.items():
        for match in re.finditer(
                r"(?<![A-Za-z0-9_])" + re.escape(word.strip()) +
                r"(?![A-Za-z0-9_])", source):
            if _named(skip, match.start()):
                continue
            for alternative in alternatives:
                out.append({"path": path,
                            "span": (match.start(), match.end()),
                            "replacement": alternative.strip(),
                            "what": f"word {word.strip()}->"
                                    f"{alternative.strip() or 'nothing'}"})
    pattern = re.compile("|".join(
        re.escape(op) for op in sorted(_OP_ALTS, key=len, reverse=True)))
    for match in pattern.finditer(source):
        if _named(skip, match.start()):
            continue
        op = match.group(0)
        left = source[match.start() - 1:match.start()]
        right = source[match.end():match.end() + 1]
        if left in "=<>!+-*/%" or right in "=":
            continue                       # part of a longer operator
        for alternative in _OP_ALTS[op]:
            out.append({"path": path,
                        "span": (match.start(), match.end()),
                        "replacement": alternative,
                        "what": f"{_OP_KIND.get(op, 'token')} "
                                f"{op}->{alternative}"})
    return out


def _structural_mutants(source: str, path: str) -> list:
    """AST-shaped edits: invert a branch, blank a returned value.

    Every candidate is compiled before it is drawn, so a mutant that would
    not parse never enters the sample -- a syntax error is killed by any
    check that imports at all, and would measure the language rather than
    the criteria.
    """
    out = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            span = _node_span(source, node.test)
            text = _span_text(source, span)
            if text:
                out.append({"path": path, "span": span,
                            "replacement": f"not ({text})",
                            "what": "branch inverted"})
        elif isinstance(node, ast.Return) and node.value is not None:
            span = _node_span(source, node.value)
            if _span_text(source, span):
                out.append({"path": path, "span": span,
                            "replacement": "None",
                            "what": "return value blanked"})
    return out


def _mutant_order(mutant: dict) -> tuple:
    return (mutant["path"], mutant["span"][0], mutant["span"][1],
            mutant["what"], mutant["replacement"])


def _draw_order(candidates: list, seed: str) -> list:
    """A deterministic draw: the sample is a function of the ROOT, so two
    runs of the same claim measure the same mutants."""
    def key(mutant):
        token = f"{seed}:{_mutant_order(mutant)}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
    return sorted(sorted(candidates, key=_mutant_order), key=key)


def _mutants(claim: str, parsed: dict, seed: str) -> list:
    """Every candidate mutant of this claim's generated code, in draw order."""
    candidates = []
    for output in _recipe.generated_outputs(parsed):
        path = os.path.join(claim, output)
        if not os.path.isfile(path) or not output.endswith(".py"):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        for mutant in (_token_mutants(source, output)
                       + _structural_mutants(source, output)):
            mutated = _edit(source, mutant)
            if mutated == source:
                continue
            try:
                compile(mutated, output, "exec")
            except (SyntaxError, ValueError):
                continue
            candidates.append(dict(mutant, source=source, mutated=mutated))
    return _draw_order(candidates, seed)


def mutation_score(claim: str, max_mutants: int | None = None) -> dict:
    """How much the criteria actually hold down: the kill rate.

    Mutants of the GENERATED code, drawn deterministically from the root and
    re-audited. The sample and the rate are residue; the root never moves.
    """
    parsed = _recipe.load_recipe(claim)
    seed = _identity.root(parsed, claim)
    wanted = int(max_mutants) if max_mutants else \
        max(MUTANT_FLOOR, min(MUTANT_CEILING, MUTANT_FLOOR * MUTANT_HEADROOM))
    drawn = _mutants(claim, parsed, seed)[:wanted]
    killed, survivors = 0, []
    scratch = tempfile.mkdtemp(prefix="reticuli-mutants-")
    try:
        for index, mutant in enumerate(drawn):
            where = os.path.join(scratch, f"m{index}-"
                                 f"{os.path.basename(mutant['path'])}")
            with open(where, "w", encoding="utf-8") as handle:
                handle.write(mutant["mutated"])
            try:
                verdict = _build.audit(
                    claim, produce_from={mutant["path"]: where})
                alive = bool(verdict["ok"])
            except ClaimError:
                alive = False
            if alive:
                survivors.append(_label(mutant["path"], mutant["span"],
                                        mutant["what"]))
            else:
                killed += 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    total = len(drawn)
    score = {"mutants": total, "killed": killed, "survivors": survivors,
             "rate": (killed / total) if total else None, "seed": seed}
    try:
        _write_json(os.path.join(claim, MUTATION_RESIDUE), score)
    except OSError:
        pass
    return score


# -- the three machines ----------------------------------------------------
def _declared(table: dict | None) -> dict:
    table = table or {}
    return {k: table[k] for k in ("tolerance", "envelope", "mutation_floor")
            if k in table}


def _machine(leg: str, mutants: int | None = None) -> dict:
    """One machine's facts, however it stands in the test.

    A leg is a claim directory -- computed on the spot by running its gates
    -- or a RECORD, a signed statement of one machine's results. The two
    transports mix freely and must reach the same verdict: a record is a
    frozen input to the comparison, not a second definition of it.
    """
    if os.path.isdir(leg):
        parsed = _recipe.load_recipe(leg)
        checked = _seal.verify(leg)
        verdict = _build.audit(leg)
        totals = _run_layer.cost(leg) or {}
        return {"kind": "directory", "path": leg,
                "name": checked["name"], "root": checked["recomputed"],
                "build": _identity.build_digest(leg, parsed),
                "audited": bool(verdict["ok"] and checked["ok"]),
                "gates": verdict["gates"],
                "cost": {k: v for k, v in totals.items() if k != "discovery"},
                "discovery": totals.get("discovery"),
                "declared": _declared(parsed.get("claim")),
                "declared_known": True,
                "independence": _run_layer.independence(leg),
                "parsed": parsed}
    if os.path.isfile(leg):
        doc = _attest.record_read(leg)
        return {"kind": "record", "path": leg,
                "name": doc["name"], "root": doc["root"],
                "build": doc["build_digest"],
                "audited": all(g["status"] == "ok" for g in doc["gates"]),
                "gates": doc["gates"],
                "cost": dict(doc.get("cost") or {}),
                "discovery": None,
                "declared": dict(doc.get("claim") or {}),
                "declared_known": doc.get("record", 1) >= 2,
                "independence": doc.get("producer") or {},
                "parsed": None}
    raise ClaimError(f"a machine is a claim directory or a record file: {leg}")


def _shared_unit(c1: dict, c3: dict):
    """Exactly ONE unit decides: the strongest both machines measured.

    Wall-clock measures the host and its load as much as the work, so a
    weaker shared unit must never veto a comparison a stronger one can make
    -- and the strongest shared unit must be DECISIVE, so agreement on a
    weaker one cannot rescue it.
    """
    for unit in COST_LADDER:
        if _finite(c1.get(unit)) and _finite(c3.get(unit)) \
                and c1.get(unit):
            return unit
    return None


def _caller_tolerance(given):
    if given is not None:
        return float(given)
    from_env = os.environ.get(_ENV_TOLERANCE)
    if from_env:
        try:
            return float(from_env)
        except ValueError:
            return None
    return None


def crosscheck(m1: str, m2: str, m3: str, tolerance=None,
               mutants: int | None = None) -> dict:
    """The three-machine test. Three machines, not one directory thrice."""
    legs = (m1, m2, m3)
    seen = {}
    for leg in legs:
        key = os.path.realpath(leg)
        if key in seen:
            raise ClaimError(
                "the three machines must be distinct: a claim presented "
                f"twice agrees with itself and proves nothing ({leg})")
        seen[key] = True

    facts = {"M1": _machine(m1), "M2": _machine(m2), "M3": _machine(m3)}
    roots = {name: f["root"] for name, f in facts.items()}
    audited = {name: f["audited"] for name, f in facts.items()}
    equivalence = len(set(roots.values())) == 1
    reuse = facts["M1"]["build"] == facts["M2"]["build"]

    rejected, incomplete = [], []
    if not equivalence:
        rejected.append("one root across all three")
    if not reuse:
        rejected.append("byte reuse (M2 is a transfer, not a second redo)")
    for name in ("M1", "M2", "M3"):
        if not audited[name]:
            rejected.append(f"{name} verdicts re-earned")

    declared = facts["M1"]["declared"]
    declared_known = facts["M1"]["declared_known"]
    if not declared_known:
        incomplete.append(
            "the declared conditions: a version-1 record cannot say what the "
            "claim declared, and unknown is not 'none declared'")

    # -- the cost band -----------------------------------------------------
    c1, c3 = facts["M1"]["cost"], facts["M3"]["cost"]
    declared_tolerance = declared.get("tolerance") if declared_known else None
    caller = _caller_tolerance(tolerance)
    if declared_tolerance is not None and caller is not None:
        effective = min(float(declared_tolerance), caller)
    elif declared_tolerance is not None:
        effective = float(declared_tolerance)
    elif caller is not None:
        effective = caller
    else:
        effective = float(TOLERANCE)
    unit = _shared_unit(c1, c3)
    comparable = None
    ratio = None
    if unit:
        ratio = c3[unit] / c1[unit]
        comparable = _run_layer._in_band(c3[unit], c1[unit], effective)
    cost = {"comparable": comparable, "unit": unit, "ratio": ratio,
            "c1": c1 or None, "c3": c3 or None,
            "tolerance": effective,
            "declared_tolerance": (float(declared_tolerance)
                                   if declared_tolerance is not None
                                   else None),
            "tightened": bool(declared_tolerance is not None and
                              caller is not None and
                              caller < float(declared_tolerance)),
            "discovery": facts["M1"]["discovery"],
            "envelope": {}}
    if declared_tolerance is not None:
        if comparable is False:
            rejected.append("cost band")
        elif comparable is None:
            incomplete.append(
                "the declared tolerance band: the two ledgers share no unit, "
                "so the band could not be measured")

    # -- the pinned envelope ----------------------------------------------
    ceilings = declared.get("envelope") if declared_known else None
    for ceiling_unit, ceiling in sorted((ceilings or {}).items()):
        paid = c3.get(ceiling_unit)
        within = None if not _finite(paid) else paid <= ceiling
        cost["envelope"][ceiling_unit] = {"ceiling": ceiling, "paid": paid,
                                          "within": within}
        if within is False:
            rejected.append(f"envelope {ceiling_unit}")
        elif within is None:
            incomplete.append(
                f"the declared envelope ceiling on {ceiling_unit}: the redo "
                f"did not measure it")

    # -- the declared mutation floor --------------------------------------
    floor = declared.get("mutation_floor") if declared_known else None
    score = None
    if floor is not None:
        if mutants and facts["M3"]["kind"] == "directory":
            score = mutation_score(m3, max_mutants=mutants)
            score = dict(score)
            score["floor"] = float(floor)
            score["ok"] = (score["rate"] is not None and
                           score["rate"] >= float(floor))
            if score["ok"] is False:
                rejected.append("mutation floor")
        else:
            incomplete.append(
                "the declared mutation_floor: no mutation run measured it")

    verdict = "reject" if rejected else ("incomplete" if incomplete
                                         else "accept")
    return {"satisfied": verdict == "accept",
            "verdict": verdict,
            "rejected": rejected,
            "incomplete": incomplete,
            "roots": roots,
            "equivalence": equivalence,
            "reuse": reuse,
            "audited": audited,
            "names": {name: f["name"] for name, f in facts.items()},
            "transports": {name: f["kind"] for name, f in facts.items()},
            "cost": cost,
            "mutation_score": score,
            "independence": _run_layer._independence_line(
                facts["M3"]["independence"])}


def record_proof(m1: str, m2: str, m3: str, signers: str | None = None,
                 tolerance=None, mutants: int | None = None) -> dict:
    """Run the crosscheck and, on a pass, seal the proof onto M1.

    A proof is residue on M1's manifest, so M1 must be a DIRECTORY.
    Directory legs are the caller's own executions and need no anchor; a
    record leg is a relayed statement whose only provenance is a signature,
    so a durable proof refuses one the verifier's anchor does not verify --
    then embeds each record's digest and signer, so a reader can walk from
    the verdict to the statements beneath it.
    """
    if not os.path.isdir(m1):
        raise ClaimError(
            "a recorded proof lands on M1's manifest, so M1 must be a claim "
            "directory, not a frozen record")
    anchor = signers or os.environ.get(_ENV_SIGNERS)
    trail = []
    for leg in (m2, m3):
        if os.path.isdir(leg):
            continue
        doc = _attest.record_read(leg)
        signer = _attest.record_signer(leg, anchor) if anchor else None
        if not signer:
            raise ClaimError(
                f"a durable proof refuses a record whose signature this "
                f"verifier's anchor does not verify: {os.path.basename(leg)}")
        trail.append({"digest": _attest.record_digest(doc), "signer": signer,
                      "record": os.path.basename(leg)})
    result = crosscheck(m1, m2, m3, tolerance=tolerance, mutants=mutants)
    recorded = False
    if result["satisfied"]:
        proof = {"kind": "crosscheck", "when": _now(),
                 "m2": result["roots"]["M2"], "m3": result["roots"]["M3"],
                 "verdict": result["verdict"]}
        if trail:
            proof["records"] = trail
        _seal.seal(m1, proof=proof)
        recorded = True
    out = dict(result)
    out["proof_recorded"] = recorded
    return out
