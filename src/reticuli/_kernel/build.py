"""The kernel's build layer: materialize a blind room, produce into it, re-earn every verdict, and the signed phase."""
import ast
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from .core import (
    _ENV_CLAIM,
    _ENV_MODEL,
    _ENV_OUTPUT,
    _ENV_OUTPUTS,
    _ENV_REQUEST,
    _ENV_SIGNERS,
    _ENV_USAGE,
    _ENV_VENDOR,
    _JAILED,
    _SHELL,
    COST_KEYS,
    MANIFEST,
    PRODUCER_TIMEOUT,
    SIGN_DIR,
    SIGN_NAMESPACE,
    STORE,
    USAGE,
    ClaimError,
    _copy_into,
    _hash_file,
    _judging_host,
    _now,
    _safe,
)
from .identity import (
    _claim_format,
    _preimage_recipe,
    build_digest,
    root,
)
from .recipe import (
    _dump_recipe,
    _inputs,
    gates,
    generated_outputs,
    load_recipe,
    produces,
    recipe_path,
)
from .jail import (  # noqa: F401
    jail_backend,
    jail_receipt,
    jail_wrap,
    require_jail,
)
from .run import (  # noqa: F401
    _ledger_path,
    _run,
    _scrub_env,
    cost,
    furnish,
    gate_timeout,
    ledger,
    preflight,
    run_gate,
    sandbox_backend,
)
from .seal import (  # noqa: F401
    read_manifest,
    seal,
    verify,
)

# ------------------------------------------------------------ the workspace

def _members(claimdir: str, recipe) -> list:
    """The members a format-5 `assembles` names, each held to its declared root.

    An assembly claim's gates judge the COMPOSITION of other claims' shipped
    outputs -- the obligations no per-component criterion can express from
    inside its own room (the import seam, call signatures, what an inherited
    method must do at a boundary). The members resolve from this claim's own
    drawer (`ret pull` puts them there, the same place `from =` components
    live), and each must RECOMPUTE to the root the assembly declares: the
    declaration is the assembly's premise, and a member whose bytes no longer
    hash to it refuses the fold rather than judging a different composition.
    One level only -- a member's own members are its own audit's business.
    """
    declared = (recipe.get("claim") or {}).get("assembles") or []
    out = []
    for entry in declared:
        name, want = entry.split("@")
        found = next(
            (c for c in (os.path.join(claimdir, STORE, store, name)
                         for store in ("sealed", "signed"))
             if os.path.isfile(os.path.join(c, MANIFEST))), None)
        if found is None:
            raise ClaimError(f"assembles: member {name!r} is not registered "
                             "in this claim's drawer -- `ret pull` it first")
        member_recipe = load_recipe(found)
        got = root(member_recipe, found)
        if got != want:
            raise ClaimError(
                f"assembles: member {name!r} recomputes to {got[:12]}… but "
                f"the assembly names {want[:12]}… -- restore the member, or "
                "re-pin the declaration (a moved member is a different "
                "assembly)")
        out.append((name, found, member_recipe))
    return out


def _materialize_members(claimdir: str, recipe, dest: str) -> dict:
    """Lay every member's shipped outputs into the workspace, and the member
    claims themselves into its drawer (so an assembly's room is itself a
    complete assembly claim). Returns {relpath: member} for what arrived --
    a collision, with the assembly's own files or between members, refuses:
    two owners for one path is not a composition."""
    arrived: dict = {}
    for name, memberdir, member_recipe in _members(claimdir, recipe):
        for step in produces(member_recipe):
            rel = step.get("output")
            if not isinstance(rel, str) or not rel:
                continue
            source = _safe(memberdir, rel)
            if not os.path.isfile(source):
                continue          # absent in the member, absent in the room
            if rel in arrived:
                raise ClaimError(f"assembles: {rel} arrives from both "
                                 f"{arrived[rel]!r} and {name!r}")
            target = _safe(dest, rel)
            if os.path.exists(target):
                raise ClaimError(f"assembles: member {name!r} supplies {rel}, "
                                 "which the assembly already carries itself")
            _copy_into(source, target)
            arrived[rel] = name
        drawer = os.path.join(dest, STORE, "sealed", name)
        if not os.path.exists(drawer) \
                and os.path.abspath(memberdir) != os.path.abspath(drawer):
            shutil.copytree(memberdir, drawer, symlinks=False)
    return arrived


