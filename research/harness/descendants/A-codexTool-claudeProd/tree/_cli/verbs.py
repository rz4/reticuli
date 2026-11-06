"""One handler per verb: the whole command surface, verb by verb.

Each handler returns an exit code and nothing else — 0 the predicate held,
1 it failed, 2 the invocation was invalid.  That seam is deliberate and
observable: an exit-1 refusal still speaks the `--json` envelope, because
automation's first question is "is this a claim?" and a bare stderr line
there would break the pipe.  An exit-2 refusal does NOT, because the verb
never ran: an invalid invocation stays a plain `ret: <verb>: <fact>` line,
and a tool must not answer a malformed call with a success-shaped document.

Two verbs COMPOSE by default, and both defaults were correct-but-unpinned
once.  `audit` judges the whole chain, with `--shallow` as the explicit,
honest opt-down; `crosscheck` compares composed realizations.  A regrown CLI
wired to the shallow primitive would silently stop the strongest everyday
verdict from composing, and the witness is the usual one: a composed claim
whose component is forged, its own gate blind.
"""
import difflib
import io
import json
import os
import shutil
import sys
import tempfile

from .. import (assess as assess_mod, attest, authoring, feedback, kernel,
                pack as pack_mod, record as record_mod, registry, transfer)
from . import handlers, output, parser, report, statusview, views


def _claim_dir(path: str) -> bool:
    for name in (kernel.RECIPE, kernel.LEGACY_RECIPE):
        if os.path.isfile(os.path.join(path, name)):
            return True
    return False


# -- authoring --------------------------------------------------------------


def _handle_init(args) -> int:
    try:
        data = handlers.init(args.path, no_agent=getattr(
            args, "no_agent", False), agent=getattr(args, "agent", None))
    except kernel.ClaimError as exc:
        output._err("init", exc)
        return 2
    return output._finish("init", data, True, "initialized", args,
                          report._r_init)


def _handle_run(args) -> int:
    """`run` is transparent: the child's exit code, unchanged."""
    command = args.command
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    try:
        return handlers.run(command, getattr(args, "workspace", "."))
    except kernel.ClaimError as exc:
        output._err("run", exc)
        return 1


def _handle_hook(args) -> int:
    """Plumbing: silent, and exit 0 whatever the payload was."""
    try:
        payload = sys.stdin.read()
    except (OSError, ValueError):
        payload = ""
    try:
        handlers.hook(payload, getattr(args, "workspace", "."))
    except kernel.ClaimError:
        pass
    return 0


def _dispatch_pack(args) -> int:
    """The single authoring boundary: session, declared recipe, or flags."""
    accept = getattr(args, "accept", None)
    destination = getattr(args, "output", None) or getattr(args, "into", None)
    if accept and not destination:
        output._err("pack", "--accept names a verdict a session earned, so "
                            "it needs -o <claim> to say where the claim goes")
        return 2
    path = getattr(args, "path", ".") or "."
    if not os.path.isdir(path):
        output._err("pack", f"nothing to pack: no directory at {path!r}")
        return 1
    try:
        if accept:
            data = authoring.build_claim(
                path, accept, destination, name=getattr(args, "name", None),
                claim=None, generated=getattr(args, "generated", None))
            data = {"name": data["name"], "root": data["root"],
                    "claim": destination, "generated": None, "inputs": None,
                    "component": None}
        elif _claim_dir(path):
            data = _seal_declared(path)
        elif getattr(args, "gate", None) or getattr(args, "pytest", False):
            gate = getattr(args, "gate", None) or "python3 -m pytest -q"
            data = pack_mod.pack(
                path, getattr(args, "name", None)
                or os.path.basename(os.path.abspath(path)),
                generated=getattr(args, "generated", None) or ["*.py"],
                inputs=[], gate=gate,
                gate_output=destination or "OK",
                environment=getattr(args, "environment", None),
                carried=getattr(args, "carried", None),
                requires=getattr(args, "requires", None),
                mutation_floor=getattr(args, "mutation_floor", None),
                inputs_manifest=getattr(args, "inputs_manifest", None))
        else:
            output._err("pack", f"nothing to pack: {path!r} holds no recipe, "
                                f"and no --gate or --accept was given")
            return 1
    except kernel.ClaimError as exc:
        return output._refusal("pack", exc, args)
    return output._finish("pack", data, True, "packed", args, report._r_pack)


