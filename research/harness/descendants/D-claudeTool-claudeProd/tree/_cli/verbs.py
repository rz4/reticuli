"""One handler per verb.

Each returns an exit code: 0 the predicate held, 1 it failed, 2 the
invocation was invalid. The composite verbs are `_dispatch_*` -- pack, audit,
status and crosscheck each cover several forms of one concept, and the fold is
deliberate: one concept, one verb.
"""
import os
import shutil
import sys
import tempfile

from .. import assess as assess_mod
from .. import attest
from .. import hooks
from .. import kernel
from .. import pack as pack_mod
from .. import record as record_mod
from .. import registry
from .. import render
from .. import transfer
from .. import feedback
from . import handlers
from . import parser
from . import report
from . import statusview
from . import views
from .output import _Progress, _err, _finish, _line, _refuse, _rel


def _opt(args, name, default=None):
    return getattr(args, name, default)


# --------------------------------------------------------------------------
# plumbing and help

def _handle_help(args) -> int:
    if _opt(args, "every"):
        return parser._help_all()
    return parser._help_topic(_opt(args, "topic"))


def _handle_completion(args) -> int:
    return parser._completion(_opt(args, "shell", "bash"))


def _handle_hook(args) -> int:
    """Plumbing: read one payload, remember it, say nothing.

    Exits 0 whatever arrives -- a handshake that broke an agent's turn would
    be worse than no handshake at all.
    """
    payload = hooks.payload_from(sys.stdin)
    try:
        hooks.event(payload)
    except (kernel.ClaimError, OSError, ValueError):
        pass
    return 0


# --------------------------------------------------------------------------
# authoring

def _handle_init(args) -> int:
    agent = _opt(args, "agent")
    if agent and agent not in ("claude",):
        _err("init", f"unsupported agent {agent!r}; this release wires claude")
        return 2
    try:
        result = handlers.init(_opt(args, "path", "."), agent=agent,
                               no_agent=bool(_opt(args, "no_agent")))
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("init", str(exc), args)
    if _opt(args, "verbose"):
        report._r_init(result, args)
    elif not _opt(args, "json"):
        report._t_init(result)
    return _finish("init", result, True, "initialized", args)


def _handle_run(args) -> int:
    """A transparent boundary: the child's exit code, unchanged."""
    command = _opt(args, "command") or []
    if isinstance(command, (list, tuple)):
        command = " ".join(str(part) for part in command)
    return handlers.run(command, _opt(args, "workspace", "."))


def _dispatch_pack(args) -> int:
    accept = _opt(args, "accept")
    into = _opt(args, "into")
    if accept and not into:
        _err("pack", "--accept names what this session stands behind; say "
                     "where the claim goes with -o DIR")
        return 2
    try:
        result = pack_mod.pack(
            _opt(args, "path", "."), name=_opt(args, "name"),
            generated=_opt(args, "generated"), inputs=_opt(args, "inputs"),
            gate=_opt(args, "gate"), gate_output=_opt(args, "output"),
            accept=accept, into=into, claim=_opt(args, "claim"),
            carried=_opt(args, "carried"), pytest=_opt(args, "pytest"),
            environment=_opt(args, "environment"),
            inputs_manifest=_opt(args, "inputs_manifest"),
            mutation_floor=_opt(args, "mutation_floor"),
            requires=_opt(args, "requires"), by=_opt(args, "by"),
            claim_format=_opt(args, "claim_format"),
            force=bool(_opt(args, "force")))
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("pack", str(exc), args)
    declared = _opt(args, "root")
    if declared and result.get("root") != declared:
        _err("pack", f"this pack minted {result.get('root')}, not the "
                     f"{declared} you named")
        return 1
    if _opt(args, "verbose"):
        report._r_pack(result, args)
    elif not _opt(args, "json"):
        _line(f"packed {result.get('name')} "
              f"{render.short(result.get('root'))}")
    return _finish("pack", result, True, "sealed", args)


# --------------------------------------------------------------------------
# verification

