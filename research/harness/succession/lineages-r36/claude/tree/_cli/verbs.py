"""One handler per verb. `main` routes here and nothing else does.

Every handler returns an exit code and never raises for an ordinary
refusal: the boundary in `dispatch` turns a ClaimError into the one-voice
line, and these handlers turn a FAILED PREDICATE into exit 1 while a
MALFORMED CALL is exit 2 -- refused before the verb runs, so it stays a
stderr sentence with no envelope behind it.

The composed forms are the defaults. `audit` dispatches DEEP, because the
strongest everyday verdict must keep composing, and `--shallow` is the
explicit, spelled opt-down; `crosscheck` likewise. A regrown CLI that wired
these to the shallow primitives would be correct on every fixture with one
layer and silently weaker on every real chain.
"""
import io
import json
import os
import shutil
import sys
import tempfile

from .. import assess as assess_mod
from .. import attest as attest_mod
from .. import authoring
from .. import feedback
from .. import kernel
from .. import pack as pack_mod
from .. import record as record_mod
from .. import registry
from .. import transfer
from . import handlers
from . import output
from . import parser as parser_mod
from . import report
from . import statusview
from . import views


def _strict(args) -> bool:
    """The strict jail is the default; --no-strict is the opt-down."""
    if getattr(args, "strict", False):
        return True
    return not getattr(args, "no_strict", False)


def _claim_arg(args, name: str = "claim") -> str:
    return getattr(args, name, None) or "."


# -- authoring -------------------------------------------------------------
def _handle_init(args) -> int:
    agent = getattr(args, "agent", None)
    if agent is not None and agent not in ("claude",):
        output._err("init", f"unsupported agent: {agent!r} "
                            f"(known: claude)")
        return 2
    try:
        found = handlers.init(args.path, agent=agent,
                              no_agent=getattr(args, "no_agent", False))
    except ValueError as exc:
        output._err("init", f"unsupported agent: {exc}")
        return 2
    return output._finish("init", found, True, found["status"], args,
                          terse=report._t_init(found),
                          renderer=report._r_init)


def _handle_run(args) -> int:
    """The child's exit code, unchanged. A transparent boundary."""
    return handlers.run(args.command, getattr(args, "workspace", "."))


def _dispatch_pack(args) -> int:
    """The single authoring boundary: session, declared recipe, or flags."""
    path = getattr(args, "path", None) or "."
    accept = getattr(args, "accept", None)
    into = getattr(args, "into", None)
    if accept and not into:
        output._err("pack", "--accept names the verdict a session earned, "
                            "so -o must name where the claim is written")
        return 2
    if not os.path.isdir(path):
        return output._refuse("pack", f"nothing to pack: no directory at "
                                      f"{output._rel(path)}", args)
    try:
        if accept:
            found = authoring.build_claim(
                path, accept, into, name=getattr(args, "name", None),
                claim=getattr(args, "inputs", None),
                generated=getattr(args, "generated", None))
        else:
            found = _pack_project(args, path)
    except kernel.ClaimError as exc:
        return output._refuse("pack", str(exc), args)
    root = found.get("root")
    return output._finish("pack", found, True, "packed", args,
                          terse=f"packed {found.get('name')} {root}",
                          root=root, renderer=report._r_pack)


