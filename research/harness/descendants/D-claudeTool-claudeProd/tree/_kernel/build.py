"""Kernel build: materialize a room, re-earn its verdicts, regrow its bytes.

`audit` trusts nothing: it stages the claim in a fresh room, re-runs every
gate sandboxed, and requires every pinned byte to reproduce. `rebuild` hands
a producer a blind room and seals what it earns. The signed phase lives here
too, because authorization is read from the same bytes an audit judges.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time

from . import identity as _identity
from . import recipe as _recipe
from . import run as _run
from .core import (ClaimError, GUIDANCE_KEYS, MANIFEST, PRODUCER_TIMEOUT, SEALED,
                   SIGN_DIR, STORE, USAGE, _ENV_CLAIM, _ENV_MODEL,
                   _ENV_OUTPUT, _ENV_OUTPUTS, _ENV_REQUEST, _ENV_SIGNERS,
                   _ENV_USAGE, _ENV_VENDOR, _KEEP_ENV, _SHELL, _copy_into,
                   _finite, _hash_file, _judging_host, _read_json, _safe,
                   _sha256_hex)
from .seal import read_manifest, seal, verify


# --------------------------------------------------------------------------
# a very small TOML writer: the room's recipe must still BE a recipe

def _toml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            f"{_toml_key(k)} = {_toml_scalar(v)}"
            for k, v in value.items()) + " }"
    raise ClaimError(f"cannot write {type(value).__name__} into a recipe")


def _toml_key(key: str) -> str:
    plain = all(c.isalnum() or c in "_-" for c in key) and key != ""
    return key if plain else json.dumps(key)


def _toml(document: dict) -> str:
    lines = []
    for key, value in document.items():
        if isinstance(value, dict) or (
                isinstance(value, list) and value
                and all(isinstance(v, dict) for v in value)):
            continue
        lines.append(f"{_toml_key(key)} = {_toml_scalar(value)}")
    for key, value in document.items():
        if isinstance(value, dict):
            lines.append("")
            lines.append(f"[{_toml_key(key)}]")
            for inner, item in value.items():
                lines.append(f"{_toml_key(inner)} = {_toml_scalar(item)}")
    for key, value in document.items():
        if isinstance(value, list) and value \
                and all(isinstance(v, dict) for v in value):
            for element in value:
                lines.append("")
                lines.append(f"[[{_toml_key(key)}]]")
                for inner, item in element.items():
                    lines.append(f"{_toml_key(inner)} = {_toml_scalar(item)}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# materializing a room

def _step_guidance(step: dict):
    """A producer hint, under either spelling."""
    for key in GUIDANCE_KEYS:
        if isinstance(step.get(key), str):
            return step[key]
    return None


def _write_room_recipe(parsed: dict, source: str, room: str) -> None:
    """At format 3 and above the room receives the PREIMAGE recipe, as TOML,
    so a gate that reads its own recipe reads exactly what the root names."""
    name = os.path.basename(_recipe.recipe_path(source))
    target = os.path.join(room, name)
    if _identity._claim_format(parsed) < 3:
        _copy_into(_recipe.recipe_path(source), target)
        return
    os.makedirs(room, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(_toml(_identity._preimage_recipe(parsed)))


def _resolve_member(claim: str, name: str, root: str) -> str:
    """A member resolves from the claim's own drawer and must RECOMPUTE."""
    where = os.path.join(claim, SEALED, name)
    if not os.path.isdir(where):
        raise ClaimError(
            f"[claim] assembles member {name!r} is not in this claim's "
            f"drawer ({SEALED}/{name}); `ret pull` puts it there")
    checked = verify(where)
    if checked["recomputed"] != root:
        raise ClaimError(
            f"assembly member {name!r} has drifted: it recomputes to "
            f"{checked['recomputed'][:16]}..., not the declared "
            f"{root[:16]}... -- a moved member is a different composition")
    return where


