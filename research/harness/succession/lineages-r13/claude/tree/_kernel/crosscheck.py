"""Crosscheck: the three-machine test, and the mutation-testing engine that
gives the equivalence class a measurable width (spec/verification.md).

`crosscheck` compares three legs -- a claim directory (a live execution) or a
record file (spec/record.md, a frozen one) -- in any mixture, and reaches one
three-valued verdict: accept, reject, or incomplete. A hard condition (one
root, byte reuse, every verdict earned, and whatever the claim's own recipe
declares -- tolerance, envelope, mutation floor) rejects on false and makes
the verdict incomplete when declared but unmeasured; an observation (cost
comparability with nothing declared, producer independence) is reported but
never decides.

`gate_deciders` and `vacuous_gates` name the files a gate's own command
reads, so a gate whose every decider is `generated` can be told apart from
one the claim actually tests. `mutation_score` draws deterministic mutants
of a claim's generated code from its root, re-earns each one cold, and
reports the kill rate -- the equivalence class's width, measured.
"""
import ast
import copy
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import tokenize

from . import attest
from . import build as build_mod
from . import core
from . import identity
from . import recipe as recipe_mod
from . import run as run_mod
from . import seal as seal_mod

# ------------------------------------------------------------ identity --
#
# `recipe_mod.load_recipe` and `identity._parts`/`seal_mod.verify` are
# pinned exactly as given and left unmodified; the two gaps a conforming
# kernel must still close are closed HERE, once, so every caller (kernel.py's
# seal/verify/audit, crosscheck's own per-leg audit) agrees on one identity
# rather than drifting into two: a `generated` output's own path shape never
# refuses identity (only `audit`'s copy-through-confinement needs to resolve
# it), and `[claim] environment` is automatically a pinned input (a
# dependency version decides what passing means, so it belongs in the root
# like any other criterion).

import tomllib as _tomllib


