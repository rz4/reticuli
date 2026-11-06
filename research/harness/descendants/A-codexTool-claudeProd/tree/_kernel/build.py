"""Materialize, re-earn, rebuild — and the signed phase.

`audit` is the only verb that re-earns a verdict.  It deletes nothing and
trusts nothing: a room is materialized from the claim's own declarations, the
gates run there cold and sandboxed, every pinned byte must reproduce, and the
claim itself must still hash to its sealed root.  A stored "passed" is never
evidence.

`rebuild` regrows the generated outputs with a producer.  The producer is the
CALLER's oracle, not a suspect: it runs with the caller's reachability and the
caller's HOME, because a model CLI's credential lives there, while the gate it
feeds faces the jail regardless.  What the caller did not hand over never
arrives; what the caller hands over always does.  A producer that rewrites a
pinned input or a carried file is refused in band rather than allowed to seal
a different, self-consistent claim.

A judging room receives the recipe the ROOT WAS COMPUTED FROM — at format 3
and above the guidance-stripped preimage, written as TOML that still parses
to those tables — so a gate that goes reading its own recipe reads exactly
what the root names, and words outside the identity cannot decide
acceptance.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from .core import (ClaimError, MANIFEST, PRODUCER_TIMEOUT, RECEIPT, SEALED,
                   STORE, _ENV_CLAIM, _ENV_MODEL, _ENV_OUTPUT, _ENV_OUTPUTS,
                   _ENV_REQUEST, _ENV_SIGNERS, _ENV_USAGE, _ENV_VENDOR,
                   _copy_into, _finite, _hash_file, _judging_host, _now,
                   _read_json, _safe, SIGN_DIR, SIGN_NAMESPACE, _write_json)
from . import identity as _identity
from . import recipe as _recipe
from . import run as _run_mod
from . import seal as _seal


# -- writing a recipe back out ---------------------------------------------


def _toml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)        # JSON string escaping is TOML-basic
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {_toml_scalar(v)}"
                                for k, v in value.items()) + " }"
    raise ClaimError(f"a recipe cannot carry {type(value).__name__}")


def _toml_dump(tables: dict) -> str:
    """Emit a recipe as TOML.

    The room's recipe must still BE a recipe: a kernel that wrote the
    preimage's canonical JSON into `reticuli.toml` refused its own file and
    was self-incompatible with the entire migrated era.
    """
    lines = ["[claim]"]
    for key, value in tables.get("claim", {}).items():
        lines.append(f"{json.dumps(key)} = {_toml_scalar(value)}")
    for step in tables.get("step", []) or []:
        lines.append("")
        lines.append("[[step]]")
        for key, value in step.items():
            lines.append(f"{json.dumps(key)} = {_toml_scalar(value)}")
    return "\n".join(lines) + "\n"


def _step_guidance(step: dict):
    """A produce step's hint, under either spelling.

    Guidance reaches a producer over the environment, never through the
    room's recipe: a byte of guidance cannot change whether any realization
    passes.
    """
    return _recipe.step_guidance(step)


# -- materialization --------------------------------------------------------


def _room_recipe(parsed: dict, claimdir: str, room: str) -> None:
    """Lay the recipe into the room — the preimage's tables at format 3+."""
    source = _recipe.recipe_path(claimdir)
    name = os.path.basename(source)
    fmt = _identity._claim_format(parsed)
    target = os.path.join(room, name)
    if fmt < 3:
        _copy_into(source, target)            # the root covers the whole file
        return
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(_toml_dump(_identity._preimage_recipe(parsed)))


def _members(parsed: dict, claimdir: str) -> list:
    """Resolve a format-5 assembly's declared members from the claim's drawer.

    Before any gate runs each member must RECOMPUTE to its declared root: a
    member whose bytes have drifted refuses the fold rather than letting the
    assembly judge a composition it never declared.
    """
    declared = (parsed.get("claim", {}) or {}).get("assembles") or []
    out = []
    for entry in declared:
        name, _, want = entry.partition("@")
        where = os.path.join(claimdir, SEALED, name)
        if not os.path.isdir(where):
            raise ClaimError(
                f"[claim] assembles names {name!r}, which is not in this "
                f"claim's drawer ({SEALED}/{name}) — `ret pull` puts it there")
        checked = _seal.verify(where)
        if checked["recomputed"] != want:
            raise ClaimError(
                f"the member {name!r} is off its declared root "
                f"({checked['recomputed'][:12]}… != {want[:12]}…) — a moved "
                f"member is a different composition, so the fold refuses")
        out.append({"name": name, "root": want, "claim": where})
    return out