def _materialize(claimdir: str, recipe, dest: str, produce_from=None,
                 input_from=None, include_generated=True) -> list:
    """Lay the claim out in a fresh workspace, every path crossing `_safe`.

    Gate outputs are never copied: a gate must re-earn its own output from the
    bytes present, and a stale copy would let a failed gate look answered.
    """
    produce_from = produce_from or {}
    input_from = input_from or {}
    os.makedirs(dest, exist_ok=True)
    # Materialise the recipe under the name it actually has: a claim sealed as
    # claim.toml must arrive in the workspace as claim.toml, or a gate that
    # names it would not find it.  At format 3+ the room receives the recipe
    # the root was computed from -- producer guidance stripped -- because the
    # root deliberately excludes guidance, and a gate that could read it in
    # the room would let words outside the identity decide acceptance: same
    # root, different verdict.  Formats 1 and 2 hash the whole recipe, so
    # their rooms receive the whole file, as ever.
    found = recipe_path(claimdir)
    target = os.path.join(dest, os.path.basename(found))
    if _claim_format(recipe) >= 3:
        with open(target, "w", encoding="utf-8") as f:
            f.write(_dump_recipe(_preimage_recipe(recipe)))
    else:
        _copy_into(found, target)

    for name in _inputs(recipe, claimdir):
        threaded = input_from.get(name)
        source = os.path.abspath(threaded) if threaded else _safe(claimdir, name)
        if not os.path.isfile(source):
            raise ClaimError(f"declared input is missing: {name}")
        _copy_into(source, _safe(dest, name))

    # the composition, before this claim's own outputs: a member file landing
    # on a path the assembly also declares is refused in _materialize_members
    # (inputs are already present) and in the loop below (own produce steps)
    assembled = _materialize_members(claimdir, recipe, dest)

    reused = []
    for step in produces(recipe):
        name = step.get("output")
        if not isinstance(name, str) or not name:
            continue
        if name in assembled:
            raise ClaimError(f"assembles: {name} is supplied by member "
                             f"{assembled[name]!r} and declared by this claim "
                             "too -- one path, one owner")
        supplied = produce_from.get(name)
        if supplied is not None:
            _copy_into(os.path.abspath(supplied), _safe(dest, name))
            reused.append(name)
            continue
        if step.get("class") == "generated" and not include_generated:
            continue                       # the producer will write it
        source = _safe(claimdir, name)      # refuses an output symlinked out
        if os.path.exists(source):
            _copy_into(source, _safe(dest, name))
    return reused


# ---------------------------------------------------------------- the audit

def ownership(claimdir: str) -> list:
    """Pinned criteria that reach a module this claim is supplied, not owns.

    A produce step with `from = "<component>"` hands this claim a file whose
    shipped bytes the owning claim decides: the producer writes its own copy
    here, the gate validates THAT copy, and assembly discards it for the
    owner's. A pinned criterion asserting a property of a supplied module
    therefore constrains a file that never ships -- the obligation is written,
    the gate passes, and nothing holds (the APEIRON campaign's R33, its single
    largest failure class: 11 of 50 upstream-test failures).

    Import-reach over-approximates "constrains" -- importing a supplied Config
    to build a fixture constrains nothing -- so this is a warning lane: each
    crossing names the criterion, the module, and the owning component, and
    nothing here ever refuses. A criterion that ASSERTS belongs in the claim
    that owns the module.
    """
    recipe = load_recipe(claimdir)
    supplied = {}
    for step in produces(recipe):
        name = step.get("output")
        if isinstance(name, str) and name.endswith(".py") and step.get("from"):
            supplied[name] = step["from"]
    if not supplied:
        return []
    crossings = []
    for name in recipe.get("claim", {}).get("inputs", []):
        if not isinstance(name, str) or not name.endswith(".py"):
            continue
        try:
            path = _safe(claimdir, name)
        except ClaimError:
            continue
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read())
        except (OSError, SyntaxError):
            continue        # the gate judges what this lane cannot even parse
        reached = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                reached.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                reached.add(node.module)
                # `from pkg import mod`: the imported name may itself be the
                # supplied module, not an attribute of the package
                reached.update(f"{node.module}.{alias.name}"
                               for alias in node.names if alias.name != "*")
        candidates = set()
        for module in reached:
            base = module.replace(".", "/")
            candidates.update((base + ".py", base + "/__init__.py"))
        for target in sorted(candidates & set(supplied)):
            crossings.append({"criterion": name, "module": target,
                              "component": supplied[target]})
    return crossings