def load_recipe_for_identity(d: str) -> dict:
    """Like `recipe_mod.load_recipe`, except a `generated` produce step's
    output is exempt from the path-safety check."""
    path = recipe_mod.recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = _tomllib.load(f)
    except _tomllib.TOMLDecodeError as exc:
        raise core.ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    except OSError as exc:
        raise core.ClaimError(f"cannot read recipe {path!r}: {exc}") from exc

    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError(f"recipe {path!r} needs a [claim] table")
    name = claim.get("name")
    if not isinstance(name, str) or not name:
        raise core.ClaimError(f"recipe {path!r}: [claim] name is required and must be a string")
    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise core.ClaimError(f"recipe {path!r}: [claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise core.ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")

    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError(f"recipe {path!r}: [[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise core.ClaimError(f"recipe {path!r}: every step must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(
                f"recipe {path!r}: step kind must be one of {sorted(core.KINDS)}, got {kind!r}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise core.ClaimError(f"recipe {path!r}: every step needs an output")
        default_cls = "generated" if kind == "produce" else "pinned"
        if step.get("class", default_cls) != "generated":
            core._safe(d, output)
        if kind == "gate":
            run = step.get("run")
            if not isinstance(run, str) or not run:
                raise core.ClaimError(f"recipe {path!r}: a gate step needs a run command")

    recipe_mod._inputs(parsed, d)
    return parsed


def parts_for_identity(parsed: dict, d: str) -> dict:
    """`identity._parts`, plus `[claim] environment` as an automatic
    pinned input."""
    parts = identity._parts(parsed, d)
    env_file = (parsed.get("claim") or {}).get("environment")
    if env_file and f"input:{env_file}" not in parts:
        parts[f"input:{env_file}"] = core._hash_file(core._safe(d, env_file))
    return parts


def verify_for_identity(d: str) -> dict:
    """`seal_mod.verify`, over `parts_for_identity` rather than
    `identity._parts` directly -- the one recompute every caller (kernel.py,
    and this module's own `_earned`/`_leg_info`) must agree on."""
    manifest = seal_mod.read_manifest(d)
    parsed = load_recipe_for_identity(d)
    new_parts = parts_for_identity(parsed, d)
    recomputed = identity._hash_str(identity._canonical_json(new_parts))
    sealed_root = manifest["root"]
    ok = recomputed == sealed_root
    result = {"ok": ok, "root": sealed_root, "recomputed": recomputed, "name": manifest["name"]}
    if not ok:
        old_parts = manifest.get("parts")
        if isinstance(old_parts, dict):
            result["changed"] = seal_mod._changed_parts(old_parts, new_parts)
    return result


# ------------------------------------------------------------- furnish --

def authorize(d: str, recipe) -> dict:
    """Whether this host may test `d`'s claim: every `requires` entry
    present, and a declared `environment` furnished -- `build._authorized`,
    chdir'd to `d` first. `furnish`'s pip install resolves a requirements
    file's own RELATIVE local paths (`./probe-1.0-....whl`) against the
    process's current directory, not the requirements file's own, so
    furnishing from outside the claim silently looks there instead and
    fails every furnished claim whose caller's cwd is elsewhere."""
    real = os.path.realpath(d)
    old_cwd = os.getcwd()
    try:
        os.chdir(real)
        return build_mod._authorized(real, recipe)
    finally:
        os.chdir(old_cwd)


# ------------------------------------------------------- record (v2.6) --
#
# attest.py speaks RECORD_FORMAT 1 only: its member set has no `claim`, so
# a version-2 document (spec/record.md's declared-obligations member) reads
# as "unknown member" under its rules. Version 2 is validated here instead,
# by checking the `claim` table itself and then delegating every other
# field to attest's own (version-independent) rules over a version-1-shaped
# copy -- so the two implementations never drift on what a field means,
# only on whether `claim` may be present.

RECORD_FORMAT_2 = 2
_CLAIM_OBLIGATIONS = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_MEMBERS_V2 = attest._RECORD_MEMBERS | {"claim"}
_RECORD_REQUIRED_V2 = attest._RECORD_REQUIRED | {"claim"}


def _validate_claim_obligations(claim) -> None:
    if not isinstance(claim, dict):
        raise core.ClaimError("record: claim must be an object")
    unknown = set(claim) - _CLAIM_OBLIGATIONS
    if unknown:
        raise core.ClaimError(f"record: claim names unknown obligations: {sorted(unknown)}")
    for key in ("tolerance", "mutation_floor"):
        if key not in claim:
            continue
        value = claim[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise core.ClaimError(f"record: claim.{key} must be a non-negative number")
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise core.ClaimError("record: claim.envelope must be a non-empty object")
        for unit, ceiling in envelope.items():
            if unit not in core.COST_KEYS:
                raise core.ClaimError(f"record: claim.envelope names an unknown unit: {unit!r}")
            if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
                raise core.ClaimError(f"record: claim.envelope.{unit} must be a positive number")


def record_validate(doc) -> None:
    """Refuse, in band, a record outside the closed format this kernel
    understands -- version 1 (attest.py's own rules) or version 2 (those
    rules, plus the `claim` member)."""
    if not isinstance(doc, dict):
        raise core.ClaimError("a record must be a JSON object")
    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int):
        raise core.ClaimError("record: record must be an integer")
    if version > RECORD_FORMAT_2:
        raise core.ClaimError(
            f"record format {version} is newer than this kernel understands "
            f"(format {RECORD_FORMAT_2}); upgrade reticuli to read it")
    if version < RECORD_FORMAT_2:
        attest.record_validate(doc)
        return

    unknown = set(doc) - _RECORD_MEMBERS_V2
    if unknown:
        raise core.ClaimError(f"a record names unknown members: {sorted(unknown)}")
    missing = _RECORD_REQUIRED_V2 - set(doc)
    if missing:
        raise core.ClaimError(f"a record is missing required members: {sorted(missing)}")
    _validate_claim_obligations(doc["claim"])

    shadow = {k: v for k, v in doc.items() if k != "claim"}
    shadow["record"] = 1
    attest.record_validate(shadow)


def record_read(path: str) -> dict:
    """Read and validate a record document from disk (version 1 or 2). The
    file must BE its canonical bytes -- sorted keys, default separators --
    or it is refused: a record is signed over those exact bytes, so a
    reformatted copy is not the same document a signature could cover."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise core.ClaimError(f"cannot read record {path!r}: {exc}") from exc
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise core.ClaimError(f"malformed record {path!r}: {exc}") from exc
    record_validate(doc)
    if raw != attest.record_canonical(doc):
        raise core.ClaimError(
            f"record {path!r} is not its own canonical bytes: a record is its "
            "canonical serialization or it is not a record")
    return doc


def record_signer(path: str, anchor: str):
    """The signer identity whose detached ssh signature over the record at
    `path` verifies against `anchor`, in the `reticuli.record` namespace --
    or `None` if no principal verifies. Version-2 aware (attest.record_signer
    is not: it reads the record through its own version-1-only validator)."""
    signature = path + ".sig"
    if not (os.path.isfile(path) and os.path.isfile(signature) and os.path.isfile(anchor)):
        return None
    try:
        doc = record_read(path)
    except core.ClaimError:
        return None
    data = attest.record_canonical(doc)

    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", anchor, "-s", signature],
            capture_output=True, timeout=30, text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    principals = [line.split()[0] for line in found.stdout.splitlines() if line.strip()]

    for principal in principals:
        try:
            verified = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", principal,
                 "-n", attest.RECORD_NAMESPACE, "-s", signature],
                input=data, capture_output=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if verified.returncode == 0:
            return principal
    return None


# --------------------------------------------------------------- deciders --

_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_REDIRECTS = frozenset({'>', '>>', '<', '2>', '2>>', '&>'})

_SPLIT_RE = re.compile(r'\|\||&&|[&|;\n]')


def _split_commands(cmd: str) -> list:
    """`cmd` cut on the shell operators in `_OPERATORS`, longest first."""
    return [p.strip() for p in _SPLIT_RE.split(cmd) if p.strip()]


def gate_deciders(cmd: str) -> list:
    """The workspace files a gate's own command reads to decide its
    verdict: a path-like command name (`./check`), or -- for a recognized
    interpreter -- the bare-word arguments that are not flags, flag values,
    or redirection targets."""
    deciders = []
    for sub in _split_commands(cmd):
        try:
            tokens = shlex.split(sub)
        except ValueError:
            continue
        if not tokens:
            continue
        head, rest = tokens[0], tokens[1:]
        if "/" in head:
            deciders.append(head[2:] if head.startswith("./") else head)
            continue
        if os.path.basename(head) not in _INTERPRETERS:
            continue
        skip_next = False
        for tok in rest:
            if skip_next:
                skip_next = False
                continue
            if tok in _REDIRECTS:
                skip_next = True
                continue
            if tok.startswith("-"):
                if tok in _SKIP_VALUE:
                    skip_next = True
                continue
            deciders.append(tok)
    return deciders


def vacuous_gates(parsed: dict) -> list:
    """Gates whose every decider is a `generated` output -- the verdict
    depends on no claim at all."""
    generated = set(recipe_mod.generated_outputs(parsed))
    out = []
    for step in recipe_mod.gates(parsed):
        deciders = gate_deciders(step.get("run", ""))
        if deciders and all(d in generated for d in deciders):
            out.append(step["output"])
    return out


# ---------------------------------------------------------- mutation ops --

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_ARITHMETIC = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)

_OP_KIND = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%",
    ast.Gt: ">", ast.Lt: "<", ast.GtE: ">=", ast.LtE: "<=",
    ast.Eq: "==", ast.NotEq: "!=", ast.And: "and", ast.Or: "or",
}

_OP_ALTS = {
    ast.Add: (ast.Sub,), ast.Sub: (ast.Add,),
    ast.Mult: (ast.FloorDiv,), ast.Div: (ast.Mult,),
    ast.FloorDiv: (ast.Mult,), ast.Mod: (ast.Mult,),
    ast.Gt: (ast.Lt, ast.GtE), ast.Lt: (ast.Gt, ast.LtE),
    ast.GtE: (ast.Lt,), ast.LtE: (ast.Gt,),
    ast.Eq: (ast.NotEq,), ast.NotEq: (ast.Eq,),
    ast.And: (ast.Or,), ast.Or: (ast.And,),
}

_WORD_ALTS = {"True": "False", "False": "True", "and": "or", "or": "and",
              "break": "continue", "continue": "break"}

_STRING_LITERAL = re.compile(r'("(?:[^"\\]|\\.)*")|(\'(?:[^\'\\]|\\.)*\')')


def _line_offsets(source: str) -> list:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _node_span(node, source: str):
    """A node's (start, end) character offsets in `source`."""
    offsets = _line_offsets(source)
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    return (start, end)


def _span_text(source: str, span) -> str:
    return source[span[0]:span[1]]


def _splice(source: str, span, replacement: str) -> str:
    return source[:span[0]] + replacement + source[span[1]:]


def _edit(source: str, node, replacement: str) -> str:
    return _splice(source, _node_span(node, source), replacement)


def _label(kind: str, loc: int, old: str, new: str) -> str:
    return f"{kind}@{loc}:{old}->{new}"


def _named(kind: str, node, source: str, new_text: str):
    span = _node_span(node, source)
    old_text = _span_text(source, span)
    mutated = _splice(source, span, new_text)
    return _label(kind, span[0], old_text, new_text), mutated


def _docstring_spans(source: str) -> list:
    """Spans of module/function/class docstrings -- left alone by the
    token-level mutants, which would otherwise mutate prose, not behavior."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    spans = []
    nodes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for node in nodes:
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            spans.append(_node_span(body[0], source))
    return spans


def _structural_mutants(source: str) -> list:
    """AST-level mutants: comparison, arithmetic, and boolean operators
    flipped to a deterministic alternative."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            kind = type(node.ops[0])
            for alt in _OP_ALTS.get(kind, ()):
                clone = copy.deepcopy(node)
                clone.ops = [alt()]
                try:
                    out.append(_named("cmp", node, source, ast.unparse(clone)))
                except Exception:
                    continue
        elif isinstance(node, ast.BinOp) and type(node.op) in _ARITHMETIC:
            kind = type(node.op)
            for alt in _OP_ALTS.get(kind, ()):
                clone = copy.deepcopy(node)
                clone.op = alt()
                try:
                    out.append(_named("arith", node, source, ast.unparse(clone)))
                except Exception:
                    continue
        elif isinstance(node, ast.BoolOp):
            kind = type(node.op)
            for alt in _OP_ALTS.get(kind, ()):
                clone = copy.deepcopy(node)
                clone.op = alt()
                try:
                    out.append(_named("bool", node, source, ast.unparse(clone)))
                except Exception:
                    continue
    return out


def _token_mutants(source: str) -> list:
    """Token-level mutants: bare words (`True`/`False`/`and`/`or`/...)
    flipped outside any docstring."""
    out = []
    skip_spans = _docstring_spans(source)
    offsets = _line_offsets(source)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenizeError, IndentationError, SyntaxError, ValueError):
        return out
    for tok in tokens:
        if tok.type != tokenize.NAME or tok.string not in _WORD_ALTS:
            continue
        start = offsets[tok.start[0] - 1] + tok.start[1]
        end = offsets[tok.end[0] - 1] + tok.end[1]
        if any(s <= start < e for s, e in skip_spans):
            continue
        new_text = _WORD_ALTS[tok.string]
        out.append((_label("word", start, tok.string, new_text),
                     _splice(source, (start, end), new_text)))
    return out


def _draw_order(n: int, root: str) -> list:
    """A deterministic permutation of `range(n)`, seeded by `root`."""
    return sorted(range(n), key=lambda i: hashlib.sha256(f"{root}:{i}".encode()).hexdigest())


def _mutant_order(items: list, root: str) -> list:
    """`items` reordered deterministically, seeded by `root`."""
    order = _draw_order(len(items), root)
    return [items[i] for i in order]


def _mutants(source: str, root: str) -> list:
    """Every distinct mutant of `source`, deduplicated and ordered
    deterministically from `root`."""
    candidates = _structural_mutants(source) + _token_mutants(source)
    seen = set()
    uniq = []
    for label, mutated in candidates:
        if mutated == source or mutated in seen:
            continue
        seen.add(mutated)
        uniq.append((label, mutated))
    return _mutant_order(uniq, root)


def _machine(d: str, recipe, output: str, mutated_source: str) -> bool:
    """Judge one mutant: materialize a fresh room over `d`'s claim, swap in
    the mutated bytes for `output`, re-run every gate. True iff it SURVIVES
    (every gate still reproduces the pinned verdict)."""
    room = tempfile.mkdtemp(prefix="reticuli-mutant-")
    try:
        build_mod._materialize(d, room, recipe, include_generated=True)
        with open(core._safe(room, output), "w", encoding="utf-8") as f:
            f.write(mutated_source)
        for step in recipe_mod.gates(recipe):
            result = run_mod.run_gate(step["run"], room, recipe)
            if result["status"] != "ok":
                return False
            if not build_mod._compare_pin(d, room, step["output"]):
                return False
        return True
    finally:
        shutil.rmtree(room, ignore_errors=True)


def mutation_score(d: str, max_mutants: int = core.MUTANT_CEILING) -> dict:
    """Mutants of `d`'s generated `.py` outputs, drawn deterministically
    from the sealed root, re-judged cold. Residue only; never the root."""
    recipe = recipe_mod.load_recipe(d)
    root_hash = seal_mod.read_manifest(d)["root"]
    pool = []
    for output in recipe_mod.generated_outputs(recipe):
        if not output.endswith(".py"):
            continue
        path = core._safe(d, output)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            source = f.read()
        for label, mutated in _mutants(source, root_hash):
            pool.append((output, label, mutated))
    pool = _mutant_order(pool, root_hash)
    sample = pool[:max_mutants]

    survivors = []
    killed = 0
    for output, label, mutated in sample:
        if _machine(d, recipe, output, mutated):
            survivors.append(label)
        else:
            killed += 1
    total = len(sample)
    rate = (killed / total) if total else 1.0
    result = {"mutants": total, "rate": rate, "survivors": survivors}
    core._write_json(os.path.join(d, core.MUTATION_RESIDUE), result)
    return result


# --------------------------------------------------------- sign_node -----

def sign_node(root: str, digest: str, links) -> str:
    """One signature-chain node: the root and build digest it is over, and
    the SET of signatures beneath it (enumeration order is not identity)."""
    payload = json.dumps({"root": root, "build_digest": digest,
                          "links": sorted(links)}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------- independence --

def independence(path: str) -> dict:
    """Declared producer identity for one machine: read from its ledger (a
    claim directory) or its `producer` block (a record)."""
    if os.path.isdir(path):
        for event in reversed(run_mod.ledger_events(path)):
            if event.get("event") == "producer":
                return {"vendor": event.get("vendor"), "model": event.get("model"),
                        "blind": event.get("blind")}
        return {"vendor": None, "model": None, "blind": None}
    doc = record_read(path)
    producer = doc.get("producer", {}) or {}
    return {"vendor": producer.get("vendor"), "model": producer.get("model"),
            "blind": producer.get("blind")}


def _independence_note(m3_info: dict) -> str:
    vendor, model = m3_info.get("vendor"), m3_info.get("model")
    if vendor and model:
        workspace = "blind workspace" if m3_info.get("blind") else "non-blind workspace"
        return f"declared: {vendor}/{model}, {workspace} (not proven)"
    return "unestablished (from content)"


# ------------------------------------------------------------- legs -----

def _earned(d: str) -> bool:
    """A claim directory's own minimal audit: every gate re-run cold must
    reproduce its pinned verdict."""
    recipe = recipe_mod.load_recipe(d)
    try:
        verified = verify_for_identity(d)
    except (OSError, UnicodeDecodeError, ValueError, core.ClaimError):
        return False
    if not verified["ok"]:
        return False
    auth = authorize(d, recipe)
    if not auth["ok"]:
        return False
    room = tempfile.mkdtemp(prefix="reticuli-cc-")
    old_path = os.environ.get("PATH")
    try:
        build_mod._materialize(d, room, recipe, include_generated=True)
        if auth.get("venv"):
            os.environ["PATH"] = os.path.join(auth["venv"], "bin") + os.pathsep + (old_path or "")
        for step in recipe_mod.gates(recipe):
            result = run_mod.run_gate(step["run"], room, recipe)
            if result["status"] != "ok" or not build_mod._compare_pin(d, room, step["output"]):
                return False
        return True
    finally:
        if auth.get("venv"):
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path
        shutil.rmtree(room, ignore_errors=True)


def _leg_info(path: str) -> dict:
    """Normalize one crosscheck leg -- a claim directory or a record file --
    into its root, build digest, earned verdict, declared obligations
    (`None` means unknowable: a version-1 record), and measured cost."""
    if os.path.isdir(path):
        recipe = recipe_mod.load_recipe(path)
        try:
            verified = verify_for_identity(path)
            root_val = verified["recomputed"]
            bdigest = identity.build_digest(path)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise core.ClaimError(f"crosscheck cannot read {path!r}: {exc}") from exc
        claim_tbl = recipe.get("claim", {}) or {}
        declared = {k: claim_tbl[k] for k in ("tolerance", "envelope", "mutation_floor")
                    if k in claim_tbl}
        return {"root": root_val, "build_digest": bdigest, "earned": _earned(path),
                "declared": declared, "cost": run_mod.cost(path)}

    doc = record_read(path)
    earned = all(g["status"] == "ok" for g in doc["gates"])
    declared = doc.get("claim", {}) if doc["record"] >= 2 else None
    return {"root": doc["root"], "build_digest": doc["build_digest"], "earned": earned,
            "declared": declared, "cost": doc.get("cost")}


def _strongest_shared(c1, c3):
    if not c1 or not c3:
        return None, None, None
    for unit in core.COST_LADDER:
        if unit in c1 and unit in c3:
            return unit, c1[unit], c3[unit]
    return None, None, None


# ----------------------------------------------------------- crosscheck --

def crosscheck(m1: str, m2: str, m3: str, mutants: int = None) -> dict:
    """The three-machine test: one root, byte reuse (M1 vs M2), every
    verdict earned, and whatever the claim declares -- over any mixture of
    claim directories and frozen records."""
    reals = {os.path.realpath(p) for p in (m1, m2, m3)}
    if len(reals) < 3:
        raise core.ClaimError(
            "crosscheck requires three distinct claims, not the same path presented more than once")

    legs = {"M1": _leg_info(m1), "M2": _leg_info(m2), "M3": _leg_info(m3)}
    roots = {k: v["root"] for k, v in legs.items()}
    equivalence = len(set(roots.values())) == 1
    reuse = legs["M1"]["build_digest"] == legs["M2"]["build_digest"]
    audited = {k: v["earned"] for k, v in legs.items()}

    obligations_unknown = legs["M1"]["declared"] is None
    declared = legs["M1"]["declared"] or {}

    c1, c3 = legs["M1"]["cost"], legs["M3"]["cost"]
    tol = declared.get("tolerance", core.TOLERANCE)
    unit, v1, v3 = _strongest_shared(c1, c3)
    if unit is None:
        comparable = None
    else:
        if v1:
            ratio = v3 / v1
        else:
            ratio = None if v3 == 0 else float("inf")
        comparable = ratio is not None and (1.0 / tol) <= ratio <= tol
    cost_report = {"comparable": comparable, "unit": unit, "envelope": {}}

    rejected, incomplete = [], []

    if "tolerance" in declared:
        if comparable is None:
            incomplete.append("cost tolerance")
        elif not comparable:
            rejected.append("cost tolerance")

    envelope = declared.get("envelope") or {}
    for eunit, ceiling in envelope.items():
        measured = (c3 or {}).get(eunit)
        within = (measured <= ceiling) if measured is not None else None
        cost_report["envelope"][eunit] = {"ceiling": ceiling, "measured": measured, "within": within}
        if within is False:
            rejected.append(f"envelope {eunit}")
        elif within is None:
            incomplete.append(f"envelope {eunit}")

    mutation_result = None
    if "mutation_floor" in declared:
        floor = declared["mutation_floor"]
        if mutants is not None and os.path.isdir(m3):
            ms = mutation_score(m3, max_mutants=mutants)
            ok = ms["rate"] >= floor
            mutation_result = {**ms, "ok": ok}
            if not ok:
                rejected.append("mutation floor")
        else:
            incomplete.append("mutation floor")

    if obligations_unknown:
        incomplete.append("declared conditions (frozen M1 is a version-1 record)")

    if not equivalence:
        rejected.append("one root")
    if not reuse:
        rejected.append("byte reuse")
    if not all(audited.values()):
        rejected.append("every verdict earned")

    if rejected:
        verdict = "reject"
    elif incomplete:
        verdict = "incomplete"
    else:
        verdict = "accept"

    note = _independence_note(independence(m3))

    return {
        "satisfied": verdict == "accept",
        "verdict": verdict,
        "roots": roots,
        "equivalence": equivalence,
        "reuse": reuse,
        "audited": audited,
        "cost": cost_report,
        "rejected": rejected,
        "incomplete": incomplete,
        "independence": note,
        "mutation_score": mutation_result,
    }


def record_proof(m1: str, m2: str, m3: str) -> dict:
    """Run the crosscheck; on a pass, seal the proof onto M1 as residue.
    M1 must be a directory. A record leg's signature must verify against
    the trust anchor (`RETICULI_SIGNERS`) or the proof refuses outright."""
    if not os.path.isdir(m1):
        raise core.ClaimError("a proof can only be recorded onto a claim directory (M1)")

    anchor = os.environ.get(core._ENV_SIGNERS)
    records = []
    for name, path in (("M2", m2), ("M3", m3)):
        if os.path.isdir(path):
            continue
        if not anchor or not os.path.isfile(anchor):
            raise core.ClaimError(
                f"{name} is a frozen record; no trust anchor to verify its signature")
        signer = record_signer(path, anchor)
        if not signer:
            raise core.ClaimError(f"{name}'s record signature does not verify against the anchor")
        doc = record_read(path)
        records.append({"signer": signer, "digest": attest.record_digest(doc)})

    result = crosscheck(m1, m2, m3)
    if not result["satisfied"]:
        return {"proof_recorded": False, "verdict": result["verdict"]}

    manifest = seal_mod.read_manifest(m1)
    manifest["proof"] = {"kind": "crosscheck", "m2": m2, "m3": m3, "records": records}
    core._write_json(os.path.join(m1, core.MANIFEST), manifest)
    return {"proof_recorded": True, "verdict": result["verdict"]}