def _materialize(parsed: dict, claimdir: str, room: str,
                 produce_from: dict = None, input_from: dict = None,
                 generated: bool = True) -> dict:
    """Build a room holding exactly what the claim declares.

    Gate verdicts are never materialized — they are what the gates earn.
    Carried bytes arrive byte-for-byte; generated bytes arrive only when a
    judging room asks for them, so a rebuilder's room is blind.
    """
    produce_from = dict(produce_from or {})
    input_from = dict(input_from or {})
    os.makedirs(room, exist_ok=True)
    fmt = _identity._claim_format(parsed)
    laid = {"inputs": [], "generated": [], "carried": [], "reused": [],
            "members": []}

    _room_recipe(parsed, claimdir, room)
    for name in _recipe._inputs(parsed, claimdir):
        target = _safe(room, name)
        source = input_from.get(name) or _safe(claimdir, name)
        if not os.path.isfile(source):
            raise ClaimError(f"the declared input {name!r} is missing")
        _copy_into(source, target)
        laid["inputs"].append(name)

    for step in _recipe.produces(parsed):
        name = step["output"]
        cls = _recipe.step_class(step, fmt)
        if cls == "carried":
            source = _safe(claimdir, name)
            if not os.path.isfile(source):
                raise ClaimError(f"the carried file {name!r} is missing")
            _copy_into(source, _safe(room, name))
            laid["carried"].append(name)
            continue
        if cls != "generated":
            continue
        if name in produce_from:
            source = produce_from[name]
            if not os.path.isfile(source):
                raise ClaimError(
                    f"the supplied bytes for {name!r} are missing: {source}")
            _copy_into(source, _safe(room, name))
            laid["reused"].append(name)
            continue
        if not generated:
            continue
        source = _safe(claimdir, name)
        if os.path.isfile(source):
            _copy_into(source, _safe(room, name))
            laid["generated"].append(name)

    own = set(laid["inputs"]) | set(laid["carried"]) | set(laid["generated"]) \
        | set(laid["reused"])
    for member in _members(parsed, claimdir):
        member_recipe = _recipe.load_recipe(member["claim"])
        for name in _recipe.produces(member_recipe):
            out = name["output"]
            source = os.path.join(member["claim"], out)
            if not os.path.isfile(source):
                continue
            if out in own:
                raise ClaimError(
                    f"the member {member['name']!r} and this assembly both "
                    f"own {out!r} — one path, one owner")
            own.add(out)
            _copy_into(source, _safe(room, out))
        drawer = os.path.join(room, SEALED, member["name"])
        if not os.path.exists(drawer):
            shutil.copytree(member["claim"], drawer, symlinks=True,
                            ignore=shutil.ignore_patterns("scratch"))
        laid["members"].append(member["name"])
    return laid


def _compare_pin(claimdir: str, room: str, output: str) -> str:
    """Did the gate's own bytes reproduce what the claim pinned?

    `ok` ran clean and the bytes match; `mismatch` ran clean and the bytes do
    not — a carried verdict, so the claim does not hold.
    """
    want = _safe(claimdir, output)
    got = os.path.join(room, output)
    if not os.path.isfile(got):
        return "mismatch"
    if not os.path.isfile(want):
        return "mismatch"
    try:
        return "ok" if _hash_file(got) == _hash_file(want) else "mismatch"
    except ClaimError:
        return "mismatch"


# -- audit ------------------------------------------------------------------