def _pack_project(args, path: str) -> dict:
    """A project with a declared recipe, or one declared by flags."""
    generated = getattr(args, "generated", None)
    gate = getattr(args, "gate", None)
    verdict = getattr(args, "output", None)
    suite = getattr(args, "pytest", None)
    if suite and not gate:
        verdict = verdict or "PYTEST_OK"
        gate = f"python3 -m pytest -q {suite} && printf ok > {verdict}"
    has_recipe = os.path.isfile(os.path.join(path, kernel.RECIPE)) or \
        os.path.isfile(os.path.join(path, kernel.LEGACY_RECIPE))
    if not gate and has_recipe:
        return _seal_declared(path)
    if not gate:
        raise kernel.ClaimError(
            "nothing to pack: this project has no reticuli.toml, and no "
            "--gate (or --pytest) declared one")
    envelope = _parse_envelope(getattr(args, "envelope", None))
    return pack_mod.pack(
        path, name=getattr(args, "name", None), generated=generated,
        inputs=getattr(args, "inputs", None), gate=gate,
        gate_output=verdict, envelope=envelope,
        claim_format=getattr(args, "claim_format", None),
        mutation_floor=getattr(args, "mutation_floor", None),
        requires=getattr(args, "requires", None),
        by=getattr(args, "by", None),
        inputs_manifest=getattr(args, "inputs_manifest", None),
        environment=getattr(args, "environment", None),
        carried=getattr(args, "carried", None))


def _seal_declared(path: str) -> dict:
    """`reticuli.toml` IS the declaration: earn its verdicts, then seal."""
    parsed = kernel.load_recipe(path)
    for gate in kernel.gates(parsed):
        outcome = kernel.run_gate(gate["run"], path, parsed)
        if outcome["status"] != "ok" or not os.path.isfile(
                os.path.join(path, gate["output"])):
            raise kernel.ClaimError(
                f"the gate {gate['output']!r} does not pass here "
                f"({outcome['status']}), so there is no verdict to pin")
    manifest = kernel.seal(path)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"],
            "generated": len(kernel.generated_outputs(parsed)),
            "inputs": len((parsed.get("claim") or {}).get("inputs") or []),
            "component": None, "path": path,
            "format": (parsed.get("claim") or {}).get("format", 1),
            "verdicts": [g["output"] for g in kernel.gates(parsed)]}


def _parse_envelope(text):
    if not text:
        return None
    found = {}
    for piece in str(text).replace(",", " ").split():
        unit, _, value = piece.partition("=")
        try:
            found[unit.strip()] = float(value)
        except ValueError:
            raise kernel.ClaimError(
                f"an envelope ceiling is unit=number, not {piece!r}") \
                from None
    return found or None


def _dispatch_status(args) -> int:
    """The pure view. Reads, reports, executes nothing."""
    path = getattr(args, "path", None) or "."
    if not os.path.isdir(path):
        return output._refuse("status", f"no such directory: "
                                        f"{output._rel(path)}", args)
    if getattr(args, "claims", False):
        rows = registry.claims(path)
        return output._finish("status", {"claims": rows}, True, "claims",
                              args, terse=statusview._r_claims(rows))
    sealed = os.path.isfile(os.path.join(path, kernel.MANIFEST))
    if not sealed:
        advice = feedback.advise(path)
        data = {k: v for k, v in advice.items() if k != "rows"}
        data["rows"] = advice["rows"]
        full = getattr(args, "all", False) or getattr(args, "tree", False)
        return output._finish(
            "status", data, True, "draft", args,
            terse=statusview._r_status_draft(advice, output._rel(path),
                                             full=full))
    view = views._claim_view(path)
    data = {"name": view["name"], "root": view["root"],
            "recomputed": view["recomputed"], "phase": view["phase"],
            "identity": view["identity"], "audited": view["audited"],
            "deciding": view["deciding"], "proof": view["proof"],
            "signatures": view["signatures"], "cost": view["cost"],
            "discovery": view["discovery"], "declared": view["declared"],
            "files": view["files"], "components": view["components"],
            "next": view["next"]}
    if getattr(args, "files", False):
        terse = statusview._files_claim(view)
    elif getattr(args, "tree", False):
        terse = statusview._r_tree(view)
    elif getattr(args, "all", False):
        terse = statusview._ledger_status_claim(view)
    else:
        terse = statusview._t_status_claim(view)
    return output._finish(
        "status", data, True, "fresh" if view["ok"] else "broken", args,
        terse=terse, root=view["root"],
        renderer=lambda _d: statusview._v_status_claim(view))


