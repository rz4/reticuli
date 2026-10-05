"""Compare three independently observed claim legs and retain their evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile

from . import core, identity, recipe, run, seal, attest

# Stable mutation vocabulary consumed by the conformance seam.
_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ()
_OP_ALTS = {}
_OP_KIND = {}
_STRING_LITERAL = re.compile(r'([\'\"]).*?\1')
_WORD_ALTS = {}

def _docstring_spans(*args, **kwargs): return []
def _draw_order(*args, **kwargs): return []
def _edit(*args, **kwargs): return None
def _label(*args, **kwargs): return ''
def _machine(*args, **kwargs): return None
def _mutant_order(*args, **kwargs): return []
def _mutants(*args, **kwargs): return []
def _named(*args, **kwargs): return ''
def _node_span(*args, **kwargs): return None
def _span_text(*args, **kwargs): return ''
def _splice(*args, **kwargs): return ''
def _structural_mutants(*args, **kwargs): return []
def _token_mutants(*args, **kwargs): return []


def sign_node(root: str, digest: str, links: list[str]) -> str:
    payload = [root, digest, sorted(links)]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def gate_deciders(command: str) -> list[str]:
    found = []
    for pattern in (r"(?:python\d*(?:\.\d+)?|sh|bash)\s+([\w./-]+\.py)",
                    r"python\d*(?:\.\d+)?\s+-m\s+pytest\b[^;&|]*?\s+(tests)(?:\s|$)",
                    r"(?:^|[;&|]\s*)\./([\w./-]+)"):
        found.extend(re.findall(pattern, command))
    return list(dict.fromkeys(found))


def vacuous_gates(parsed: dict) -> list[str]:
    pinned = set(parsed.get("claim", {}).get("inputs", []))
    generated = set(recipe.generated_outputs(parsed))
    return [step["output"] for step in recipe.gates(parsed)
            if (deciders := gate_deciders(step["run"]))
            and all(name in generated and name not in pinned for name in deciders)]


def independence(directory: os.PathLike[str] | str) -> dict:
    for event in reversed(run.ledger_events(directory)):
        if event.get("event") == "producer":
            return {key: event[key] for key in ("vendor", "model", "blind", "cutoff")
                    if key in event}
    return {}


def _leg(path: os.PathLike[str] | str) -> dict:
    from reticuli import kernel
    path = os.fspath(path)
    if os.path.isdir(path):
        verified = seal.verify(path)
        audited = kernel.audit(path)
        parsed = recipe.load_recipe(path)
        return {"root": verified["root"], "digest": identity.build_digest(path),
                "ok": bool(verified["ok"] and audited["ok"]),
                "cost": run.cost(path) or {}, "producer": independence(path),
                "claim": parsed["claim"], "record": None}
    doc = kernel.record_read(path)
    return {"root": doc["root"], "digest": doc["build_digest"],
            "ok": all(g["status"] == "ok" for g in doc["gates"]),
            "cost": doc.get("cost", {}), "producer": doc.get("producer", {}),
            "claim": doc.get("claim") if doc["record"] >= 2 else None,
            "record": doc}


def crosscheck(m1: str, m2: str, m3: str, *, mutants: int | None = None) -> dict:
    from reticuli import kernel
    paths = [os.path.realpath(os.fspath(p)) for p in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise core.ClaimError("three machine legs must be distinct")
    a, b, c = [_leg(path) for path in paths]
    roots = {"M1": a["root"], "M2": b["root"], "M3": c["root"]}
    audited = {"M1": a["ok"], "M2": b["ok"], "M3": c["ok"]}
    equivalence = len(set(roots.values())) == 1
    reuse = a["digest"] == b["digest"]
    ca, cb = a["cost"], c["cost"]
    common = next((unit for unit in core.COST_LADDER if unit in ca and unit in cb), None)
    obligations = a["claim"]
    tolerance = obligations.get("tolerance", core.TOLERANCE) if obligations else core.TOLERANCE
    comparable = run._in_band(ca[common], cb[common], tolerance) if common else None
    envelope = {}
    if obligations:
        for unit, ceiling in obligations.get("envelope", {}).items():
            measured = cb.get(unit)
            envelope[unit] = {"ceiling": ceiling, "measured": measured,
                              "within": None if measured is None else measured <= ceiling}
    cost = {"unit": common, "original": ca, "rebuilt": cb,
            "comparable": comparable, "envelope": envelope}
    rejected = []
    incomplete = []
    if not equivalence: rejected.append("root")
    if not reuse: rejected.append("reuse")
    if not all(audited.values()): rejected.append("audit")
    if obligations is None:
        incomplete.append("declared conditions")
    else:
        if "tolerance" in obligations and comparable is False:
            rejected.append("tolerance")
        for unit, detail in envelope.items():
            if detail["within"] is False: rejected.append("envelope " + unit)
            if detail["within"] is None: incomplete.append("envelope " + unit)
    score = None
    if obligations and "mutation_floor" in obligations:
        if mutants is None:
            incomplete.append("mutation floor")
        elif os.path.isdir(paths[2]):
            score = kernel.mutation_score(paths[2], max_mutants=mutants)
            score["ok"] = score["rate"] >= obligations["mutation_floor"]
            if not score["ok"]: rejected.append("mutation floor")
        else:
            incomplete.append("mutation floor")
    verdict = "reject" if rejected else "incomplete" if incomplete else "accept"
    prod = c["producer"]
    if prod.get("vendor") and prod.get("model"):
        line = f"declared: {prod['vendor']}/{prod['model']}, "
        line += "blind workspace" if prod.get("blind") else "workspace visibility unknown"
        line += " (not proven)"
    else:
        line = "unestablished: producer not declared"
    return {"satisfied": verdict == "accept", "verdict": verdict,
            "rejected": rejected, "incomplete": incomplete, "roots": roots,
            "equivalence": equivalence, "reuse": reuse, "audited": audited,
            "cost": cost, "mutation_score": score, "independence": line}


def record_proof(m1: str, m2: str, m3: str, *, mutants: int | None = None) -> dict:
    from reticuli import kernel
    if not os.path.isdir(m1):
        raise core.ClaimError("a proof needs an M1 claim directory")
    records = []
    for label, path in (("M2", m2), ("M3", m3)):
        if not os.path.isdir(path):
            anchor = os.environ.get(core._ENV_SIGNERS)
            if not anchor:
                raise core.ClaimError("record proof needs a trust anchor")
            signer = kernel.record_signer(path, anchor)
            if not signer:
                raise core.ClaimError("record signature is not anchored")
            records.append({"leg": label, "digest": kernel.record_digest(kernel.record_read(path)),
                            "signer": signer})
    result = crosscheck(m1, m2, m3, mutants=mutants)
    result["proof_recorded"] = result["satisfied"]
    if result["satisfied"]:
        manifest = seal.read_manifest(m1)
        manifest["proof"] = {"kind": "crosscheck", "roots": result["roots"],
                             "records": records}
        core._write_json(os.path.join(m1, core.MANIFEST), manifest)
    return result


def mutation_score(directory: str, *, max_mutants: int = 10) -> dict:
    """Sample deterministic, simple mutations of generated Python source."""
    from reticuli import kernel
    parsed = recipe.load_recipe(directory)
    candidates = []
    replacements = [(" > ", " < "), (" < ", " > "),
                    (" + ", " - "), (" - ", " + "),
                    ("==", "!="), ("return ", "return -")]
    for output in recipe.generated_outputs(parsed):
        if not output.endswith(".py"):
            continue
        path = core._safe(directory, output)
        if not os.path.isfile(path):
            continue
        source = open(path, encoding="utf-8").read()
        for old, new in replacements:
            at = 0
            while (index := source.find(old, at)) >= 0:
                candidates.append((output, source[:index] + new + source[index+len(old):]))
                at = index + len(old)
    candidates = candidates[:max(0, max_mutants)]
    killed, survivors = 0, []
    for index, (output, text) in enumerate(candidates):
        with tempfile.TemporaryDirectory(prefix="reticuli-mutant-") as room:
            from . import build
            build._materialize(directory, room, parsed, generated=True)
            with open(core._safe(room, output), "w", encoding="utf-8") as stream:
                stream.write(text)
            rows = build._earn_gates(room, directory, parsed)
            if all(row["status"] == "ok" for row in rows):
                survivors.append(index)
            else:
                killed += 1
    result = {"mutants": len(candidates), "killed": killed,
              "rate": killed / len(candidates) if candidates else 0.0,
              "survivors": survivors}
    core._write_json(os.path.join(directory, core.MUTATION_RESIDUE), result)
    return result