def _seal_declared(path: str) -> dict:
    """A declared recipe IS the declaration: earn its gates and seal it."""
    parsed = kernel.load_recipe(path)
    vacuous = kernel.vacuous_gates(parsed)
    if vacuous:
        raise kernel.ClaimError(
            f"the gate(s) {', '.join(vacuous)} are vacuous: every file that "
            f"decides them is generated")
    for gate in kernel.gates(parsed):
        outcome = kernel.run_gate(gate["run"], path, parsed)
        if outcome["status"] != "ok":
            raise kernel.ClaimError(
                f"the gate {gate['output']!r} did not earn its verdict "
                f"({outcome['status']}): "
                f"{(outcome['stderr'] or outcome['stdout'])[-400:]}")
    manifest = kernel.seal(path)
    return {"name": manifest["name"], "root": manifest["root"],
            "generated": len(kernel.generated_outputs(parsed)),
            "inputs": len(kernel.declared_inputs(parsed, path)),
            "component": None, "claim": path}


def _dispatch_status(args) -> int:
    """The pure view: read, report, and name the next rung."""
    path = getattr(args, "path", ".") or "."
    if not os.path.isdir(path):
        return output._refusal("status", f"no such directory: {path}", args)
    try:
        if getattr(args, "claims", False):
            rows = registry.claims(path)
            return output._finish(
                "status", {"claims": rows}, True, "claims", args,
                lambda data, a, s: statusview._r_claims(data["claims"], a))
        if getattr(args, "deps", False):
            payload = registry.deps(path)
            return output._finish(
                "status", payload, True, "deps", args,
                lambda data, a, s: statusview._r_deps(data, a))
        if _claim_dir(path):
            view = views._claim_view(path)
            if getattr(args, "tree", False):
                payload = registry.structure(path)
                return output._finish(
                    "status", payload, True, view["status"], args,
                    lambda data, a, s: statusview._r_tree(data, a))
            renderer = statusview._t_status_claim
            if getattr(args, "files", False):
                renderer = statusview._files_claim
            elif getattr(args, "all", False):
                renderer = statusview._ledger_status_claim
            elif getattr(args, "verbose", False):
                renderer = statusview._v_status_claim
            return output._finish(
                "status", view, True, view["status"], args,
                lambda data, a, s: renderer(data, a))
        advice = feedback.advise(path)
        return output._finish(
            "status", advice, True, "draft", args,
            lambda data, a, s: statusview._r_status_draft(data, a))
    except kernel.ClaimError as exc:
        return output._refusal("status", exc, args)


# -- verification -----------------------------------------------------------


def _handle_verify(args) -> int:
    """Identity only.  A passing verify is silent; the exit code is the answer."""
    claim = getattr(args, "claim", ".") or "."
    try:
        data = kernel.verify(claim)
    except kernel.ClaimError as exc:
        return output._refusal("verify", exc, args,
                               hint="ret pack <path> to declare a claim here")
    status = "fresh" if data["ok"] else "broken"
    data = dict(data, phase=views._phase(claim))
    if not data["ok"] and not getattr(args, "json", False):
        moved = ", ".join(data.get("changed") or []) or "some declared byte"
        output._err("verify",
                    f"broken: the bytes present do not recompute to the "
                    f"sealed root ({moved} moved)",
                    hint=f"ret status {claim} --all to see what moved, then "
                         f"restore the declared bytes")
    return output._finish("verify", data, data["ok"], status, args,
                          report._r_verify)


def _dispatch_audit(args) -> int:
    """The judge.  Composed by default; --shallow is the honest opt-down."""
    claim = getattr(args, "claim", ".") or "."
    strict = not getattr(args, "no_strict", False)
    try:
        if getattr(args, "shallow", False):
            data = kernel.audit(claim, strict=strict)
        else:
            data = registry.audit_deep(claim, strict=strict)
        if getattr(args, "mutants", None):
            data = dict(data, mutation_score=kernel.mutation_score(
                claim, max_mutants=args.mutants))
        if getattr(args, "record", None):
            record_mod.write(record_mod.emit(claim), args.record)
    except kernel.ClaimError as exc:
        return output._refusal("audit", exc, args)
    ok, status = bool(data["ok"]), data["verdict"]
    if not ok and not getattr(args, "json", False):
        detail = "; ".join(f"{g['output']}: {g['status']}"
                           for g in data.get("gates") or [])
        detail = detail or "; ".join(
            f"{r['name']}: {r['status']}" for r in data.get("layers") or []
            if not r["ok"])
        output._err("audit", f"{status}: {detail or 'the claim does not hold'}",
                    hint=f"ret status {claim} --all to see what this claim "
                         f"pins")
    return output._finish("audit", data, ok, status, args, report._r_audit)