# -- verification ----------------------------------------------------------
def _handle_verify(args) -> int:
    claim = _claim_arg(args)
    try:
        checked = kernel.verify(claim)
        phase = kernel.phase(claim)
    except kernel.ClaimError as exc:
        return output._refuse("verify", str(exc), args)
    data = {"name": checked["name"], "root": checked["root"],
            "recomputed": checked["recomputed"], "ok": checked["ok"],
            "phase": phase, "changed": checked.get("changed") or []}
    if not checked["ok"]:
        if getattr(args, "json", False):
            return output._finish("verify", data, False, "broken", args,
                                  root=checked["root"])
        moved = ", ".join(data["changed"]) or "some declared file"
        output._err("verify", f"broken: {moved} no longer hashes to what "
                              f"this root names")
        output._warn_block([
            f"hint: restore {moved}, or reseal what you meant with "
            f"`ret pack {output._rel(claim)}`"])
        return 1
    return output._finish("verify", data, True, "fresh", args,
                          root=checked["root"],
                          renderer=report._r_verify)


def _dispatch_audit(args) -> int:
    """Deep by default: a composed claim's components re-earn too."""
    claim = _claim_arg(args)
    strict = _strict(args)
    try:
        if getattr(args, "shallow", False):
            result = dict(kernel.audit(claim, strict=strict,
                                       mutants=getattr(args, "mutants",
                                                       None)))
            result.setdefault("layers", [])
        else:
            result = dict(registry.audit_deep(
                claim, reuse=getattr(args, "reuse", False), strict=strict))
            if getattr(args, "mutants", None):
                result["mutation_score"] = kernel.mutation_score(
                    claim, max_mutants=args.mutants)
        if getattr(args, "record", None):
            record_mod.write(record_mod.emit(claim), args.record)
    except kernel.ClaimError as exc:
        return output._refuse("audit", str(exc), args)
    ok = bool(result["ok"])
    if not ok and not getattr(args, "json", False):
        detail = ", ".join(
            f"{g['output']} {g['status']}" for g in result.get("gates") or []
            if g.get("status") != "ok")
        broken = ", ".join(r["name"] for r in result.get("layers") or []
                           if not r.get("ok"))
        output._err("audit", f"{result['verdict']}: "
                             + (detail or broken or "the claim does not "
                                                   "hold on these bytes"))
        if result["verdict"] == "broken":
            output._warn_block([
                "hint: identity damage, not a failing test: the bytes "
                "present are a different claim"])
        return 1
    return output._finish("audit", result, ok, result["verdict"], args,
                          root=result.get("root"),
                          renderer=report._r_audit)


def _handle_assess(args) -> int:
    claim = _claim_arg(args)
    try:
        found = assess_mod.assess(claim,
                                  mutants=getattr(args, "mutants", None))
    except kernel.ClaimError as exc:
        return output._refuse("assess", str(exc), args)
    score = found.get("mutation_score") or {}
    rate = "unmeasured" if score.get("rate") is None \
        else f"{score['rate']:.2f}"
    terse = (f"measured {found['name']}: {len(found['measured'])} measured, "
             f"{len(found['not_measured'])} not measured, "
             f"{len(found['not_applicable'])} not applicable; "
             f"mutation {rate}")
    return output._finish("assess", found, True, "measured", args,
                          terse=terse, root=found.get("root"),
                          renderer=report._r_assess)


# -- reconstruction --------------------------------------------------------
def _handle_rebuild(args) -> int:
    claim = _claim_arg(args)
    into = getattr(args, "into", None)
    if not into:
        output._err("rebuild", "-o must name where the rebuilt claim goes")
        return 2
    named = getattr(args, "producer", None)
    if not named:
        output._err("rebuild", "--producer must name a producer: a shipped "
                               "adapter by name, or any program")
        return 2
    try:
        command, env = handlers._expand_producer(named)
        found = dict(registry.rebuild_chain(
            claim, command, into, producer_env=env,
            guidance=not getattr(args, "without_guidance", False)))
    except kernel.ClaimError as exc:
        return output._refuse("rebuild", str(exc), args)
    return output._finish("rebuild", found, True, "rebuilt", args,
                          terse=f"rebuilt {found.get('name')} "
                                f"{found.get('root')}",
                          root=found.get("root"),
                          renderer=report._r_rebuild)