def _materialize(parsed: dict, source: str, room: str,
                 produce_from: dict | None = None,
                 input_from: dict | None = None,
                 include_generated: bool = True) -> dict:
    """Lay a claim out in a fresh room. Returns what was supplied.

    Every path crosses the confinement boundary, so a declared name that is a
    symlink, climbs out, or is absolute is refused before a byte moves.
    """
    produce_from = dict(produce_from or {})
    input_from = dict(input_from or {})
    os.makedirs(room, exist_ok=True)
    _write_room_recipe(parsed, source, room)

    for declared in _recipe._inputs(parsed, source):
        target = _safe(room, declared)
        origin = input_from.get(declared) or _safe(source, declared)
        _copy_into(origin, target)

    supplied = []
    for step in _recipe.produces(parsed):
        output = step.get("output")
        if not output:
            continue
        klass = _recipe.step_class(step)
        target = _safe(room, output)
        if klass != "generated":
            _copy_into(_safe(source, output), target)
            continue
        origin, is_supplied = produce_from.get(output), True
        if origin is None and step.get("from"):
            candidate = _safe(source, output)
            origin = candidate if os.path.isfile(candidate) else None
        elif origin is None and include_generated:
            candidate = _safe(source, output)
            origin, is_supplied = (
                candidate if os.path.isfile(candidate) else None), False
        if origin is not None:
            _copy_into(origin, target)
            if is_supplied:
                supplied.append(output)

    members = []
    for name, root in _recipe.members(parsed):
        where = _resolve_member(source, name, root)
        member_recipe = _recipe.load_recipe(where)
        for step in _recipe.produces(member_recipe):
            output = step.get("output")
            origin = _safe(where, output)
            if not os.path.isfile(origin):
                continue
            landing = _safe(room, output)
            if os.path.exists(landing):
                raise ClaimError(
                    f"assembly collision: {output!r} is laid down by member "
                    f"{name!r} and by something else -- one path, one owner")
            _copy_into(origin, landing)
        drawer = os.path.join(room, SEALED, name)
        if not os.path.exists(drawer):
            shutil.copytree(where, drawer, symlinks=False)
        members.append(name)
    return {"supplied": supplied, "members": members}


def _snapshot(parsed: dict, room: str) -> dict:
    """The question a producer may not change: the recipe and every pin."""
    taken = {}
    recipe_file = _recipe.recipe_path(room)
    taken[os.path.basename(recipe_file)] = _hash_file(recipe_file)
    for declared in _recipe._inputs(parsed, room):
        taken[declared] = _hash_file(_safe(room, declared))
    for step in _recipe.produces(parsed):
        if _recipe.step_class(step) in ("carried", "pinned"):
            taken[step["output"]] = _hash_file(_safe(room, step["output"]))
    return taken


def _compare_pin(room: str, claim: str, output: str) -> bool:
    """Did the gate reproduce the bytes the claim pinned?"""
    here, there = _safe(room, output), _safe(claim, output)
    if not os.path.isfile(here) or not os.path.isfile(there):
        return False
    with open(here, "rb") as left, open(there, "rb") as right:
        return left.read() == right.read()