def _handle_assess(args) -> int:
    claim = getattr(args, "claim", ".") or "."
    try:
        data = assess_mod.assess(claim, mutants=getattr(args, "mutants", None))
    except kernel.ClaimError as exc:
        return output._refusal("assess", exc, args)
    return output._finish("assess", data, True, "measured", args,
                          report._r_assess)


# -- reconstruction ---------------------------------------------------------


def _handle_rebuild(args) -> int:
    """Regrow from the criteria alone; the generated sources are withheld."""
    producer = getattr(args, "producer", None)
    destination = getattr(args, "output", None)
    if not producer:
        output._err("rebuild", "--producer names the program (or the shipped "
                               "adapter) that regrows the implementation")
        return 2
    if not destination:
        output._err("rebuild", "-o names where the rebuilt claim goes")
        return 2
    try:
        command, extra = handlers._expand_producer(producer)
        data = kernel.rebuild(
            getattr(args, "claim"), command, destination,
            guidance=not getattr(args, "without_guidance", False),
            producer_env=extra)
    except kernel.ClaimError as exc:
        return output._refusal("rebuild", exc, args)
    return output._finish("rebuild", data, True, "rebuilt", args,
                          report._r_rebuild)


def _dispatch_crosscheck(args) -> int:
    """The three-machine test, composed, with roles inferred from position."""
    legs = list(getattr(args, "legs", None) or [])
    if len(legs) < 2:
        output._err("crosscheck",
                    "one realization is not a comparison: name at least two "
                    "(a third is M2, the transferred copy)")
        return 2
    scratch, materialized = None, False
    try:
        if len(legs) == 2:
            # A pair gets a REAL byte-copy leg, materialized here and said
            # so — never a silently weakened two-legged test.
            scratch = tempfile.mkdtemp(prefix="reticuli-m2-")
            m2 = os.path.join(scratch, "m2")
            shutil.copytree(legs[0], m2, symlinks=True)
            order, materialized = (legs[0], m2, legs[1]), True
        else:
            order = tuple(legs[:3])
        try:
            data = registry.crosscheck_deep(
                *order, tolerance=getattr(args, "tolerance", None),
                mutants=getattr(args, "mutants", None))
        except kernel.ClaimError as exc:
            return output._refusal("crosscheck", exc, args)
        data = dict(data, m2_materialized=materialized)
        ok, status = bool(data["satisfied"]), data["verdict"]
        if not ok and not getattr(args, "json", False):
            reasons = "; ".join(data["rejected"] + data["incomplete"])
            output._err("crosscheck", f"{status}: {reasons}")
        return output._finish("crosscheck", data, ok, status, args,
                              report._r_crosscheck)
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)


# -- composition and transport ---------------------------------------------


def _handle_pull(args) -> int:
    try:
        data = registry.pull(getattr(args, "claim"),
                             getattr(args, "workspace", "."))
    except kernel.ClaimError as exc:
        return output._refusal("pull", exc, args)
    return output._finish("pull", data, True, "pulled", args, report._r_pull)


def _handle_export(args) -> int:
    archive = getattr(args, "archive", None) or getattr(args, "output", None)
    if not archive:
        output._err("export", "name the archive to write, or -o <archive>")
        return 2
    try:
        data = transfer.export(getattr(args, "claim"), archive,
                               blind=getattr(args, "blind", False))
    except kernel.ClaimError as exc:
        return output._refusal("export", exc, args)
    return output._finish("export", data, True, "exported", args,
                          report._r_export)