def _handle_verify(args) -> int:
    claim = _opt(args, "claim", ".")
    try:
        result = dict(kernel.verify(claim))
        result["phase"] = views._phase(claim)
    except kernel.ClaimError as exc:
        return _refuse("verify", str(exc), args)
    if not result["ok"]:
        moved = ", ".join(result.get("changed") or []) or "declared bytes"
        if _opt(args, "json"):
            return _finish("verify", result, False, "broken", args)
        _err("verify", f"broken: {moved} no longer hash into the sealed root",
             hint=f"restore the files that moved, or reseal what you meant "
                  f"with `ret pack {_rel(claim)}`")
        return 1
    if _opt(args, "verbose"):
        report._r_verify(result, args)
    return _finish("verify", result, True, "fresh", args)


def _dispatch_audit(args) -> int:
    """The judge. Deep by default; --shallow is the explicit opt-down."""
    claim = _opt(args, "claim", ".")
    strict = not bool(_opt(args, "no_strict"))
    mutants = _opt(args, "mutants")
    try:
        with _Progress(args, "re-earning every verdict cold"):
            if _opt(args, "shallow"):
                result = kernel.audit(claim, strict=strict, mutants=mutants)
            else:
                result = registry.audit_deep(claim, strict=strict,
                                             mutants=mutants)
    except kernel.ClaimError as exc:
        return _refuse("audit", str(exc), args)
    _receipt(claim, result)
    target = _opt(args, "record")
    if target:
        try:
            document = record_mod.emit(claim)
            record_mod.write(document, target)
        except (kernel.ClaimError, OSError) as exc:
            return _refuse("audit", str(exc), args)
    if _opt(args, "verbose"):
        report._r_audit(result, args)
    if not result["ok"]:
        if not _opt(args, "json"):
            detail = [row for row in result.get("gates") or []
                      if row.get("status") != "ok"]
            named = ", ".join(str(row.get("output")) for row in detail)
            _err("audit", f"{result['verdict']}: "
                          f"{named or 'identity does not hold'}",
                 hint=f"`ret status {_rel(claim)}` says what moved")
        return _finish("audit", result, False, result["verdict"], args)
    return _finish("audit", result, True, "earned", args)


def _receipt(claim: str, result: dict) -> None:
    """A dated receipt, so a reader can see when this was last judged."""
    from .._util import write_json
    try:
        write_json(os.path.join(claim, views.RECEIPT),
                   {"root": result.get("recomputed") or result.get("root"),
                    "when": kernel._now(), "verdict": result.get("verdict"),
                    "ok": bool(result.get("ok")),
                    "gates": result.get("gates") or [],
                    "layers": [row.get("name")
                               for row in result.get("layers") or []]})
    except OSError:
        pass


def _handle_assess(args) -> int:
    claim = _opt(args, "claim", ".")
    try:
        result = assess_mod.assess(claim, mutants=_opt(args, "mutants"))
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("assess", str(exc), args)
    if _opt(args, "verbose"):
        report._r_assess(result, args)
    elif not _opt(args, "json"):
        score = result.get("mutation_score") or {}
        _line(f"measured {result.get('name')} "
              f"{len(result.get('measured') or [])} of "
              f"{len(result.get('measured') or []) + len(result.get('not_measured') or [])} "
              f"generated files, kill rate {score.get('rate', 'unmeasured')}")
    return _finish("assess", result, True, "measured", args)


def _dispatch_status(args) -> int:
    """The pure view: it reads and reports, and never executes."""
    path = _opt(args, "path", ".")
    if not os.path.isdir(path):
        return _refuse("status", f"no such directory: {path}", args)
    if _opt(args, "claims"):
        statusview._r_claims(path, args)
        return 0
    if _opt(args, "deps"):
        statusview._r_deps(path, args)
        return 0
    if _opt(args, "tree"):
        statusview._r_tree(path, args)
        return 0
    sealed = os.path.isfile(os.path.join(path, kernel.MANIFEST))
    if sealed:
        try:
            view = views._claim_view(path)
        except kernel.ClaimError as exc:
            return _refuse("status", str(exc), args)
        if _opt(args, "files"):
            statusview._files_claim(path, args)
            return 0
        if _opt(args, "json"):
            return _finish("status", view, True,
                           "fresh" if view["ok"] else "broken", args)
        if _opt(args, "every"):
            statusview._ledger_status_claim(view, args)
        elif _opt(args, "verbose"):
            statusview._v_status_claim(view, args)
        else:
            statusview._t_status_claim(view, args)
        return 0
    try:
        advice = feedback.advise(path)
    except kernel.ClaimError as exc:
        return _refuse("status", str(exc), args)
    if _opt(args, "json"):
        return _finish("status", advice, True, "draft", args)
    statusview._r_status_draft(path, advice, args,
                              every=bool(_opt(args, "every")))
    return 0