def audit(claimdir: str, produce_from: dict = None, strict: bool = True,
          input_from: dict = None, **_ignored) -> dict:
    """Re-run every gate cold and sandboxed, and re-check that the claim holds.

    The verdict distinguishes identity damage from a refused criterion,
    because a recipient reads that word to decide whether the BYTES are
    untrustworthy or the CRITERIA said no — opposite responses.  `broken` is
    identity damage; `failed` is a gate that said no on an intact claim.
    """
    started = time.monotonic()
    manifest = _seal.read_manifest(claimdir)
    parsed = _recipe.load_recipe(claimdir)
    name = parsed["claim"]["name"]

    missing = _run_mod.preflight(parsed)
    if missing:
        return {
            "ok": False, "verdict": "environment", "name": name,
            "root": manifest["root"], "recomputed": None,
            "environment": missing, "layers": [], "quarantine": None,
            "elapsed": time.monotonic() - started,
            "gates": [{"output": g["output"], "status": "environment",
                       "quarantine": None, "detail":
                       f"the host lacks {', '.join(missing)}"}
                      for g in _recipe.gates(parsed)],
        }

    checked = _seal.verify(claimdir)
    if not checked["ok"]:
        return {
            "ok": False, "verdict": "broken", "name": name,
            "root": manifest["root"], "recomputed": checked["recomputed"],
            "environment": [], "layers": [], "quarantine": None,
            "changed": checked["changed"],
            "elapsed": time.monotonic() - started,
            "gates": [],
            "detail": "the bytes present do not recompute to the sealed root",
        }

    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        _materialize(parsed, claimdir, room, produce_from=produce_from,
                     input_from=input_from, generated=True)
        furnished = _run_mod.furnish(parsed, room)
        if not furnished["ok"]:
            return {
                "ok": False, "verdict": "environment", "name": name,
                "root": manifest["root"], "recomputed": checked["recomputed"],
                "environment": [parsed["claim"].get("environment")],
                "layers": [], "quarantine": None,
                "elapsed": time.monotonic() - started,
                "gates": [{"output": g["output"], "status": "environment",
                           "quarantine": None, "detail": furnished["reason"]}
                          for g in _recipe.gates(parsed)],
            }
        rows, backend = [], None
        for gate in _recipe.gates(parsed):
            outcome = _run_mod.run_gate(gate["run"], room, parsed,
                                        strict=strict,
                                        venv=furnished["venv"])
            backend = outcome["quarantine"]
            status = outcome["status"]
            if status == "ok":
                status = _compare_pin(claimdir, room, gate["output"])
            rows.append({
                "output": gate["output"], "status": status,
                "quarantine": outcome["quarantine"],
                "detail": (outcome["stderr"] or outcome["stdout"])[-600:],
                "seconds": outcome["seconds"],
            })
        for output in _recipe.pinned_outputs(parsed):
            if any(r["output"] == output for r in rows):
                continue
            if _compare_pin(claimdir, room, output) != "ok":
                rows.append({"output": output, "status": "mismatch",
                             "quarantine": backend,
                             "detail": "a pinned output did not reproduce"})
        ok = bool(rows) and all(r["status"] == "ok" for r in rows)
        if not rows:
            ok = True
        verdict = "earned" if ok else next(
            (r["status"] for r in rows if r["status"] != "ok"), "failed")
        result = {
            "ok": ok, "verdict": verdict, "name": name,
            "root": manifest["root"], "recomputed": checked["recomputed"],
            "environment": [], "layers": [], "gates": rows,
            "quarantine": backend,
            "elapsed": time.monotonic() - started,
        }
        _receipt(claimdir, result)
        return result
    finally:
        shutil.rmtree(room, ignore_errors=True)


def _receipt(claimdir: str, result: dict) -> None:
    """Leave a dated audit receipt as residue — testimony, not a verdict."""
    try:
        _write_json(os.path.join(claimdir, RECEIPT), {
            "when": _now(), "root": result.get("recomputed"),
            "ok": bool(result.get("ok")), "verdict": result.get("verdict"),
            "host": _judging_host(),
            "gates": [{"output": r["output"], "status": r["status"],
                       "quarantine": r.get("quarantine")}
                      for r in result.get("gates", [])],
        })
    except (ClaimError, OSError):
        pass


# -- rebuild ----------------------------------------------------------------