def audit(claimdir: str, produce_from=None, timeout=None, strict=False,
          progress=None) -> dict:
    """THE DEEP CHECK: re-earn every verdict on the bytes actually present.

    Claim-deep, not gate-shallow.  The root must still recompute (a spec
    substituted after sealing is caught even when the gate stays green), and
    every gate is re-run in a fresh workspace: a gate that fails is `failed`, a
    gate that passes but does not reproduce the pinned bytes is a `mismatch` (a
    carried verdict), a host that lacks a declared requirement is
    `environment` -- untested, not disproven.

    `produce_from` substitutes generated bytes, so gates COMPOSE: a dependent's
    shipped code is judged by the component's own claim rather than by the
    component's sealed copy of itself.

    `timeout` tightens the wall-clock ceiling for this audit only, never
    loosening what the claim or the environment already allow.  It exists for
    mutation testing: a mutated loop condition does not terminate, and a run of
    twenty such mutants against the standing ten-minute ceiling is three hours
    of waiting for an answer that was available in a second.

    `progress`, when given, is called as progress(i, total, name) before each
    gate runs — presentation plumbing for a caller that wants to narrate a
    long audit. It is never consulted for anything; a callback that raises is
    the caller's own bug and deliberately not swallowed.
    """
    _judging_host()
    recipe = load_recipe(claimdir)
    manifest = read_manifest(claimdir)
    declared_gates = gates(recipe)
    # advisory, never a verdict: R33 crossings ride every return below so the
    # warning survives even an audit the environment cuts short
    supplied_reach = ownership(claimdir)

    missing = preflight(recipe)
    if missing:
        return {
            "ok": False,
            "claim_ok": None,
            "root": manifest.get("root"),
            "ownership": supplied_reach,
            "environment": missing,
            "gates": [{"output": g.get("output"), "status": "environment",
                       "quarantine": None, "returncode": None, "seconds": None,
                       "detail": f"host lacks {', '.join(missing)}"}
                      for g in declared_gates],
        }

    recomputed = root(recipe, claimdir)
    claim_ok = recomputed == manifest.get("root")

    scratch = tempfile.mkdtemp(prefix="reticuli-audit-")
    try:
        work = os.path.join(scratch, "work")
        _materialize(claimdir, recipe, work, produce_from=produce_from)
        # Furnish the room before judging in it. A room that cannot be
        # furnished is an ENVIRONMENT failure -- the gates were not run, so
        # nothing was proven and nothing was disproven.
        try:
            venv_bin = furnish(recipe, work)
        except ClaimError as exc:
            return {
                "ok": False,
                "claim_ok": claim_ok,
                "root": manifest.get("root"),
                "recomputed": recomputed,
                "ownership": supplied_reach,
                "environment": [str(exc)],
                "gates": [{"output": g.get("output"), "status": "environment",
                           "quarantine": None, "returncode": None,
                           "seconds": None, "detail": str(exc)[-400:]}
                          for g in declared_gates],
            }
        results = []
        for index, step in enumerate(declared_gates, 1):
            name = step.get("output")
            if progress is not None:
                progress(index, len(declared_gates), name)
            # min(), never max(): a caller may tighten this gate's ceiling but
            # must not raise one the claim or the host has already set.
            limit = gate_timeout(recipe)
            if timeout is not None:
                limit = min(limit, float(timeout))
            outcome = run_gate(step["run"], work, recipe, timeout=limit,
                               extra_path=venv_bin, strict=strict)
            entry = {
                "output": name,
                "status": outcome["status"],
                "quarantine": outcome["quarantine"],
                "returncode": outcome["returncode"],
                "seconds": round(outcome["seconds"], 3),
                "detail": "",
            }
            if outcome["status"] == "ok":
                entry.update(_compare_pin(claimdir, work, step))
            else:
                entry["detail"] = (outcome["stderr"] or outcome["stdout"])[-400:]
            results.append(entry)
        return {
            "ok": bool(claim_ok and all(g["status"] == "ok" for g in results)),
            "claim_ok": claim_ok,
            "root": manifest.get("root"),
            "recomputed": recomputed,
            "ownership": supplied_reach,
            "environment": [],
            "gates": results,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _compare_pin(claimdir: str, work: str, step) -> dict:
    """Did the gate reproduce the bytes the claim pins for it?"""
    name = step.get("output")
    if not isinstance(name, str) or not name:
        return {"status": "ok"}
    produced = os.path.join(work, name)
    if not os.path.exists(produced):
        return {"status": "failed", "detail": f"the gate produced no {name}"}
    if step.get("class") == "generated":
        return {"status": "ok"}            # nothing is pinned to compare against
    try:
        pinned_path = _safe(claimdir, name)
    except ClaimError:
        return {"status": "mismatch", "detail": f"{name} escapes the claim"}
    if not os.path.exists(pinned_path):
        return {"status": "mismatch", "detail": f"the claim pins no {name}"}
    try:
        same = _hash_file(pinned_path) == _hash_file(produced)
    except ClaimError as exc:
        return {"status": "mismatch", "detail": str(exc)}
    if same:
        return {"status": "ok"}
    return {"status": "mismatch",
            "detail": f"the gate passed but {name} is not the bytes it produces"}


def phase(claimdir: str) -> str:
    """draft -> sealed -> signed, and only ever for a well-formed claim.

    phase agrees with verify on validity: a claim verify refuses (a corrupt
    recipe or manifest, an input that escapes or is missing) is one phase
    refuses too, rather than answering a positive an auditor would misread.

    SIGNED = AUTHORIZED (a signature from a key this verifier anchors) AND
    PROVEN (a recorded proof) AND COHERENT (the stored packet matches both the
    signature and the bytes on disk).  Trust is verifier-relative.
    """
    recipe = load_recipe(claimdir)
    if not os.path.isfile(os.path.join(claimdir, MANIFEST)):
        return "draft"
    manifest = read_manifest(claimdir)
    recomputed = root(recipe, claimdir)
    if _authorized(claimdir, manifest, recomputed):
        return "signed"
    return "sealed"


def _authorized(claimdir: str, manifest, recomputed: str) -> bool:
    if manifest.get("root") != recomputed:
        return False                       # drifted claim: nothing is authorized
    proof = manifest.get("proof")
    if not proof:
        return False                       # authorized but not proven
    signdir = os.path.join(claimdir, SIGN_DIR)
    if not os.path.isdir(signdir):
        return False
    anchor = os.environ.get(_ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):
        return False                       # no trust anchor: not signed TO YOU
    if not shutil.which("ssh-keygen"):
        return False
    try:
        digest = build_digest(claimdir)
    except ClaimError:
        return False
    for entry in sorted(os.listdir(signdir)):
        if not entry.endswith(".sign.json"):
            continue
        statement_path = os.path.join(signdir, entry)
        signature_path = statement_path + ".sig"
        if not os.path.isfile(signature_path):
            continue
        try:
            with open(statement_path, "rb") as f:
                statement = json.loads(f.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if not isinstance(statement, dict):
            continue
        identity = statement.get("identity")
        if not isinstance(identity, str) or not identity:
            continue
        packet_path = os.path.join(
            signdir, entry[:-len(".sign.json")] + ".packet.json")
        if not os.path.isfile(packet_path):
            continue
        try:
            with open(packet_path, "rb") as f:
                raw = f.read()
            packet = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if not isinstance(packet, dict):
            continue
        # the STORED packet is authoritative: the reviewable bundle on disk is
        # what the signature binds, so a swapped packet demotes even though the
        # live claim is untouched.
        if hashlib.sha256(raw).hexdigest() != statement.get("packet_digest"):
            continue
        if packet.get("root") != manifest.get("root"):
            continue
        if statement.get("root") != manifest.get("root"):
            continue
        # the signature froze the generated bytes: a rebuild after signing drifts
        if packet.get("build_digest") != digest:
            continue
        if not packet.get("proof") or packet.get("proof") != proof:
            continue
        # domain separation: an attestation must not authorize a mint
        if _ssh_verify(anchor, identity, SIGN_NAMESPACE,
                       signature_path, statement_path):
            return True
    return False


def _ssh_verify(anchor: str, identity: str, namespace: str,
                signature: str, data: str) -> bool:
    try:
        with open(data, "rb") as f:
            payload = f.read()
    except OSError:
        return False
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", identity,
             "-n", namespace, "-s", signature],
            input=payload, capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


# --------------------------------------------------------------- the rebuild

def rebuild(src: str, command: str, into: str, produce_from=None,
            input_from=None, guidance=True, producer_env=None,
            jail=False, forbid=(), keep=()) -> dict:
    """Redo the claim in a blind workspace and seal what comes out.

    The workspace carries the claim and its pinned bytes but not its generated
    ones -- the producer writes those from the request alone (unless a
    component supplies them, which is ledgered as a reuse).  Every gate is run;
    the cost is accounted as residue; the verdict environment is ledgered.

    `jail=True` confines the producer (jail.py): the SOURCE CLAIM is always a
    forbidden root -- its materialized generated bytes are the answer sheet,
    and "blind" is otherwise a convention, not an enforcement -- plus whatever
    `forbid` adds (an upstream original, a sibling solution); `keep` carves
    needed roots back out of forbidden ones.  No usable backend refuses: a
    caller that asked for confinement is never silently served without it.
    The touch receipt is ledgered; a BREACH attempt (made AND denied) is
    recorded, not fatal -- rebuild reports, a clone may choose to refuse.
    """
    _judging_host()
    recipe = load_recipe(src)
    missing = preflight(recipe)
    if missing:
        raise ClaimError("environment: this host cannot test the claim, it "
                         f"lacks {', '.join(missing)}")
    if not isinstance(command, str) or not command.strip():
        raise ClaimError("a rebuild needs a producer command")

    dest = os.path.abspath(into)
    if os.path.exists(dest) and (not os.path.isdir(dest) or os.listdir(dest)):
        raise ClaimError(f"the target already holds a claim: {dest}")
    os.makedirs(os.path.join(dest, STORE), exist_ok=True)

    backend = sandbox_backend()
    ledger(dest, {"event": "environment", "when": _now(),
                  "python": platform.python_version(),
                  "implementation": platform.python_implementation(),
                  "platform": sys.platform, "machine": platform.machine(),
                  "quarantine": backend, "shell": _SHELL})

    reused = _materialize(src, recipe, dest, produce_from=produce_from,
                          input_from=input_from, include_generated=False)
    for name in reused:
        ledger(dest, {"event": "reuse", "when": _now(), "output": name,
                      "note": "supplied by a component, not regenerated"})
    for name in input_from or {}:
        ledger(dest, {"event": "thread", "when": _now(), "input": name,
                      "note": "threaded from a rebuilt component"})

    # Furnish before producing: the producer iterates against the gate, and
    # the gate needs the room's environment. A refusal here propagates -- an
    # unfurnishable room cannot host a rebuild.
    venv_bin = furnish(recipe, dest)

    # What the producer must not touch, hashed after materialization (so a
    # caller's deliberate threading is inside the snapshot) and checked before
    # the seal.  A producer that rewrites a pinned input or the recipe does
    # not fail any gate -- it seals to a different, self-consistent root --
    # so without this check "rebuilt" could mean "changed the question".
    found = recipe_path(dest)
    watched = {os.path.basename(found): _hash_file(found)}
    for name in _inputs(recipe, dest):
        watched[name] = _hash_file(_safe(dest, name))
    # Pinned produce outputs are inside the root exactly like inputs, and the
    # room receives their bytes -- so they are criteria the producer may not
    # touch. Left unwatched, a producer that rewrote one sealed a different,
    # self-consistent claim while this verb printed `rebuilt` and exited 0;
    # the crosscheck caught it, but rebuild is the verb people read for
    # success. Gate outputs stay unwatched: a gate re-earns its own output.
    for step in produces(recipe):
        name = step.get("output")
        if (isinstance(name, str) and name
                and step.get("class") not in ("generated", "free")
                and os.path.isfile(_safe(dest, name))):
            watched[name] = _hash_file(_safe(dest, name))
    # An assembled member's files are the member's shipped bytes, anchored by
    # the member root the recipe names -- a producer that rewrote one would
    # hand the gates a composition the assembly never declared, so they are
    # watched exactly like pinned criteria.
    for _, _memberdir, member_recipe in _members(src, recipe):
        for step in produces(member_recipe):
            rel = step.get("output")
            if isinstance(rel, str) and rel \
                    and os.path.isfile(_safe(dest, rel)):
                watched[rel] = _hash_file(_safe(dest, rel))

    confinement = None
    if jail:
        require_jail()
        confinement = jail_wrap(dest, forbid=[src, *forbid], keep=keep)

    receipt = _produce(recipe, dest, command, produce_from,
                       extra_path=venv_bin, guidance=guidance,
                       producer_env=producer_env, confinement=confinement)

    for step in gates(recipe):
        name = step.get("output")
        outcome = run_gate(step["run"], dest, recipe, extra_path=venv_bin)
        ledger(dest, {"event": "gate", "when": _now(), "output": name,
                      "status": outcome["status"],
                      "returncode": outcome["returncode"],
                      "quarantine": outcome["quarantine"],
                      "seconds": round(outcome["seconds"], 3)})
        if outcome["status"] != "ok":
            # the exception, not the traceback: the last line names what went
            # wrong; the full dump would splice a multi-line traceback into the
            # one-line error contract (docs/cli-style.md).
            out = (outcome["stderr"] or outcome["stdout"] or "").strip()
            last = out.splitlines()[-1].strip() if out else \
                f"exit {outcome['returncode']}"
            raise ClaimError(f"gate {name!r} {outcome['status']}: {last}")
        if name and not os.path.exists(os.path.join(dest, name)):
            raise ClaimError(f"gate {name!r} passed but produced no {name}")

    for name, digest in sorted(watched.items()):
        path = _safe(dest, name)
        if not os.path.isfile(path) or _hash_file(path) != digest:
            raise ClaimError(
                f"the producer changed {name}, which is pinned: a rebuild "
                "may write only generated outputs, and changing a criterion "
                "turns reproducing a claim into making a new one")

    manifest = seal(dest)
    # The one comparison a rebuild exists to win, carried in the result so a
    # renderer can refuse to let a mismatch read as success. Internal callers
    # (the self-claim chain) rebuild from staged copies that are not sealed;
    # an unreadable source manifest is their business, not a refusal here.
    try:
        source_root = read_manifest(src)["root"]
    except ClaimError:
        source_root = None
    result = {"root": manifest["root"], "claim": dest, "reused": reused,
              "source_root": source_root,
              "ledger": _ledger_path(dest), "quarantine": backend}
    if receipt:
        result["jail"] = {"backend": receipt["backend"],
                          "verdict": receipt["verdict"],
                          "forbidden": len(receipt["forbidden_roots"])}
    return result


def _step_guidance(step) -> str | None:
    """A step's producer guidance under either key name.  `guidance` is the
    format-3 spelling; `request` is the older one, still read so a claim
    sealed under it keeps guiding its producer."""
    for key in ("guidance", "request"):
        value = step.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _produce(recipe, dest: str, command: str, produce_from,
             extra_path=None, guidance=True, producer_env=None,
             confinement=None):
    """Run the oracle with cwd=dest and account what it cost.

    `confinement` is a generation jail already built by `jail_wrap` -- the
    producer's argv is wrapped in its prefix, its environment says
    RETICULI_JAILED=<backend> so a nested gate reports `inherited` instead of
    dying against the no-nesting rule, and the touch receipt is ledgered
    whether the producer succeeded or not: what it tried to read matters MOST
    on the runs that failed.  Returns the receipt, or None unjailed.

    `guidance=False` is the guidance-blind rebuild: the producer is handed
    the output to write but NOT the hint for how, so a pass measures what the
    acceptance criteria alone carry.  Guidance is not in the format-3 root,
    so a blind rebuild targets the same root a guided one does.

    `producer_env` is what the CALLER deliberately hands the producer over
    the scrub — a vendor credential for a producer the user named, a model
    choice.  The scrub still strips everything inherited: gates never see
    any of this, and nothing arrives that the caller did not place here.
    """
    outputs = generated_outputs(recipe)
    pending = [o for o in outputs
               if not os.path.exists(os.path.join(dest, o))]
    usage = os.path.join(dest, USAGE)
    try:
        os.remove(usage)
    except OSError:
        pass
    extra = {_ENV_CLAIM: dest,
             _ENV_USAGE: usage,                     # ABSOLUTE: `into` may be relative
             _ENV_OUTPUTS: json.dumps(outputs)}
    target = (pending or outputs or [None])[0]
    if target:
        extra[_ENV_OUTPUT] = _safe(dest, target)
        if guidance:
            for step in produces(recipe):
                if step.get("output") == target:
                    hint = _step_guidance(step)
                    if hint is not None:
                        extra[_ENV_REQUEST] = hint
    if producer_env:
        extra.update({k: str(v) for k, v in producer_env.items() if v})
    if confinement:
        extra[_JAILED] = confinement[0]
    env = _scrub_env(extra)
    if extra_path:
        env["PATH"] = extra_path + os.pathsep + env["PATH"]

    prefix = confinement[1] if confinement else []
    outcome = _run([*prefix, _SHELL, "-c", command], cwd=dest, env=env,
                   timeout=PRODUCER_TIMEOUT)
    receipt = None
    if confinement:
        receipt = jail_receipt(confinement[2], outcome["returncode"])
        ledger(dest, {"event": "jail", "when": _now(), **{
            k: receipt[k] for k in ("backend", "room", "forbidden_roots",
                                    "network", "verdict", "content_attempts",
                                    "exit") if k in receipt}})
    event = {"event": "oracle", "when": _now(), "calls": 1,
             "seconds": round(outcome["seconds"], 3),
             "status": outcome["status"]}
    reported = _read_usage(usage)
    for key, value in reported.items():
        if key in COST_KEYS and not isinstance(value, bool) \
                and isinstance(value, (int, float)):
            event[key] = value
    ledger(dest, event)
    # WHO produced this, observed where it can be: a producer that chooses its
    # own model (any CLI driven without an explicit model) is the only party
    # that knows which one ran, and it says so in the usage drop. The env var
    # is a DECLARATION by the caller and stands only as fallback -- recording
    # it as though it were observation is how ten proofs came to name no model
    # at all. `model_source` keeps the difference legible to a later reader
    # instead of flattening observation and declaration into one field.
    def _said(key):
        value = reported.get(key)
        return value if isinstance(value, str) and value else None
    declared_model = os.environ.get(_ENV_MODEL)
    # the producer may say HOW it knows (a CLI that read its own session log
    # knows better than one echoing the flag it passed); absent that, a
    # reported model counts as observed and the environment as declared
    reported_source = _said("model_source")
    producer_event = {"event": "producer", "when": _now(),
                      "vendor": _said("vendor") or os.environ.get(_ENV_VENDOR),
                      "model": _said("model") or declared_model,
                      "model_source": (
                          (reported_source or "observed") if _said("model")
                          else "declared" if declared_model
                          else "unrecorded"),
                      "blind": not bool(produce_from),
                      "guidance": bool(guidance),
                      "command": command}
    for key in ("provider", "producer_version"):
        if _said(key):
            producer_event[key] = _said(key)
    ledger(dest, producer_event)
    if outcome["status"] != "ok":
        raise ClaimError(
            f"the producer {outcome['status']} (rc={outcome['returncode']}): "
            f"{(outcome['stderr'] or outcome['stdout'])[-400:]}")
    return receipt


def _read_usage(path: str) -> dict:
    """A producer's self-reported cost.  Junk pollutes nothing."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}                          # a list is refused, not totalled
    return payload
