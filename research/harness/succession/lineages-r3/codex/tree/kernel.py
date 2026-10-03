"""Public kernel: identity, judging, rebuilding, and three-machine comparison."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib

from ._kernel import core, recipe, identity, seal as seal_module, run, build, attest
from ._kernel import crosscheck as mutations

ClaimError = core.ClaimError
NAMESPACE = core.NAMESPACE
SIGN_NAMESPACE = core.SIGN_NAMESPACE
SIGN_DIR = core.SIGN_DIR
RECIPE = core.RECIPE
STORE = core.STORE
MANIFEST = core.MANIFEST
LEDGER = core.LEDGER
_JAILED = core._JAILED
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = attest.RECORD_FORMAT
record_validate = attest.record_validate
record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_signer = attest.record_signer
_hash_file = core._hash_file
root = identity.root
load_recipe = recipe.load_recipe
read_manifest = seal_module.read_manifest
build_digest = identity.build_digest
ledger = run.ledger
ledger_events = run.ledger_events


def _validate_claim(parsed):
    claim = parsed["claim"]
    envelope = claim.get("envelope")
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("claim envelope must be a nonempty table")
        for unit, amount in envelope.items():
            if unit not in core.COST_KEYS or type(amount) not in (int, float) or amount <= 0:
                raise ClaimError("invalid claim envelope ceiling")
    for key in ("tolerance", "mutation_floor"):
        if key in claim and (type(claim[key]) not in (int, float) or claim[key] < 0):
            raise ClaimError(f"invalid claim {key}")
    return parsed


def load_recipe(directory):
    try:
        return _validate_claim(recipe.load_recipe(directory))
    except ClaimError as error:
        # Generated names may be symlinks in a sealed claim; audit rejects
        # copying their bytes. The recipe itself remains readable.
        if "symlink in claim path" not in str(error):
            raise
        try:
            with open(recipe.recipe_path(directory), "rb") as stream:
                parsed = tomllib.load(stream)
            recipe._inputs(parsed, directory)
            for step in recipe._steps(parsed):
                name = step["output"]
                if (step.get("kind") == "produce"
                        and step.get("class", "generated") in ("generated", "free")
                        and os.path.islink(os.path.join(directory, name))):
                    continue
                core._safe(directory, name)
            return _validate_claim(parsed)
        except (OSError, UnicodeError, ValueError, KeyError, tomllib.TOMLDecodeError) as exc:
            raise ClaimError(str(exc)) from exc


def seal(directory):
    parsed = load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(os.path.join(directory, MANIFEST), manifest)
    return manifest


def verify(directory):
    parsed = load_recipe(directory)
    manifest = read_manifest(directory)
    recomputed = identity.root(parsed, directory)
    result = {"ok": manifest["root"] == recomputed and manifest["name"] == parsed["claim"]["name"],
              "root": manifest["root"], "recomputed": recomputed,
              "name": manifest["name"]}
    return result


def record_read(path):
    doc = attest.record_read(path)
    with open(path, "rb") as stream:
        if stream.read() != record_canonical(doc):
            raise ClaimError("record file is not canonical JSON")
    return doc


def preflight(parsed):
    missing = []
    for requirement in parsed.get("claim", {}).get("requires", []):
        if requirement.startswith("python") and re.fullmatch(r"python(?:3)?(?:>=|>|==)[0-9.]+", requirement):
            match = re.match(r"python(?:3)?(>=|>|==)([0-9.]+)", requirement)
            have = sys.version_info[:2]
            need = tuple(map(int, match.group(2).split(".")))
            op = match.group(1)
            if not {">=": have >= need, ">": have > need, "==": have == need}[op]:
                missing.append(requirement)
        elif shutil.which(requirement) is None:
            try:
                import importlib.util
                found = importlib.util.find_spec(requirement)
            except (ValueError, ImportError):
                found = None
            if found is None:
                missing.append(requirement)
    return missing


def sandbox(command=None, directory=None):
    backend = run.sandbox_backend()
    return ([core._SHELL, "-c", command or "true"], backend)


def run_gate(command, directory, parsed=None, *, env=None, timeout=None):
    parsed = parsed or {}
    missing = preflight(parsed)
    if missing:
        return {"status": "environment", "quarantine": None,
                "detail": "missing requirements: " + ", ".join(missing),
                "stderr": "", "stdout": ""}
    backend = run.sandbox_backend()
    environment = run._scrub_env(os.fspath(directory), env, backend)
    if backend in ("seatbelt", "bubblewrap"):
        environment[core._JAILED] = backend
    bound = timeout or run.gate_timeout(parsed)
    try:
        bound = min(bound, float(os.environ.get(core._ENV_TIMEOUT, bound)))
    except ValueError:
        pass
    result = run._run(run._sandbox_argv(command, os.fspath(directory), backend),
                      os.fspath(directory), environment, bound)
    result["quarantine"] = backend
    return result


def cost(directory):
    totals = {}
    for event in ledger_events(directory):
        if event.get("event") not in ("oracle", "producer", "produce") and event.get("kind") not in ("producer", "produce"):
            continue
        for unit in core.COST_KEYS:
            number = event.get(unit)
            if type(number) in (int, float) and number >= 0:
                totals[unit] = totals.get(unit, 0) + number
    return totals or None


def gate_deciders(command):
    tokens = shlex.split(command)
    out = []
    for i, token in enumerate(tokens):
        if token in ("python", "python3", "pytest", "py.test") and i + 1 < len(tokens):
            if token in ("pytest", "py.test") and i >= 2 and tokens[i-1] == "-m":
                continue
            j = i + 1
            if tokens[j] == "-m":
                j += 2
                while j < len(tokens) and tokens[j].startswith("-"):
                    j += 1
            if j < len(tokens) and tokens[j] not in ("&&", ";", "|"):
                out.append(tokens[j])
        elif token.startswith("./"):
            out.append(token[2:])
    return out


def vacuous_gates(parsed):
    inputs = set(parsed.get("claim", {}).get("inputs", []))
    generated = set(recipe.generated_outputs(parsed))
    return [gate["output"] for gate in recipe.gates(parsed)
            if (deciders := gate_deciders(gate["run"]))
            and all(d in generated and d not in inputs for d in deciders)]


def _materialize(directory, into, parsed, *, generated=True):
    return build._materialize(directory, into, parsed, generated=generated)


def _furnish(room, parsed):
    previous = os.getcwd()
    try:
        os.chdir(room)
        return run.furnish(room, parsed)
    finally:
        os.chdir(previous)


def _copy_external(source, target, name):
    core._hash_file(source)
    destination = core._safe(target, name)
    core._copy_into(source, destination)


def _gate_results(source, room, parsed, *, furnished=None):
    gates = []
    env = {"PATH": furnished + os.pathsep + os.environ.get("PATH", os.defpath)} if furnished else None
    for step in recipe.gates(parsed):
        outcome = run_gate(step["run"], room, parsed, env=env)
        status = outcome["status"]
        if status == "ok":
            try:
                if core._hash_file(core._safe(source, step["output"])) != core._hash_file(core._safe(room, step["output"])):
                    status = "mismatch"
            except ClaimError:
                status = "mismatch"
        gates.append({"output": step["output"], "status": status,
                      "quarantine": outcome.get("quarantine"),
                      "detail": outcome.get("detail") or outcome.get("stderr", "")})
        if status != "ok":
            break
    return gates


def audit(directory, *, shallow=False, produce_from=None):
    checked = verify(directory)
    if not checked["ok"]:
        return {"ok": False, "root": checked["root"], "gates": [], "detail": "identity mismatch"}
    parsed = load_recipe(directory)
    missing = preflight(parsed)
    if missing:
        return {"ok": False, "root": checked["root"], "environment": missing,
                "gates": [{"output": g["output"], "status": "environment", "quarantine": None}
                          for g in recipe.gates(parsed)]}
    with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
        _materialize(directory, room, parsed)
        for name, path in (produce_from or {}).items():
            _copy_external(path, room, name)
        try:
            furnished = _furnish(room, parsed)
        except ClaimError as exc:
            return {"ok": False, "root": checked["root"], "detail": str(exc),
                    "gates": [{"output": g["output"], "status": "environment", "quarantine": None}
                              for g in recipe.gates(parsed)]}
        gates = _gate_results(directory, room, parsed, furnished=furnished)
    return {"ok": bool(gates) and all(g["status"] == "ok" for g in gates),
            "root": checked["root"], "gates": gates}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None):
    source = os.path.abspath(directory)
    target = os.path.abspath(into)
    parsed = load_recipe(source)
    if os.path.exists(target) and os.listdir(target):
        raise ClaimError("rebuild target is not empty")
    missing = preflight(parsed)
    if missing:
        raise ClaimError("environment missing: " + ", ".join(missing))
    os.makedirs(target, exist_ok=True)
    _materialize(source, target, parsed, generated=False)
    for name, path in (input_from or {}).items():
        _copy_external(path, target, name)
    for name, path in (produce_from or {}).items():
        _copy_external(path, target, name)
        ledger(target, {"event": "reuse", "output": name})
    snapshot = {name: core._hash_file(core._safe(target, name))
                for name in [os.path.basename(recipe.recipe_path(target)), *recipe._inputs(parsed, target)]}
    backend = sandbox("true", target)[1]
    ledger(target, {"event": "environment", "python": sys.version, "platform": sys.platform,
                    "quarantine": backend})
    ledger(target, {"event": "producer", "vendor": os.environ.get(core._ENV_VENDOR),
                    "model": os.environ.get(core._ENV_MODEL), "blind": True})
    outputs = recipe.generated_outputs(parsed)
    if isinstance(producer, str):
        commands = [producer]
    else:
        commands = producer
    for output in outputs:
        if output in (produce_from or {}):
            continue
        command = commands[output] if isinstance(commands, dict) else commands[0]
        env = run._scrub_env(target, {core._ENV_OUTPUT: output,
                                     core._ENV_REQUEST: next((build._step_guidance(s) for s in recipe.produces(parsed) if s["output"] == output), ""),
                                     core._ENV_CLAIM: target,
                                     core._ENV_USAGE: os.path.join(target, core.USAGE)})
        result = run._run([core._SHELL, "-c", command], target, env, core.PRODUCER_TIMEOUT)
        if result["status"] != "ok":
            raise ClaimError("producer " + result["status"] + ": " + result["stderr"])
        usage = build._read_usage(target)
        ledger(target, {"event": "oracle", "kind": "producer", "calls": 1,
                        "seconds": result["seconds"], **usage})
    for name, digest in snapshot.items():
        if core._hash_file(core._safe(target, name)) != digest:
            raise ClaimError("producer changed pinned bytes: " + name)
    try:
        furnished = _furnish(target, parsed)
    except ClaimError as exc:
        raise ClaimError("environment: " + str(exc)) from exc
    for step in recipe.gates(parsed):
        outcome = run_gate(step["run"], target, parsed,
                           env={"PATH": furnished + os.pathsep + os.environ.get("PATH", os.defpath)} if furnished else None)
        ledger(target, {"event": "gate", "output": step["output"],
                        "status": outcome["status"], "quarantine": outcome.get("quarantine")})
        if outcome["status"] != "ok":
            raise ClaimError("gate " + step["output"] + " " + outcome["status"] + ": " + outcome.get("stderr", ""))
        expected = core._safe(source, step["output"])
        actual = core._safe(target, step["output"])
        if os.path.exists(expected) and core._hash_file(expected) != core._hash_file(actual):
            raise ClaimError("gate verdict mismatch: " + step["output"])
    return seal(target)


def mutation_score(directory, *, max_mutants=core.MUTANT_CEILING):
    parsed = load_recipe(directory)
    checked = verify(directory)
    if not checked["ok"]:
        raise ClaimError("identity mismatch")
    candidates = []
    for name in recipe.generated_outputs(parsed):
        if not name.endswith(".py"):
            continue
        try:
            with open(core._safe(directory, name), encoding="utf-8") as stream:
                source = stream.read()
        except (OSError, UnicodeError) as exc:
            raise ClaimError(str(exc)) from exc
        candidates += [(name, variant) for variant in mutations._mutants(source)]
    order = mutations._mutant_order(checked["root"], candidates)[:max_mutants]
    killed, survivors = 0, []
    for index, (name, variant) in enumerate(order):
        with tempfile.TemporaryDirectory(prefix="reticuli-mutant-") as room:
            _materialize(directory, room, parsed)
            with open(core._safe(room, name), "w", encoding="utf-8") as stream:
                stream.write(variant)
            all_ok = True
            for gate in recipe.gates(parsed):
                outcome = run_gate(gate["run"], room, parsed)
                if outcome["status"] != "ok":
                    all_ok = False
                    break
            if all_ok:
                survivors.append(index)
            else:
                killed += 1
    result = {"mutants": len(order), "killed": killed,
              "survivors": survivors, "rate": killed / len(order) if order else 0.0}
    core._write_json(os.path.join(directory, core.MUTATION_RESIDUE), result)
    return result


def independence(directory):
    for event in ledger_events(directory):
        if event.get("event") == "producer":
            return {"vendor": event.get("vendor"), "model": event.get("model"),
                    "blind": event.get("blind", False)}
    return {"vendor": None, "model": None, "blind": False}


def _leg(path):
    path = os.fspath(path)
    if os.path.isfile(path):
        doc = record_read(path)
        return {"root": doc["root"], "digest": doc["build_digest"],
                "audited": all(g["status"] == "ok" for g in doc["gates"]),
                "cost": doc.get("cost"), "claim": doc.get("claim"),
                "record": doc, "path": path}
    checked = verify(path)
    judged = audit(path)
    return {"root": checked["root"], "digest": build_digest(path),
            "audited": checked["ok"] and judged["ok"],
            "cost": cost(path), "claim": load_recipe(path)["claim"],
            "path": path}


def crosscheck(m1, m2, m3, *, mutants=None):
    paths = [os.path.realpath(os.fspath(x)) for x in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise ClaimError("three machine paths must be distinct")
    legs = [_leg(path) for path in (m1, m2, m3)]
    one, two, three = legs
    roots = dict(zip(("M1", "M2", "M3"), (leg["root"] for leg in legs)))
    audited = dict(zip(("M1", "M2", "M3"), (leg["audited"] for leg in legs)))
    equivalence = len(set(roots.values())) == 1
    reuse = one["digest"] == two["digest"]
    first, third = one["cost"] or {}, three["cost"] or {}
    shared = next((unit for unit in core.COST_LADDER if unit in first and unit in third), None)
    tol = (one["claim"] or {}).get("tolerance", core.TOLERANCE)
    if shared:
        a, b = first[shared], third[shared]
        comparable = (a == b == 0) or (a > 0 and b > 0 and 1 / tol <= b / a <= tol)
    else:
        comparable = None
    envelope = {}
    obligations = one["claim"]
    for unit, ceiling in (obligations or {}).get("envelope", {}).items():
        actual = third.get(unit)
        envelope[unit] = {"ceiling": ceiling, "measured": actual,
                          "within": actual <= ceiling if actual is not None else None}
    costs = {"comparable": comparable, "unit": shared, "M1": one["cost"],
             "M3": three["cost"], "envelope": envelope}
    rejected, incomplete = [], []
    if not equivalence:
        rejected.append("root")
    if not reuse:
        rejected.append("reuse")
    for label, ok in audited.items():
        if not ok:
            rejected.append("audit " + label)
    if obligations is None:
        incomplete.append("claim obligations")
    else:
        if "tolerance" in obligations and comparable is False:
            rejected.append("tolerance")
        for unit, report in envelope.items():
            if report["within"] is False:
                rejected.append("envelope " + unit)
            elif report["within"] is None:
                incomplete.append("envelope " + unit)
    score = None
    if obligations and "mutation_floor" in obligations:
        if mutants is None or os.path.isfile(os.fspath(m3)):
            incomplete.append("mutation floor")
        else:
            score = mutation_score(m3, max_mutants=mutants)
            score["ok"] = score["rate"] >= obligations["mutation_floor"]
            if not score["ok"]:
                rejected.append("mutation floor")
    verdict = "reject" if rejected else "incomplete" if incomplete else "accept"
    declaration = (three["record"] or {}).get("producer") if three.get("record") else independence(m3)
    if declaration and declaration.get("vendor") and declaration.get("model") and declaration.get("blind"):
        independent = f"declared: {declaration['vendor']}/{declaration['model']}, blind workspace (not proven)"
    else:
        independent = "unestablished"
    return {"satisfied": verdict == "accept", "verdict": verdict,
            "rejected": rejected, "incomplete": incomplete,
            "roots": roots, "audited": audited, "equivalence": equivalence,
            "reuse": reuse, "cost": costs, "mutation_score": score,
            "independence": independent}


def record_proof(m1, m2, m3, *, mutants=None):
    if not os.path.isdir(m1):
        raise ClaimError("proof requires a directory M1")
    records = []
    anchor = os.environ.get(core._ENV_SIGNERS)
    for leg in (m2, m3):
        if os.path.isfile(leg):
            if not anchor:
                raise ClaimError("record proof requires a trust anchor")
            signer = record_signer(leg, anchor)
            if signer is None:
                raise ClaimError("record signature is untrusted")
            records.append({"digest": record_digest(record_read(leg)), "signer": signer})
    result = crosscheck(m1, m2, m3, mutants=mutants)
    result["proof_recorded"] = result["satisfied"]
    if result["satisfied"]:
        manifest = read_manifest(m1)
        manifest["proof"] = {"kind": "crosscheck", "roots": result["roots"],
                             "records": records}
        core._write_json(os.path.join(m1, MANIFEST), manifest)
    return result


def sign_node(root, digest, links):
    payload = {"root": root, "build_digest": digest, "links": sorted(links)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _signed(directory, manifest):
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not manifest.get("proof"):
        return False
    location = os.path.join(directory, SIGN_DIR)
    if not os.path.isdir(location):
        return False
    expected_packet = {"root": manifest["root"],
                       "build_digest": build_digest(directory),
                       "proof": manifest["proof"]}
    for filename in os.listdir(location):
        if not filename.endswith(".sign.json"):
            continue
        statement_path = os.path.join(location, filename)
        packet_path = statement_path[:-len(".sign.json")] + ".packet.json"
        try:
            with open(statement_path, encoding="utf-8") as stream:
                statement = json.load(stream)
            with open(packet_path, encoding="utf-8") as stream:
                packet = json.load(stream)
            if packet != expected_packet or not statement.get("proof_recorded"):
                continue
            pdig = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            if statement.get("packet_digest") != pdig or statement.get("root") != manifest["root"]:
                continue
            with open(anchor, encoding="utf-8") as stream:
                signers = [line.split()[0] for line in stream if line.strip() and not line.lstrip().startswith("#")]
            for principal in signers:
                if build._ssh_verify(open(statement_path, "rb").read(), statement_path + ".sig",
                                     anchor, principal):
                    return True
        except (OSError, ValueError, ClaimError):
            continue
    return False


def phase(directory):
    recipe.recipe_path(directory)
    if not os.path.isfile(os.path.join(directory, MANIFEST)):
        load_recipe(directory)
        return "draft"
    checked = verify(directory)
    if not checked["ok"]:
        return "draft"
    manifest = read_manifest(directory)
    return "signed" if _signed(directory, manifest) else "sealed"