def _read_usage(path: str) -> dict:
    """A producer's self-report. A non-dict payload is refused, not totalled."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (ValueError, OSError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    clean = {}
    for unit in ("usd", "tokens", "calls"):
        value = payload.get(unit)
        if _finite(value) and value >= 0:
            clean[unit] = value
    return clean


# --------------------------------------------------------------------------
# audit: the only verb that re-earns a verdict

def audit(claim: str, produce_from: dict | None = None, strict: bool = True,
          mutants: int | None = None) -> dict:
    """Re-run every gate, cold and sandboxed, against the bytes present."""
    started = time.monotonic()
    parsed = _recipe.load_recipe(claim)
    manifest = read_manifest(claim)
    checked = verify(claim)
    gate_steps = _recipe.gates(parsed)
    result = {"name": manifest["name"], "root": manifest["root"],
              "recomputed": checked["recomputed"], "layers": [],
              "environment": [], "gates": [], "sandbox": None,
              "elapsed": 0.0, "ok": False, "verdict": "broken"}

    missing = _run.preflight(parsed)
    if missing:
        result["environment"] = missing
        result["gates"] = [{"output": g.get("output"), "status": "environment",
                            "quarantine": None, "detail":
                            f"the host lacks {', '.join(missing)}"}
                           for g in gate_steps]
        result["verdict"] = "environment"
        result["elapsed"] = time.monotonic() - started
        return result

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        _materialize(parsed, claim, room, produce_from=produce_from)
        furnished = _run.furnish(parsed, room)
        if not furnished["ok"]:
            result["environment"] = [furnished["reason"] or "unfurnishable"]
            result["gates"] = [
                {"output": g.get("output"), "status": "environment",
                 "quarantine": None, "detail": furnished["reason"]}
                for g in gate_steps]
            result["verdict"] = "environment"
            result["elapsed"] = time.monotonic() - started
            return result
        rows = []
        for step in gate_steps:
            output = step.get("output")
            outcome = _run.run_gate(step["run"], room, parsed,
                                    path_prefix=furnished["path"],
                                    strict=strict)
            status = outcome["status"]
            if status == "ok" and not _compare_pin(room, claim, output):
                status = "mismatch"
            rows.append({"output": output, "status": status,
                         "quarantine": outcome["quarantine"],
                         "detail": (outcome["stderr"]
                                    or outcome["stdout"])[-400:]})
            result["sandbox"] = outcome["quarantine"]
        result["gates"] = rows
    finally:
        shutil.rmtree(room, ignore_errors=True)

    failed = [r for r in result["gates"] if r["status"] != "ok"]
    result["ok"] = checked["ok"] and not failed
    if not checked["ok"]:
        result["verdict"] = "broken"
    elif failed:
        result["verdict"] = failed[0]["status"]
    else:
        result["verdict"] = "earned"
    result["elapsed"] = time.monotonic() - started
    if mutants:
        from .crosscheck import mutation_score
        result["mutation_score"] = mutation_score(claim, max_mutants=mutants)
    return result


# --------------------------------------------------------------------------
# rebuild: a blind room, a producer, and a cold seal

def _producer_env(room: str, extra: dict | None) -> dict:
    """A producer is the caller's oracle: scrubbed, but not confined.

    It keeps the caller's HOME -- the model CLI's credential lives there --
    and it never sees a variable the caller did not hand over.
    """
    env = {name: os.environ[name] for name in _KEEP_ENV if name in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env[_ENV_CLAIM] = os.path.abspath(room)
    for name in (_ENV_VENDOR, _ENV_MODEL):
        if os.environ.get(name):
            env[name] = os.environ[name]
    if extra:
        env.update({k: str(v) for k, v in extra.items() if v is not None})
    return env


def _produce(target: str, producer: str, work: list, guidance_text,
             producer_env: dict | None, usage_path: str) -> tuple:
    """Invoke the producer until every output it was asked for exists.

    The kernel NAMES the target in RETICULI_OUTPUT -- an absolute path, one of
    the claim's own outputs -- and lists them all in RETICULI_OUTPUTS, whether
    the claim has one generated output or twenty.
    """
    started = time.monotonic()
    calls = 0
    rounds = len(work) + 1 if work else 1
    for _ in range(rounds):
        pending = [o for o in work if not os.path.isfile(_safe(target, o))]
        if not pending:
            break
        env = _producer_env(target, producer_env)
        env[_ENV_OUTPUT] = _safe(target, pending[0])
        env[_ENV_OUTPUTS] = json.dumps(work)
        env[_ENV_USAGE] = os.path.abspath(usage_path)
        if guidance_text:
            env[_ENV_REQUEST] = guidance_text
        calls += 1
        try:
            done = subprocess.run(
                [_SHELL, "-c", producer], cwd=target, env=env,
                capture_output=True, text=True,
                timeout=PRODUCER_TIMEOUT, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ClaimError(f"the producer exceeded its bound: {exc}") from exc
        if done.returncode != 0:
            raise ClaimError(
                "the producer failed: "
                + ((done.stderr or done.stdout) or "")[-500:])
    return calls, time.monotonic() - started


def rebuild(claim: str, producer: str, into: str,
            produce_from: dict | None = None, input_from: dict | None = None,
            guidance: bool = True, producer_env: dict | None = None,
            strict: bool = True) -> dict:
    """Regrow the generated outputs until the gates pass; ledger the cost."""
    target = os.path.abspath(into)
    if os.path.isdir(target) and os.listdir(target):
        raise ClaimError(
            f"rebuild target {into!r} already holds bytes; a partially built "
            f"chain is a refusal with a reason, never a silent resumption")
    parsed = _recipe.load_recipe(claim)
    missing = _run.preflight(parsed)
    if missing:
        raise ClaimError(
            f"environment: this host cannot test the claim -- "
            f"missing {', '.join(missing)}")
    os.makedirs(target, exist_ok=True)
    laid = _materialize(parsed, claim, target, produce_from=produce_from,
                        input_from=input_from, include_generated=False)
    taken = _snapshot(parsed, target)

    work = []
    for step in _recipe.produces(parsed):
        if _recipe.step_class(step) != "generated":
            continue
        output = step["output"]
        if os.path.isfile(_safe(target, output)):
            continue
        work.append(output)

    usage_path = os.path.join(target, USAGE)
    os.makedirs(os.path.join(target, STORE), exist_ok=True)
    guidance_text = None
    if guidance:
        for step in _recipe.produces(parsed):
            if step.get("output") in work:
                guidance_text = _step_guidance(step)
                if guidance_text:
                    break

    calls, seconds = _produce(target, producer, work, guidance_text,
                              producer_env, usage_path)

    for name, digest in taken.items():
        try:
            now = _hash_file(_safe(target, name))
        except ClaimError as exc:
            raise ClaimError(
                f"the producer removed {name!r}, which the claim pins: "
                f"{exc}") from exc
        if now != digest:
            raise ClaimError(
                f"the producer rewrote {name!r}, which the claim pins -- a "
                f"producer cannot change the question it is answering")

    backend = _run.sandbox_backend()
    gate_rows = []
    for step in _recipe.gates(parsed):
        outcome = _run.run_gate(step["run"], target, parsed, strict=strict)
        backend = outcome["quarantine"]
        _run.ledger(target, {"event": "gate", "output": step.get("output"),
                             "status": outcome["status"],
                             "quarantine": outcome["quarantine"]})
        gate_rows.append({"output": step.get("output"),
                          "status": outcome["status"],
                          "quarantine": outcome["quarantine"]})
        if outcome["status"] != "ok":
            raise ClaimError(
                f"gate {step.get('output')!r} did not earn its verdict "
                f"({outcome['status']}): "
                + ((outcome["stderr"] or outcome["stdout"]) or "")[-500:])

    for output in laid["supplied"]:
        _run.ledger(target, {"event": "reuse", "output": output})

    manifest = seal(target)
    event = {"event": "producer", "calls": calls, "seconds": round(seconds, 6),
             "blind": not laid["supplied"]}
    if os.environ.get(_ENV_VENDOR):
        event["vendor"] = os.environ[_ENV_VENDOR]
    if os.environ.get(_ENV_MODEL):
        event["model"] = os.environ[_ENV_MODEL]
    event.update(_read_usage(os.path.abspath(usage_path)))
    event["seconds"] = round(seconds, 6)
    _run.ledger(target, event)
    host = _judging_host()
    _run.ledger(target, {"event": "environment", "python": host["python"],
                         "platform": host["platform"],
                         "machine": host["machine"], "quarantine": backend})
    return {"root": manifest["root"], "name": manifest["name"],
            "quarantine": backend, "calls": calls, "gates": gate_rows,
            "into": target}


# --------------------------------------------------------------------------
# the signed phase

def _anchor(signers: str | None = None) -> str | None:
    if signers:
        return signers if os.path.isfile(signers) else None
    from_env = os.environ.get(_ENV_SIGNERS)
    if from_env and os.path.isfile(from_env):
        return from_env
    return None


def _ssh_verify(payload: bytes, signature: str, signers: str,
                namespace: str, identity: str) -> bool:
    if not shutil.which("ssh-keygen"):
        return False
    try:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", identity,
             "-n", namespace, "-s", signature],
            input=payload, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _authorized(claim: str, signers: str | None = None) -> list:
    """Every authorization statement in the claim's signing drawer, judged."""
    from .core import SIGN_NAMESPACE
    drawer = os.path.join(claim, SIGN_DIR)
    if not os.path.isdir(drawer):
        return []
    anchor = _anchor(signers)
    rows = []
    try:
        checked = verify(claim)
        current_root = checked["recomputed"]
        current_build = _identity.build_digest(claim)
    except ClaimError:
        return []
    for name in sorted(os.listdir(drawer)):
        if not name.endswith(".sign.json"):
            continue
        path = os.path.join(drawer, name)
        try:
            statement = _read_json(path, "signing statement")
        except ClaimError:
            continue
        if not isinstance(statement, dict):
            continue
        identity = statement.get("identity") or ""
        signature = path + ".sig"
        intact = os.path.isfile(signature)
        trusted = bool(anchor) and intact and _ssh_verify(
            _read_bytes(path), signature, anchor, SIGN_NAMESPACE, identity)
        packet_path = path[:-len(".sign.json")] + ".packet.json"
        packet, packet_holds = None, False
        if os.path.isfile(packet_path):
            try:
                packet = _read_json(packet_path, "review packet")
            except ClaimError:
                packet = None
        if isinstance(packet, dict):
            digest = _sha256_hex(json.dumps(packet, sort_keys=True).encode())
            packet_holds = digest == statement.get("packet_digest")
        drifted = True
        if isinstance(packet, dict):
            drifted = not (packet.get("root") == current_root
                           and packet.get("build_digest") == current_build)
        rows.append({
            "identity": identity,
            "statement": os.path.relpath(path, claim),
            "intact": intact,
            "anchored": bool(anchor),
            "trusted": trusted,
            "packet_holds": packet_holds,
            "drifted": drifted,
            "names_this_root": statement.get("root") == current_root,
            "proof_recorded": bool(statement.get("proof_recorded")),
            "verdict": "authorized" if trusted else
                       ("intact" if intact else "broken"),
        })
    return rows


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def phase(claim: str) -> str:
    """draft / sealed / signed -- and a refusal for a claim verify refuses."""
    _recipe.load_recipe(claim)
    if not os.path.isfile(os.path.join(claim, MANIFEST)):
        return "draft"
    checked = verify(claim)
    if not checked["ok"]:
        return "sealed"
    manifest = read_manifest(claim)
    if not manifest.get("proof"):
        return "sealed"
    for row in _authorized(claim):
        if row["trusted"] and row["packet_holds"] and row["proof_recorded"] \
                and not row["drifted"] and row["names_this_root"]:
            return "signed"
    return "sealed"