def _read_usage(path: str) -> dict:
    """A producer's self-reported usage, or nothing.

    A non-dict payload is refused rather than totalled: a producer may
    REPORT calls/tokens/usd, and junk is not a report.  `seconds` never
    crosses this boundary — wall-clock is the kernel's own measurement, or
    the cost envelope would be handed a number the producer chose for it.
    """
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items()
            if k in ("usd", "tokens", "calls") and _finite(v)}


def _produce(command: str, room: str, target: str, outputs: list,
             guidance: str, producer_env: dict) -> dict:
    """Invoke the producer once, for one named output.

    The kernel NAMES the target in `RETICULI_OUTPUT` — an absolute path, one
    of the claim's own outputs — and lists them all in `RETICULI_OUTPUTS`,
    whether the claim has one generated output or twenty.  The producer
    inherits the caller's environment apart from the scrub, keeps the
    caller's HOME, and is never confined by this kernel: it needs the
    network, and its output faces the jailed gate regardless.
    """
    usage = os.path.join(room, STORE, "usage.json")
    os.makedirs(os.path.dirname(usage), exist_ok=True)
    if os.path.isfile(usage):
        os.remove(usage)
    env = dict(os.environ)
    env.pop("RETICULI_LEAK_PROBE", None)
    for key in list(env):
        if key.startswith("RETICULI_") and key not in (
                _ENV_MODEL, _ENV_VENDOR, "RETICULI_PRICE",
                "RETICULI_AGENT_TURNS", "RETICULI_JAILED"):
            env.pop(key, None)
    env = _producer_env(env)
    env[_ENV_OUTPUT] = os.path.abspath(os.path.join(room, target)) \
        if target else ""
    env[_ENV_OUTPUTS] = json.dumps(outputs)
    env[_ENV_CLAIM] = os.path.abspath(room)
    env[_ENV_USAGE] = usage
    env.pop(_ENV_REQUEST, None)
    if guidance:
        env[_ENV_REQUEST] = guidance
    if producer_env:
        env.update({k: str(v) for k, v in producer_env.items()})
    started = time.monotonic()
    try:
        done = subprocess.run(command, shell=True, cwd=os.path.abspath(room),
                              env=env, capture_output=True, text=True,
                              timeout=PRODUCER_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise ClaimError(
            f"the producer exceeded {PRODUCER_TIMEOUT}s and was stopped")
    return {"code": done.returncode, "stdout": done.stdout or "",
            "stderr": done.stderr or "", "usage": _read_usage(usage),
            "seconds": time.monotonic() - started}


def _producer_env(env: dict) -> dict:
    """The producer's base environment: the caller's, minus this tool's own
    channel variables.  An inherited CREDENTIAL is not handed over — only
    `producer_env` passes one, and only by the caller's hand."""
    scrubbed = dict(env)
    for key in ("SNEAKED_SECRET",):
        scrubbed.pop(key, None)
    # The scrub's drop-list is the complement of a keep-list: anything the
    # caller did not deliberately hand over must not arrive.  Witnessed in a
    # succession, where a conforming kernel passed an inherited vendor
    # credential through and a metered key was billed.
    keep = {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "SHELL",
            "USER", "LOGNAME", "PWD", "TERM", "PYTHONPATH",
            "SYSTEMROOT", "COMSPEC", _ENV_MODEL, _ENV_VENDOR,
            "RETICULI_PRICE", "RETICULI_AGENT_TURNS"}
    return {k: v for k, v in scrubbed.items() if k in keep}


def _snapshot(parsed: dict, room: str) -> dict:
    """The bytes a producer may not touch: the recipe and the pinned inputs."""
    fmt = _identity._claim_format(parsed)
    snap = {}
    name = os.path.basename(_recipe.recipe_path(room))
    snap[name] = _hash_file(os.path.join(room, name))
    for path in _recipe._inputs(parsed, room):
        target = _safe(room, path)
        if os.path.isfile(target):
            snap[path] = _hash_file(target)
    for step in _recipe.produces(parsed):
        if _recipe.step_class(step, fmt) == "carried":
            target = _safe(room, step["output"])
            if os.path.isfile(target):
                snap[step["output"]] = _hash_file(target)
    return snap


def rebuild(claimdir: str, producer: str, into: str, produce_from: dict = None,
            input_from: dict = None, guidance: bool = True,
            producer_env: dict = None, strict: bool = True,
            **_ignored) -> dict:
    """Regrow the generated outputs in a fresh room until the gates pass."""
    room = os.path.abspath(into)
    if os.path.exists(room) and os.listdir(room):
        raise ClaimError(
            f"{into!r} already holds bytes; a partially built chain is a "
            f"refusal with a reason, never a silent resumption onto bytes "
            f"nobody re-earned")
    parsed = _recipe.load_recipe(claimdir)
    missing = _run_mod.preflight(parsed)
    if missing:
        raise ClaimError(
            f"environment: this host lacks {', '.join(missing)}, so the "
            f"claim cannot be tested here — nothing proven, nothing disproven")
    os.makedirs(room, exist_ok=True)
    fmt = _identity._claim_format(parsed)

    laid = _materialize(parsed, claimdir, room, produce_from=produce_from,
                        input_from=input_from, generated=False)
    for name in laid["reused"]:
        _run_mod.ledger(room, {"event": "reuse", "output": name,
                               "when": _now()})
    _run_mod.ledger(room, dict({"event": "environment"}, **_judging_host(),
                               quarantine=_run_mod.sandbox_backend(),
                               when=_now()))

    snapshot = _snapshot(parsed, room)
    work = [s for s in _recipe.produces(parsed)
            if _recipe.step_class(s, fmt) == "generated"
            and s["output"] not in laid["reused"]]
    outputs = [s["output"] for s in work]

    calls, attempts = 0, 0
    declared = {"vendor": os.environ.get(_ENV_VENDOR),
                "model": os.environ.get(_ENV_MODEL),
                "blind": not laid["generated"]}
    while attempts <= len(outputs) + 1:
        pending = [s for s in work
                   if not os.path.isfile(os.path.join(room, s["output"]))]
        if not pending:
            break
        attempts += 1
        step = pending[0]
        hint = _step_guidance(step) if guidance else None
        outcome = _produce(producer, room, step["output"], outputs, hint,
                           producer_env)
        calls += 1
        event = {"event": "producer", "calls": 1, "output": step["output"],
                 "seconds": outcome["seconds"], "when": _now(),
                 "blind": declared["blind"]}
        if declared["vendor"]:
            event["vendor"] = declared["vendor"]
        if declared["model"]:
            event["model"] = declared["model"]
        event.update(outcome["usage"])
        _run_mod.ledger(room, event)
        if outcome["code"] != 0 and not os.path.isfile(
                os.path.join(room, step["output"])):
            raise ClaimError(
                f"the producer exited {outcome['code']} without writing "
                f"{step['output']!r}: "
                f"{(outcome['stderr'] or outcome['stdout'])[-400:]}")
    if calls == 0 and outputs:
        hint = _step_guidance(work[0]) if guidance else None
        outcome = _produce(producer, room, work[0]["output"], outputs, hint,
                           producer_env)
        calls += 1
        _run_mod.ledger(room, {"event": "producer", "calls": 1,
                               "seconds": outcome["seconds"],
                               "blind": declared["blind"], "when": _now(),
                               **outcome["usage"]})

    for name, before in snapshot.items():
        target = os.path.join(room, name)
        if not os.path.isfile(target) or _hash_file(target) != before:
            raise ClaimError(
                f"the producer rewrote {name!r}, which this claim pins — a "
                f"producer cannot change the question it was asked")

    furnished = _run_mod.furnish(parsed, room)
    if not furnished["ok"]:
        raise ClaimError(f"environment: the room cannot be furnished "
                         f"({furnished['reason']})")
    backend = None
    for gate in _recipe.gates(parsed):
        outcome = _run_mod.run_gate(gate["run"], room, parsed, strict=strict,
                                    venv=furnished["venv"], record=True)
        backend = outcome["quarantine"]
        if outcome["status"] != "ok":
            raise ClaimError(
                f"the rebuilt claim does not hold: gate {gate['output']!r} "
                f"is {outcome['status']} — "
                f"{(outcome['stderr'] or outcome['stdout'])[-400:]}")

    manifest = _seal.seal(room)
    result = dict(manifest)
    result.update({"ok": True, "quarantine": backend or "none",
                   "generated": len(outputs), "calls": calls,
                   "reused": laid["reused"], "into": room})
    return result


# -- the signed phase -------------------------------------------------------


def _ssh_verify(path: str, namespace: str, signers: str, identity: str) -> bool:
    """Does `path.sig` verify for `identity` in `namespace` under the anchor?

    Trust is verifier-relative: with no reachable anchor nothing is
    authorized TO YOU, so an unanchored check can never answer yes.
    """
    if not signers or not os.path.isfile(signers):
        return False
    if not shutil.which("ssh-keygen") or not os.path.isfile(path + ".sig"):
        return False
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", identity,
             "-n", namespace, "-s", path + ".sig"],
            input=payload, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _authorized(claimdir: str, signers: str = None) -> list:
    """Every signing statement that actually authorizes this claim's bytes.

    Four things must hold together, and each was a measured gap: the
    signature verifies under the verifier's own anchor; the STORED packet
    file matches the digest the statement signed (a kernel that reconstructs
    the packet from current state calls a forged review bundle signed); the
    packet names this claim's current root AND build digest (so regenerating
    after signing demotes — the signature froze those bytes); and the packet
    carries a recorded proof.
    """
    anchor = signers or os.environ.get(_ENV_SIGNERS)
    where = os.path.join(claimdir, SIGN_DIR)
    if not os.path.isdir(where):
        return []
    try:
        root = _seal.verify(claimdir)["recomputed"]
        digest = _identity.build_digest(claimdir)
        manifest = _seal.read_manifest(claimdir)
    except ClaimError:
        return []
    out = []
    for name in sorted(os.listdir(where)):
        if not name.endswith(".sign.json"):
            continue
        path = os.path.join(where, name)
        try:
            statement = _read_json(path)
        except ClaimError:
            continue
        if not isinstance(statement, dict):
            continue
        identity = statement.get("identity")
        if not isinstance(identity, str):
            continue
        row = {"identity": identity, "statement": name,
               "verdict": "intact", "packet_holds": False,
               "proof_recorded": bool(statement.get("proof_recorded")),
               "drifted": False}
        anchored = _ssh_verify(path, SIGN_NAMESPACE, anchor, identity)
        row["verdict"] = "authorized" if anchored else "intact"
        packet_name = name[:-len(".sign.json")] + ".packet.json"
        packet_path = os.path.join(where, packet_name)
        packet = None
        if os.path.isfile(packet_path):
            try:
                packet = _read_json(packet_path)
            except ClaimError:
                packet = None
        if isinstance(packet, dict):
            stored = hashlib.sha256(
                json.dumps(packet, sort_keys=True).encode()).hexdigest()
            row["packet_holds"] = stored == statement.get("packet_digest")
            row["drifted"] = packet.get("build_digest") != digest
            row["root_holds"] = packet.get("root") == root
            row["proof_recorded"] = bool(packet.get("proof"))
        else:
            row["root_holds"] = False
        row["signed"] = bool(
            anchored and row["packet_holds"] and not row["drifted"]
            and row.get("root_holds") and row["proof_recorded"]
            and manifest.get("proof")
            and statement.get("root") == root)
        out.append(row)
    return out


def phase(claimdir: str) -> str:
    """`draft` / `sealed` / `signed`.

    A recorded proof alone never advances phase, and neither does a
    signature from an untrusted key: SIGNED means AUTHORIZED by a signer the
    verifier anchors AND PROVEN by a recorded crosscheck, over undrifted
    bytes.  With no reachable anchor every claim is at most `sealed` to you.
    """
    _recipe.load_recipe(claimdir)                 # a wreck refuses in band
    if not os.path.isfile(os.path.join(claimdir, MANIFEST)):
        return "draft"
    _seal.verify(claimdir)                        # refuses a damaged claim
    if any(row["signed"] for row in _authorized(claimdir)):
        return "signed"
    return "sealed"