# --------------------------------------------------------------------------
# reconstruction

def _handle_rebuild(args) -> int:
    into = _opt(args, "into")
    if not into:
        _err("rebuild", "say where the rebuild goes with -o DIR")
        return 2
    try:
        command, environment = handlers._expand_producer(_opt(args, "producer"))
    except kernel.ClaimError as exc:
        return _refuse("rebuild", str(exc), args)
    try:
        with _Progress(args, "regrowing the generated outputs"):
            result = registry.rebuild_chain(
                _opt(args, "claim"), command, into,
                guidance=not bool(_opt(args, "without_guidance")),
                producer_env=environment)
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("rebuild", str(exc), args)
    if _opt(args, "verbose"):
        report._r_rebuild(result, args)
    elif not _opt(args, "json"):
        _line(f"rebuilt {result.get('root')} into {_rel(result.get('into'))}")
    return _finish("rebuild", result, True, "rebuilt", args)


def _dispatch_crosscheck(args) -> int:
    """Roles are inferred from position, never named: M1, [M2], M3."""
    legs = list(_opt(args, "legs") or [])
    if len(legs) < 2:
        _err("crosscheck", "a comparison needs at least two realizations; "
                           "one directory presented twice proves nothing")
        return 2
    if len(legs) > 3:
        _err("crosscheck", "the test has three machines: M1 [M2] M3")
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
            with _Progress(args, "comparing three realizations"):
                result = registry.crosscheck_deep(
                    legs[0], legs[1], legs[2],
                    mutants=_opt(args, "mutants"),
                    tolerance=_opt(args, "tolerance"))
        except (kernel.ClaimError, OSError) as exc:
            return _refuse("crosscheck", str(exc), args)
        result["m2_materialized"] = materialized
        if _opt(args, "verbose"):
            report._r_crosscheck(result, args)
        if not result["satisfied"]:
            if not _opt(args, "json"):
                reasons = result.get("rejected") or result.get("incomplete")
                _err("crosscheck", f"{result['verdict']}: "
                                   f"{', '.join(str(r) for r in reasons)}")
            return _finish("crosscheck", result, False, result["verdict"],
                           args)
        return _finish("crosscheck", result, True, result["verdict"], args)
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)


# --------------------------------------------------------------------------
# composition and transport

def _handle_pull(args) -> int:
    try:
        result = registry.pull(_opt(args, "claim"),
                               _opt(args, "workspace", "."))
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("pull", str(exc), args)
    if _opt(args, "verbose"):
        report._r_pull(result, args)
    elif not _opt(args, "json"):
        _line(f"pulled {result.get('pulled')} "
              f"{render.short(result.get('root'))}")
    return _finish("pull", result, True, "pulled", args)


def _handle_export(args) -> int:
    target = _opt(args, "out") or _opt(args, "output")
    if not target:
        _err("export", "say where the archive goes: ret export CLAIM PATH")
        return 2
    try:
        result = transfer.export(_opt(args, "claim"), target,
                                 blind=bool(_opt(args, "blind")))
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("export", str(exc), args)
    if _opt(args, "verbose"):
        report._r_export(result, args)
    return _finish("export", result, True, "written", args)


def _handle_import(args) -> int:
    try:
        result = transfer.import_(_opt(args, "archive"),
                                  _opt(args, "into", "."))
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("import", str(exc), args)
    if not result["ok"]:
        if not _opt(args, "json"):
            _err("import", "the received bytes do not recompute to the "
                           "manifest's root")
        return _finish("import", result, False, "broken", args)
    if _opt(args, "verbose"):
        report._r_import(result, args)
    return _finish("import", result, True, "verified", args)


# --------------------------------------------------------------------------
# evidence