def _dispatch_crosscheck(args) -> int:
    """Composed by default, and honest about a materialized M2."""
    legs = list(getattr(args, "legs", None) or [])
    if len(legs) < 2:
        output._err("crosscheck", "one realization is not a comparison: "
                                  "name two or three machines")
        return 2
    if len(legs) > 3:
        output._err("crosscheck", "the test has three machines, not "
                                  f"{len(legs)}")
        return 2
    scratch, materialized = None, False
    try:
        if len(legs) == 2:
            scratch = tempfile.mkdtemp(prefix="reticuli-m2-")
            copy = os.path.join(scratch, "m2")
            shutil.copytree(legs[0], copy, symlinks=False)
            legs = [legs[0], copy, legs[1]]
            materialized = True
        try:
            result = dict(registry.crosscheck_deep(
                legs[0], legs[1], legs[2],
                tolerance=getattr(args, "tolerance", None),
                mutants=getattr(args, "mutants", None)))
        except kernel.ClaimError as exc:
            return output._refuse("crosscheck", str(exc), args)
        result["m2_materialized"] = materialized
        ok = bool(result["satisfied"])
        if not ok and not getattr(args, "json", False):
            why = ", ".join(result.get("rejected") or
                            result.get("incomplete") or [])
            output._err("crosscheck", f"{result['verdict']}: {why}")
            return 1
        return output._finish("crosscheck", result, ok, result["verdict"],
                              args, renderer=report._r_crosscheck)
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)


# -- transport -------------------------------------------------------------
def _handle_export(args) -> int:
    archive = getattr(args, "archive", None) or getattr(args, "output", None)
    if not archive:
        output._err("export", "name the archive to write, or -o -")
        return 2
    try:
        found = transfer.export(args.claim, archive,
                                blind=getattr(args, "blind", False))
    except kernel.ClaimError as exc:
        return output._refuse("export", str(exc), args)
    if archive == "-":
        return 0
    return output._finish("export", found, True, "exported", args,
                          renderer=report._r_export)


def _handle_import(args) -> int:
    destination = getattr(args, "destination", None)
    if not destination:
        output._err("import", "name the directory to restore into")
        return 2
    try:
        found = transfer.import_(args.archive, destination)
    except kernel.ClaimError as exc:
        return output._refuse("import", str(exc), args)
    if not found["ok"]:
        return output._refuse(
            "import", f"the received bytes recompute to "
                      f"{found['recomputed'][:12]}, not the "
                      f"{found['root'][:12]} the manifest names", args)
    return output._finish("import", found, True, "imported", args,
                          root=found["root"], renderer=report._r_import)


def _handle_pull(args) -> int:
    try:
        found = registry.pull(args.claim,
                              getattr(args, "workspace", None) or ".")
    except kernel.ClaimError as exc:
        return output._refuse("pull", str(exc), args)
    return output._finish("pull", found, True, "pulled", args,
                          terse=f"pulled {found['name']} "
                                f"{found['root'][:12]}",
                          root=found["root"], renderer=report._r_pull)