def _handle_import(args) -> int:
    try:
        data = transfer.import_(getattr(args, "archive"),
                                getattr(args, "dest", "."))
    except kernel.ClaimError as exc:
        return output._refusal("import", exc, args)
    if not data["ok"] and not getattr(args, "json", False):
        output._err("import", "the received bytes do not recompute to the "
                              "sealed root; nothing was substituted in "
                              "transit, or something was")
    return output._finish("import", data, data["ok"],
                          "fresh" if data["ok"] else "broken", args,
                          report._r_import)


# -- evidence ---------------------------------------------------------------


def _handle_record(args) -> int:
    claim = getattr(args, "claim", ".") or "."
    key = getattr(args, "key", None)
    identity = getattr(args, "identity", None)
    try:
        if getattr(args, "check", False):
            data = attest.check(claim, getattr(args, "signers", None))
            if not data["ok"] and not getattr(args, "json", False):
                output._err("record", "an attestation on this claim does not "
                                      "hold against these bytes")
            return output._finish("record", data, data["ok"],
                                  "verified" if data["ok"] else "refused",
                                  args, report._r_attest_check)
        if key and identity and not getattr(args, "output", None):
            data = attest.attest(claim, key, identity)
            return output._finish("record", data, True, "attested", args,
                                  report._r_attest)
        doc = record_mod.emit(claim)
        data = {"record": doc, "digest": record_mod.digest(doc),
                "root": doc["root"]}
        if getattr(args, "output", None):
            data["path"] = record_mod.write(doc, args.output)
        if getattr(args, "sign", False) or key:
            signing_key = key or os.environ.get(kernel._ENV_KEY)
            if not signing_key:
                output._err("record", "--sign needs an identity: pass --key "
                                      "<key> or set RETICULI_KEY")
                return 1
            if not data.get("path"):
                output._err("record", "-o names the record file to sign")
                return 2
            data["signature"] = record_mod.sign(data["path"], signing_key)
    except kernel.ClaimError as exc:
        return output._refusal("record", exc, args)
    return output._finish("record", data, True, "recorded", args,
                          report._r_record)


def _handle_sign(args) -> int:
    """The human ceremony.  Unanchored, nothing is authorized to you."""
    claim = getattr(args, "claim", ".") or "."
    try:
        if getattr(args, "check", False):
            data = attest.sign_check(claim,
                                     signers=getattr(args, "signers", None))
            if not data["anchored"]:
                return output._refusal(
                    "sign", "no trust anchor is reachable, so nothing is "
                            "authorized to you: unanchored a signature is "
                            "valid for whatever key is embedded in it", args,
                    hint="pass --signers <allowed_signers> or set "
                         "RETICULI_SIGNERS")
            if not data["ok"] and not getattr(args, "json", False):
                output._err("sign", "the authorization does not verify "
                                    "against this anchor and these bytes")
            return output._finish("sign", data, data["ok"],
                                  "authorized" if data["ok"] else "refused",
                                  args, report._r_sign_check)
        key = getattr(args, "key", None)
        if key:
            data = attest.sign(claim, key,
                               getattr(args, "identity", None) or "keyholder")
            return output._finish("sign", data, True, "authorized", args,
                                  report._r_sign)
        data = attest.review_packet(claim)
        return output._finish("sign", data, True, "review", args,
                              report._r_review)
    except kernel.ClaimError as exc:
        return output._refusal("sign", exc, args)


# -- help and plumbing ------------------------------------------------------


def _handle_help(args) -> int:
    if getattr(args, "all_topics", False):
        return parser._help_all()
    topic = getattr(args, "topic", None)
    if topic:
        return parser._help_topic(topic)
    top, _table = parser._parser()
    print(top.format_help(), end="")
    return 0


def _handle_completion(args) -> int:
    return parser._completion(getattr(args, "shell", None) or "bash")


def suggest(verb: str) -> str:
    """The git answer to an unknown verb: name the mistake, offer the near miss."""
    near = difflib.get_close_matches(verb, parser.verbs(), n=3, cutoff=0.5)
    lines = [f"'{verb}' is not a ret command."]
    if near:
        lines.append("The most similar command" +
                     ("s are" if len(near) > 1 else " is"))
        for name in near:
            lines.append(f"    {name}")
    lines.append("See 'ret -h' for the fourteen verbs.")
    return "\n".join(lines)