def _handle_record(args) -> int:
    claim = _opt(args, "claim", ".")
    if _opt(args, "check"):
        try:
            result = attest.check(claim, _opt(args, "signers"))
        except (kernel.ClaimError, OSError) as exc:
            return _refuse("record", str(exc), args)
        if not result["ok"]:
            if not _opt(args, "json"):
                _err("record", "an attestation here does not hold against "
                               "these bytes")
            return _finish("record", result, False, "broken", args)
        if _opt(args, "verbose"):
            report._r_attest_check(result, args)
        return _finish("record", result, True, "verified", args)

    identity = _opt(args, "identity")
    target = _opt(args, "output")
    if identity and not target:
        key = _opt(args, "key") or os.environ.get("RETICULI_KEY")
        if not key:
            return _refuse("record", "attesting needs a key: --key PATH, or "
                                     "RETICULI_KEY in your environment", args)
        try:
            result = attest.attest(claim, key, identity)
        except (kernel.ClaimError, OSError) as exc:
            return _refuse("record", str(exc), args)
        if _opt(args, "verbose"):
            report._r_attest(result, args)
        return _finish("record", result, True, "attested", args)

    try:
        document = record_mod.emit(claim)
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("record", str(exc), args)
    key = _opt(args, "key")
    if _opt(args, "sign") and not key:
        key = os.environ.get("RETICULI_KEY")
        if not key:
            return _refuse("record", "signing needs an identity: set "
                                     "RETICULI_KEY, or pass --key PATH", args)
    payload = {"record": document, "digest": record_mod.digest(document),
               "root": document["root"], "path": target, "signature": None}
    if target == "-":
        sys.stdout.buffer.write(record_mod.canonical(document))
        sys.stdout.buffer.flush()
    elif target:
        record_mod.write(document, target)
        if key:
            try:
                payload["signature"] = record_mod.sign(target, key)
            except (kernel.ClaimError, OSError) as exc:
                return _refuse("record", str(exc), args)
    if _opt(args, "verbose"):
        report._r_record(payload, args)
    return _finish("record", payload, True, "recorded", args,
                   root=document["root"])


def _handle_sign(args) -> int:
    claim = _opt(args, "claim", ".")
    ws = _opt(args, "workspace")
    if _opt(args, "check"):
        try:
            result = attest.sign_check(claim, ws=ws,
                                       signers=_opt(args, "signers"))
        except (kernel.ClaimError, OSError) as exc:
            return _refuse("sign", str(exc), args)
        if not result["anchored"]:
            return _refuse(
                "sign", "nothing is authorized to you without a trust "
                        "anchor: unanchored, a signature can only be shown "
                        "self-consistent, never attributed", args,
                hint="pass --signers FILE, or set RETICULI_SIGNERS")
        if not result["ok"]:
            if not _opt(args, "json"):
                _err("sign", "no authorization here verifies against your "
                             "anchor")
            return _finish("sign", result, False, "unauthorized", args)
        if _opt(args, "verbose"):
            report._r_sign_check(result, args)
        return _finish("sign", result, True, "authorized", args)

    key = _opt(args, "key")
    if key:
        identity = _opt(args, "identity")
        if not identity:
            return _refuse("sign", "an authorization is accountable: say who "
                                   "is signing with --as IDENTITY", args)
        try:
            result = attest.sign(claim, key, identity, ws=ws)
        except (kernel.ClaimError, OSError) as exc:
            return _refuse("sign", str(exc), args)
        if _opt(args, "verbose"):
            report._r_sign(result, args)
        return _finish("sign", result, True, "authorized", args)

    try:
        packet = attest.review_packet(claim, ws=ws)
    except (kernel.ClaimError, OSError) as exc:
        return _refuse("sign", str(exc), args)
    if _opt(args, "verbose"):
        report._r_review(packet, args)
    elif not _opt(args, "json"):
        _line(f"review {packet['name']} {render.short(packet['root'])}  "
              f"audit={'ok' if packet['audit']['ok'] else packet['audit']['verdict']}"
              f"  proof={'recorded' if packet.get('proof') else 'none'}")
    return _finish("sign", packet, True, "reviewed", args)