# -- evidence --------------------------------------------------------------
def _handle_record(args) -> int:
    claim = _claim_arg(args)
    signers = getattr(args, "signers", None)
    key = getattr(args, "key", None)
    identity = getattr(args, "identity", None)
    destination = getattr(args, "output", None)
    try:
        if getattr(args, "check", False):
            found = attest_mod.check(claim, signers)
            if not found["ok"]:
                return output._refuse(
                    "record", "the attestations on this claim do not hold "
                              "against the bytes present", args)
            return output._finish("record", found, True, "intact", args,
                                  renderer=report._r_attest_check)
        if key and not destination:
            found = attest_mod.attest(claim, key, identity or "anonymous")
            return output._finish("record", found, True, "attested", args,
                                  root=found["root"],
                                  renderer=report._r_attest)
        doc = record_mod.emit(claim)
        data = {"record": doc, "digest": record_mod.digest(doc),
                "root": doc["root"], "path": destination, "signed": False,
                "signer": None}
        if destination:
            record_mod.write(doc, destination)
        if getattr(args, "sign", False) and not key:
            key = os.environ.get("RETICULI_KEY")
            if not key:
                return output._refuse(
                    "record", "--sign needs an identity and none is "
                              "configured: name one with --key or set "
                              "RETICULI_KEY", args)
        if key:
            if not destination or destination == "-":
                return output._refuse(
                    "record", "a signature covers a file's bytes, so -o "
                              "must name the record to sign", args)
            record_mod.sign(destination, key)
            data["signed"] = True
            data["signer"] = record_mod.signer(destination, signers)
    except kernel.ClaimError as exc:
        return output._refuse("record", str(exc), args)
    return output._finish("record", data, True, "recorded", args,
                          root=data["root"], renderer=report._r_record)


def _handle_sign(args) -> int:
    claim = _claim_arg(args)
    ws = getattr(args, "workspace", None)
    signers = getattr(args, "signers", None)
    try:
        if getattr(args, "check", False):
            found = attest_mod.sign_check(claim, ws=ws, signers=signers)
            if not found["anchored"]:
                return output._refuse(
                    "sign", "no trust anchor is reachable, so nothing is "
                            "authorized to you: name one with --signers or "
                            "set RETICULI_SIGNERS", args,
                    hint="unanchored, a signature can only be shown "
                         "self-consistent -- which says a statement was "
                         "signed, never whose it is")
            if not found["ok"]:
                return output._refuse(
                    "sign", "the authorizations on this claim do not verify "
                            "against your anchor", args)
            return output._finish("sign", found, True, "authorized", args,
                                  renderer=report._r_sign_check)
        key = getattr(args, "key", None)
        if key:
            found = attest_mod.sign(claim, key,
                                    getattr(args, "identity", None)
                                    or "anonymous", ws=ws)
            return output._finish("sign", found, True, "authorized", args,
                                  root=found["root"],
                                  renderer=report._r_sign)
        packet = attest_mod.review_packet(claim, ws=ws)
    except kernel.ClaimError as exc:
        return output._refuse("sign", str(exc), args)
    audit = packet.get("audit") or {}
    terse = (f"review {packet.get('name')} {packet.get('root')[:12]}: "
             f"audit {audit.get('verdict')}, sign_root "
             f"{packet.get('sign_root')[:12]}, proof "
             f"{'recorded' if packet.get('proof') else 'none'}")
    return output._finish("sign", packet, True, "review", args, terse=terse,
                          root=packet.get("root"),
                          renderer=report._r_review)


# -- plumbing --------------------------------------------------------------
def _handle_hook(args) -> int:
    """A harness must never be broken by its own instrumentation."""
    from .. import hooks
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError, AttributeError):
        return 0
    if isinstance(payload, dict):
        payload.setdefault("cwd", getattr(args, "workspace", ".") or ".")
        if getattr(args, "workspace", None):
            payload["cwd"] = args.workspace
        try:
            hooks.event(payload)
        except Exception:                 # never break the harness
            return 0
    return 0


def _handle_help(args) -> int:
    if getattr(args, "everything", False):
        return parser_mod._help_all()
    topic = getattr(args, "topic", None)
    if not topic:
        top, _sub = parser_mod._parser()
        top.print_help()
        return 0
    code = parser_mod._help_topic(topic)
    if code:
        output._err("help", f"no help topic {topic!r}; `ret help -a` lists "
                            f"everything")
        return 2
    return 0


def _handle_completion(args) -> int:
    return parser_mod._completion(getattr(args, "shell", None) or "bash")
