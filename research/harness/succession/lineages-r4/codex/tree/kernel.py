"""Public, standard-library claim kernel."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import tomllib

from ._kernel import core, recipe, identity, seal as sealing, run, build, attest
from ._kernel import crosscheck as checking

ClaimError = core.ClaimError
RECIPE = core.RECIPE
STORE = core.STORE
MANIFEST = core.MANIFEST
LEDGER = core.LEDGER
SIGN_DIR = core.SIGN_DIR
NAMESPACE = core.NAMESPACE
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = 2
_JAILED = core._JAILED
_hash_file = core._hash_file
root = identity.root
build_digest = identity.build_digest
load_recipe = recipe.load_recipe
read_manifest = sealing.read_manifest

def _parsed_for_identity(directory):
    try:
        return recipe.load_recipe(directory)
    except ClaimError as original:
        if "symlink in claim path" not in str(original):
            raise
        with open(recipe.recipe_path(directory), "rb") as stream:
            parsed = tomllib.load(stream)
        for step in parsed.get("step", []):
            if step.get("kind") == "produce" and step.get("class", "generated") == "generated":
                continue
            core._safe(directory, step["output"])
        for name in recipe._inputs(parsed, directory):
            core._safe(directory, name)
        return parsed

def seal(directory):
    parsed = _parsed_for_identity(directory)
    manifest = {"name": parsed["claim"]["name"], "root": identity.root(parsed, directory)}
    core._write_json(os.path.join(directory, MANIFEST), manifest)
    return manifest

def verify(directory):
    manifest = read_manifest(directory)
    parsed = _parsed_for_identity(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": recomputed == manifest["root"], "name": manifest["name"],
            "root": manifest["root"], "recomputed": recomputed}
cost = run.cost
ledger = run.ledger
ledger_events = run.ledger_events
preflight = run.preflight
sign_node = checking.sign_node
gate_deciders = checking.gate_deciders
vacuous_gates = checking.vacuous_gates
crosscheck = checking.crosscheck
record_proof = checking.record_proof
mutation_score = checking.mutation_score
independence = checking.independence
def record_signer(path: str, anchor: str) -> str | None:
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    if not os.path.isfile(signature):
        return None
    found = subprocess.run(["ssh-keygen", "-Y", "find-principals", "-f", anchor,
                            "-s", signature], capture_output=True, text=True)
    for principal in found.stdout.splitlines():
        verified = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", anchor,
                                   "-I", principal, "-n", RECORD_NAMESPACE,
                                   "-s", signature], input=record_canonical(doc),
                                  capture_output=True)
        if verified.returncode == 0:
            return principal
    return None

_original_scrub_env = run._scrub_env
def _scrub_env_with_backend(directory, scratch, backend, extra=None):
    env = _original_scrub_env(directory, scratch, backend, extra)
    if backend in ("seatbelt", "bubblewrap"):
        env[_JAILED] = backend
    return env
run._scrub_env = _scrub_env_with_backend

_original_furnish = run.furnish
def _furnish_in_room(directory, parsed):
    old = os.getcwd()
    try:
        os.chdir(directory)
        return _original_furnish(directory, parsed)
    finally:
        os.chdir(old)
run.furnish = _furnish_in_room


def sandbox(command: str = "true", directory: str = ".") -> tuple[str, str]:
    return command, run.sandbox_backend()


def run_gate(command: str, directory: str, parsed: dict | None,
             *, extra_env: dict[str, str] | None = None) -> dict:
    result = run.run_gate(command, directory, parsed, extra_env=extra_env)
    if result["status"] == "environment" and result.get("missing"):
        result["quarantine"] = None
    return result


def _copy_recipe_room(source: str, destination: str, parsed: dict,
                      *, generated: bool = True,
                      produce_from: dict[str, str] | None = None,
                      input_from: dict[str, str] | None = None) -> None:
    source, destination = os.path.abspath(source), os.path.abspath(destination)
    os.makedirs(destination, exist_ok=True)
    name = os.path.basename(recipe.recipe_path(source))
    core._copy_into(core._safe(source, name), core._safe(destination, name))
    for item in recipe._inputs(parsed, source):
        src = (input_from or {}).get(item, core._safe(source, item))
        core._copy_into(src, core._safe(destination, item))
    for step in recipe.produces(parsed):
        output = step["output"]
        path = core._safe(source, output)
        supplied = (produce_from or {}).get(output)
        if supplied or (os.path.isfile(path) and (generated or
                       step.get("class", "generated") != "generated")):
            core._copy_into(supplied or path, core._safe(destination, output))


def audit(directory: str, *, produce_from: dict[str, str] | None = None,
          shallow: bool = False) -> dict:
    checked = verify(directory)  # malformed identity is a refusal
    parsed = _parsed_for_identity(directory)
    if not checked["ok"]:
        return {"ok": False, "root": checked["root"], "verdict": "mismatch", "gates": []}
    missing = preflight(parsed)
    if missing:
        gates = [{"output": step["output"], "status": "environment", "quarantine": None}
                 for step in recipe.gates(parsed)]
        return {"ok": False, "root": checked["root"], "verdict": "environment",
                "environment": missing, "gates": gates}
    with tempfile.TemporaryDirectory(prefix="reticuli-audit-") as room:
        _copy_recipe_room(directory, room, parsed, produce_from=produce_from)
        if parsed["claim"].get("format", 1) >= 3:
            _strip_guidance(room)
        rows = build._earn_gates(room, directory, parsed)
    okay = all(row["status"] == "ok" for row in rows)
    return {"ok": okay, "root": checked["root"],
            "verdict": "earned" if okay else "carried or broken", "gates": rows}


def _strip_guidance(directory: str) -> None:
    parsed = load_recipe(directory)
    path = recipe.recipe_path(directory)
    with open(path, encoding="utf-8") as stream:
        lines = stream.readlines()
    lines = [line for line in lines if not line.lstrip().startswith(("guidance =", "request ="))]
    with open(path, "w", encoding="utf-8") as stream:
        stream.writelines(lines)


def rebuild(directory: str, producer: str, into: str, *,
            produce_from: dict[str, str] | None = None,
            input_from: dict[str, str] | None = None,
            guidance: bool = True,
            producer_env: dict[str, str] | None = None) -> dict:
    source, target = os.path.abspath(directory), os.path.abspath(into)
    parsed = load_recipe(source)
    if preflight(parsed):
        raise ClaimError("environment requirements missing")
    if os.path.isdir(target) and os.listdir(target):
        raise ClaimError("rebuild target contains bytes")
    if os.path.exists(target) and not os.path.isdir(target):
        raise ClaimError("rebuild target is not a directory")
    if os.path.isfile(os.path.join(source, MANIFEST)) and not verify(source)["ok"]:
        raise ClaimError("source identity mismatch")
    _copy_recipe_room(source, target, parsed, generated=False,
                      produce_from=produce_from, input_from=input_from)
    for output in produce_from or {}:
        ledger(target, {"event": "reuse", "output": output})
    name = os.path.basename(recipe.recipe_path(target))
    pinned = [name, *recipe._inputs(parsed, target)]
    before = {p: _hash_file(core._safe(target, p)) for p in pinned}
    vendor, model = os.environ.get(core._ENV_VENDOR), os.environ.get(core._ENV_MODEL)
    ledger(target, {"event": "environment", "python": os.sys.version.split()[0],
                    "platform": os.sys.platform, "quarantine": run.sandbox_backend()})
    producer_decl = {"event": "producer", "blind": True}
    if vendor: producer_decl["vendor"] = vendor
    if model: producer_decl["model"] = model
    ledger(target, producer_decl)
    env = dict(producer_env or {})
    env[core._ENV_USAGE] = os.path.join(target, core.USAGE)
    produced = build._produce(producer, target, parsed, guidance=guidance, producer_env=env)
    if produced["status"] != "ok":
        raise ClaimError(f"producer {produced['status']}: {produced.get('stderr', '')}")
    after = {p: _hash_file(core._safe(target, p)) for p in pinned}
    if before != after:
        raise ClaimError("producer changed pinned claim bytes")
    if os.path.isfile(os.path.join(source, MANIFEST)):
        rows = build._earn_gates(target, source, parsed)
    else:
        rows = []
        for step in recipe.gates(parsed):
            result = run_gate(step["run"], target, parsed)
            rows.append({"output": step["output"], "status": result["status"],
                         "quarantine": result["quarantine"]})
    for row in rows:
        ledger(target, {"event": "gate", **row})
    if any(row["status"] != "ok" for row in rows):
        raise ClaimError(f"rebuild gates did not reproduce: {rows}")
    manifest = seal(target)
    usage = build._read_usage(target)
    ledger(target, {"event": "oracle", "calls": usage.get("calls", 1),
                    "seconds": produced.get("seconds", 0.0),
                    "quarantine": produced["quarantine"],
                    **{k: v for k, v in usage.items() if k not in ("calls", "seconds")}})
    return {"root": manifest["root"], "build_digest": build_digest(target),
            "gates": rows, "quarantine": produced["quarantine"]}


def phase(directory: str) -> str:
    parsed = load_recipe(directory)
    if not os.path.exists(os.path.join(directory, MANIFEST)):
        return "draft"
    checked = verify(directory)
    if not checked["ok"]:
        return "sealed"
    manifest = read_manifest(directory)
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not manifest.get("proof"):
        return "sealed"
    folder = os.path.join(directory, SIGN_DIR)
    if not os.path.isdir(folder):
        return "sealed"
    for filename in os.listdir(folder):
        if not filename.endswith(".sign.json"):
            continue
        statement = os.path.join(folder, filename)
        signature = statement + ".sig"
        try:
            with open(statement, encoding="utf-8") as stream:
                doc = json.load(stream)
            packet = os.path.join(folder, filename[:-10] + ".packet.json")
            with open(packet, "rb") as stream:
                raw = stream.read()
            payload = json.loads(raw)
            canonical_packet = json.dumps(payload, sort_keys=True).encode()
            if hashlib.sha256(canonical_packet).hexdigest() != doc.get("packet_digest"):
                continue
            if (payload.get("root") != checked["root"] or
                payload.get("build_digest") != build_digest(directory) or
                payload.get("proof") != manifest["proof"]):
                continue
            found = subprocess.run(["ssh-keygen", "-Y", "find-principals", "-f", anchor,
                                    "-s", signature], capture_output=True, text=True)
            for principal in found.stdout.splitlines():
                with open(statement, "rb") as stream:
                    statement_bytes = stream.read()
                valid = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", anchor,
                                        "-I", principal, "-n", SIGN_NAMESPACE,
                                        "-s", signature], input=statement_bytes,
                                       capture_output=True)
                if valid.returncode == 0:
                    return "signed"
        except (OSError, ValueError, KeyError):
            continue
    return "sealed"


def record_validate(doc: object) -> None:
    if not isinstance(doc, dict):
        raise ClaimError("record must be an object")
    version = doc.get("record")
    if type(version) is not int or version not in (1, 2):
        raise ClaimError(f"unsupported record version {version}")
    if version == 1 and "claim" in doc:
        raise ClaimError("version 1 record cannot carry claim obligations")
    if version == 2 and "claim" not in doc:
        raise ClaimError("version 2 record requires claim obligations")
    if version == 2:
        obligations = doc["claim"]
        if not isinstance(obligations, dict) or obligations.keys() - {"tolerance", "envelope", "mutation_floor"}:
            raise ClaimError("invalid record claim obligations")
        for key in ("tolerance", "mutation_floor"):
            if key in obligations and (type(obligations[key]) not in (int, float) or
                                       not math.isfinite(obligations[key]) or obligations[key] < 0):
                raise ClaimError("invalid record " + key)
        if "envelope" in obligations:
            env = obligations["envelope"]
            if not isinstance(env, dict) or not env or any(
                    key not in core.COST_UNITS or type(value) not in (int, float) or
                    not math.isfinite(value) or value <= 0 for key, value in env.items()):
                raise ClaimError("invalid record envelope")
    old = dict(doc)
    old.pop("claim", None)
    old["record"] = 1
    attest.record_validate(old)


def record_canonical(doc: object) -> bytes:
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    try:
        with open(path, "rb") as stream:
            raw = stream.read()
        doc = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ClaimError(f"cannot read record: {exc}") from exc
    record_validate(doc)
    if raw != record_canonical(doc):
        raise ClaimError("record bytes are not canonical")
    return doc
