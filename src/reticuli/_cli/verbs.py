"""ret command line — the verbs layer: the verb handlers and the composite
dispatches (pack/audit/status/crosscheck). main() routes to these."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

from .. import assess as assess_mod
from .. import attest as attest_mod
from .. import authoring as authoring_mod
from .. import feedback as feedback_mod
from .. import hooks as hooks_mod
from .. import kernel
from .. import pack as pack_mod
from .. import record as record_mod
from .. import registry as registry_mod
from .. import reuse as reuse_mod
from .. import transfer as transfer_mod
from ..render import duration, paint, short
from .handlers import (
    _expand_producer,
    init,
    run,
)
from .output import (
    _confirm,
    _err,
    _finish,
    _line,
    _Progress,
    _rel,
    _warn_block,
)
from .parser import (  # noqa: F401
    _FULL_HELP,
    ALIASES,
    _completion,
    _help_all,
    _help_topic,
    _parser,
    verbs,
)
from .report import (
    _r_assess,
    _r_attest,
    _r_attest_check,
    _r_audit,
    _r_crosscheck,
    _r_export,
    _r_import,
    _r_init,
    _r_pack,
    _r_pull,
    _r_rebuild,
    _r_record,
    _r_review,
    _r_seal,
    _r_sign,
    _r_sign_check,
    _r_verify,
    _t_init,
)
from .statusview import (
    _files_claim,
    _ledger_status_claim,
    _r_claims,
    _r_deps,
    _r_status_draft,
    _r_structure,
    _r_tree,
    _t_status_claim,
    _v_status_claim,
)
from .views import (
    _claim_view,
    _gate_ok,
    _phase,
    _verdict,
    _verified,
)


def _handle_help(args) -> int:
    p, _ = _parser()
    if args.all:
        return _help_all()
    if args.topic:
        return _help_topic(args.topic)
    print(p.format_help())
    return 0


def _handle_init(args) -> int:
    if args.agent not in (None, "claude", "generic"):
        # a value the grammar does not know is an invalid invocation
        print(f"ret: init: unsupported agent {args.agent!r} "
              "(supported: claude, generic)", file=sys.stderr)
        return 2
    r = init(args.project, agent=args.agent, no_agent=args.no_agent)
    _finish("init", r, True, "initialized", args, _r_init, _t_init)
    return 0


def _handle_completion(args) -> int:
    return _completion(args.shell)


def _handle_hook(args) -> int:
    hooks_mod.consume(args.workspace)   # silent: hook stdout can leak into the agent
    return 0


# `_handle_hooks` (the standalone installer verb) was retired 2026-09-22:
# `ret init` already wires the agent via hooks_mod.install, and init is
# idempotent, so re-running it re-wires. hooks_mod.install stays; the verb does not.


def _handle_run(args) -> int:
    cmd = " ".join(args.command)
    if not cmd.strip():
        print("ret: run: needs a command", file=sys.stderr)
        return 2
    return run(cmd, args.workspace)


def _handle_verify(args) -> int:
    j = getattr(args, "json", False)
    r = _verified(args.claim)
    _finish("verify", r, r["ok"], "fresh" if r["ok"] else "broken", args,
            _r_verify)          # a passing check is silent (bar a tty note)
    if r["ok"] and not j and not getattr(args, "verbose", False):
        _confirm("verify: fresh — the bytes hash to the sealed root")
    if not r["ok"] and not j:
        changed = r.get("changed")
        if changed:
            _err("verify", paint("broken", "fail", stderr=True)
                 + f" — {len(changed)} pinned file(s) changed",
                 detail=changed,
                 hint="restore them, or reseal deliberately — a "
                      "moved criterion is a different claim")
        else:
            _err("verify", paint("broken", "fail", stderr=True)
                 + f" — expected {short(r['root'])}, "
                   f"got {short(r['recomputed'])}")
    return 0 if r["ok"] else 1


def _handle_assess(args) -> int:
    with _Progress("assess: measuring"):
        r = assess_mod.assess(args.claim, mutants=args.mutants,
                              rebuild=args.rebuild,
                              rebuild_into=args.rebuild_into,
                              guided=args.guided, corpus=args.corpus,
                              heldout=args.heldout,
                              heldout_producers=args.heldout_producer,
                              heldout_cases=args.heldout_cases,
                              heldout_into=args.heldout_into)
    def _terse_assess(r):
        bits = []
        circ = r["measured"].get("circularity")
        if circ:
            bits.append("circularity=" + ("ok" if circ["ok"] else "VACUOUS"))
        mut = r["measured"].get("mutation")
        survivors = mut.get("survivors") if mut else None
        if mut:
            bits.append(f"mutation={mut['rate']:.2f}")
            if survivors:
                bits.append(f"survivors={len(survivors)}")
        red = r["measured"].get("re_derivation")
        if red:
            bits.append("rederive[blind]=" + ("pass" if red["ok"] else "fail"))
        redg = r["measured"].get("re_derivation_guided")
        if redg:
            bits.append("rederive[guided]=" + ("pass" if redg["ok"] else "fail"))
        gen = r["measured"].get("generalization")
        if gen:
            for prod in gen["producers"]:
                if prod.get("landed"):
                    bits.append(f"heldout[{prod['name']}]={prod['pass_rate']:.2f}")
        ind = r["measured"].get("independence")
        if ind:
            bits.append(f"independence={ind['degree']}")
        cor = r.get("corpus")
        if cor:
            bits.append(f"corpus={cor['population']}")
        bits.append(f"unmeasured={len(r['not_measured'])}")
        _line(*bits)
        # the survivor is the actionable part — the boundary the tests
        # miss — so name it in the terse view, not only under -v/--json
        if survivors:
            more = (f" (+{len(survivors) - 1} more)"
                    if len(survivors) > 1 else "")
            _line(paint("survivor", "warn"), survivors[0] + more)
    _finish("assess", r, True, "measured", args, _r_assess, _terse_assess)
    return 0


def _handle_rebuild(args) -> int:
    producer, penv = _expand_producer(args.producer)
    with _Progress("rebuild: producer running"):
        if args.recursive:
            r = registry_mod.rebuild_chain(
                args.claim, producer, args.into, producer_env=penv,
                guidance=not args.without_guidance)
        elif kernel.read_manifest(args.claim).get("components"):
            # a composed claim reuses its sealed components (the
            # incremental build: regrow only this layer), rather than
            # asking the producer to reproduce a layer already sealed
            r = registry_mod.rebuild_chain(
                args.claim, producer, args.into, producer_env=penv,
                reuse=True, guidance=not args.without_guidance)
        else:
            r = kernel.rebuild(args.claim, producer, args.into,
                               guidance=not args.without_guidance,
                               producer_env=penv)
    r.setdefault("into", r["claim"])
    r.setdefault("name", kernel.read_manifest(r["claim"])["name"])
    r.setdefault("cost", kernel.cost(r["claim"]))
    try:
        r.setdefault("build", kernel.build_digest(r["claim"]))
    except kernel.ClaimError:
        pass

    def _terse_rebuild(r):
        # the root was unknowable; so was the bill, and money is
        # never spent silently
        c = r.get("cost") or {}
        _line("rebuilt", paint(short(r["root"]), "hash"),
              f"usd={c['usd']}" if c.get("usd") else None,
              f"tokens={c['tokens']}" if c.get("tokens") else None)
    _finish("rebuild", r, True, "rebuilt", args, _r_rebuild, _terse_rebuild)
    return 0


def _handle_pull(args) -> int:
    r = registry_mod.pull(args.component, args.into)
    _finish("pull", r, True, "pulled", args, _r_pull)   # target was named
    return 0


# `_handle_attest` was retired 2026-09-22 — the machine attestation folded into
# `_handle_record` (the --check and --as branches below), reusing the same
# attest_mod functions. `sign` (the human ceremony) is unchanged.


def _handle_sign(args) -> int:
    j = getattr(args, "json", False)
    if args.check:
        r = attest_mod.sign_check(args.claim, None, args.signers)
        _finish("sign", r, r["ok"],
                "authorized" if r["ok"] else "unauthorized", args,
                _r_sign_check)             # a passing check is silent
        if not r["ok"] and not j:
            _err("sign", "unauthorized — no authorization verifies "
                 "against a trust anchor",
                 hint="pass --signers <allowed_signers>, or authorize: "
                      "ret sign --key <ssh_key> --as <identity>")
        return 0 if r["ok"] else 1
    if not args.key or not args.identity:      # review, don't authorize
        r = attest_mod.review_packet(args.claim)
        _finish("sign", r, True, "review", args, _r_review,
                lambda r: _line("review", paint(short(r["sign_root"]), "hash"),
                                f"fresh={str(r['fresh']).lower()}",
                                f"gates={len(r['gates'])}"))
        return 0
    r = attest_mod.sign(args.claim, args.key, args.identity)
    _finish("sign", r, True, "signed", args, _r_sign)
    return 0


def _handle_export(args) -> int:
    tar = args.tar_opt or args.tar
    if not tar:
        tar = kernel.read_manifest(args.claim)["name"] + ".tar"
    r = transfer_mod.export(args.claim, tar, blind=args.blind)
    if tar == "-":              # the archive owns stdout; say nothing
        return 0
    _finish("export", r, True, "exported", args, _r_export)
    return 0


def _handle_record(args) -> int:
    j = getattr(args, "json", False)
    # -- the machine attestation (folded from the retired `attest` verb).
    # --check verifies the in-claim witnesses; --as writes a new one. Both
    # reuse attest_mod, so the in-toto witness format and its self-invalidation
    # on regeneration are unchanged; only the CLI surface moved.
    if args.check:
        r = attest_mod.check(args.claim, args.signers)
        _finish("record", r, r["ok"], "attested" if r["ok"] else "unattested",
                args, _r_attest_check)     # a passing check is silent
        if not r["ok"] and not j:
            _err("record", "unattested — no signature matches these bytes",
                 hint="re-attest the current build: ret record --key "
                      "<ssh_key> --as <identity>")
        return 0 if r["ok"] else 1
    if args.identity:                      # --as => attest the build, in-claim
        if not args.key:
            print("ret: record --as needs --key (the signing key)", file=sys.stderr)
            return 2
        r = attest_mod.attest(args.claim, args.key, args.identity)
        _finish("record", r, True, "attested", args, _r_attest)
        return 0
    key = args.key
    if args.sign and not key:
        key = os.environ.get("RETICULI_KEY")
        if not key:
            raise kernel.ClaimError(
                "record --sign: no configured identity — set RETICULI_KEY "
                "to a private ssh key path, or pass --key")
    if args.out == "-" and key:
        print("ret: record: a detached signature needs a file; "
              "-o - cannot be signed", file=sys.stderr)
        return 2
    with _Progress("record: re-running the gates"):
        doc = record_mod.emit(args.claim)
    earned = all(g["status"] == "ok" for g in doc["gates"])
    if args.out == "-":         # the record owns stdout
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0 if earned else 1
    out = args.out or f"{doc['name']}.record.json"
    record_mod.write(doc, out)
    r = {"name": doc["name"], "root": doc["root"],
         "digest": record_mod.digest(doc), "file": out,
         "earned": earned,
         "signed": record_mod.sign(out, key) if key else None,
         "record": doc}
    _finish("record", r, r["earned"], "recorded", args, _r_record)
    if not args.out and r["earned"] and not j:
        # the path was defaulted, so it is the one thing the user could
        # not already know: name it (tty-only, per the silence rule; a
        # script names -o or reads the --json `file`).
        _confirm(f"record: wrote {out}")
    # a failing gate still records -- the failure is evidence -- but
    # the exit code tells a script which kind of record it is holding
    if not r["earned"] and not j:
        _err("record", "failed — the gates did not pass "
             f"(recorded anyway: {out})",
             hint="a negative result is still evidence; the record "
                  "carries the per-gate detail")
    return 0 if r["earned"] else 1


def _handle_import(args) -> int:
    j = getattr(args, "json", False)
    into = args.into_opt or args.into
    if not into:
        if args.tar == "-":
            print("ret: import: reading stdin needs a destination "
                  "directory", file=sys.stderr)
            return 2
        base = os.path.basename(args.tar)
        for ext in (".tar", ".ret"):
            base = base.removesuffix(ext)
        into = base
    r = transfer_mod.import_(args.tar, into)
    _finish("import", r, r["ok"], "imported" if r["ok"] else "broken",
            args, _r_import)    # a verified import is silent
    if not r["ok"] and not j:
        _err("import", paint("broken", "fail", stderr=True)
             + f" — the extracted bytes do not hash to {short(r['root'])}")
    return 0 if r["ok"] else 1


def _dispatch_pack(args) -> int:
    """One authoring boundary. A declared project (reticuli.toml, no build
    flags) seals in place after its gates pass warm; a draft session needs
    --accept and -o and its gates re-run cold; declaration flags build the
    recipe first. (The `seal` spelling was retired 2026-09-22 — this is the
    single pack entry point.)"""
    root = os.path.abspath(args.path)
    name = args.name
    if args.root is not None:
        # the older grammar, kept working: `ret pack <name> -C <dir>` — the
        # positional was the claim's name, the directory rode -C
        root = os.path.abspath(args.root)
        if args.path != ".":
            name = name or args.path
    build_flags = bool(args.generated or args.gate or args.output or args.pytest)
    declared = (os.path.isfile(os.path.join(root, "reticuli.toml"))
                or os.path.isfile(os.path.join(root, "claim.toml")))
    if args.accept:
        # the session flow: the author declares what decides acceptance
        if not args.into:
            print("ret: pack: --accept needs -o <directory> (where the claim "
                  "materializes)", file=sys.stderr)
            return 2
        if not args.force:
            unresolved = feedback_mod.advise(root).get("uncovered") or []
            if unresolved:
                raise kernel.ClaimError(
                    "pack: unresolved observations — generated files no gate "
                    "covers: " + ", ".join(unresolved)
                    + ". Add a gate (`ret run`), declare differently, or --force.")
        r = authoring_mod.build_claim(root, args.accept, args.into, name,
                                      args.claim, args.generated or [],
                                      args.mutation_floor, args.requires)
        r.setdefault("into", args.into)
        # Honest-partial: a pack states what the trace could not establish and
        # still seals. --json carries the findings under data; humans get a
        # block on stderr, the packed root staying on stdout.
        warns = feedback_mod.warnings(root)
        for a in args.accept:
            p = os.path.join(root, a)
            if os.path.isfile(p) and os.path.getsize(p) == 0:
                warns.append({"kind": "empty-verdict",
                              "detail": f"accept file {a} is empty; the verdict is a "
                                        "zero-byte file, which any run that creates it "
                                        "satisfies — name a check that decides something"})
        if warns:
            r["warnings"] = warns
        _finish("pack", r, True, "packed", args, _r_seal,
                lambda r: _line("packed", paint(short(r["root"]), "hash")))
        if warns and not getattr(args, "json", False):
            _warn_block(warns)
        return 0
    if declared and not build_flags:
        # the recipe IS the declaration; nothing to invent, nowhere else to go
        if args.into:
            print("ret: pack: a declared project seals in place; -o is the "
                  "session flow's destination", file=sys.stderr)
            return 2
        r = pack_mod.pack_declared(root)
        _finish("pack", r, True, "packed", args, _r_pack,
                lambda r: _line("packed", paint(short(r["root"]), "hash")))
        return 0
    if not build_flags:
        if os.path.isfile(os.path.join(root, authoring_mod.TRACE)):
            raise kernel.ClaimError(
                "pack: this is a draft session — declare what decides "
                "acceptance: ret pack --accept <verdict-file> -o <directory>")
        raise kernel.ClaimError(
            "pack: nothing to pack — no reticuli.toml here, no session trace, "
            "and no declaration flags (see `ret help pack`)")
    # the explicit project flow: flags build the recipe, gates run warm, seal
    if args.into:
        # -o belongs to the session flow, which materializes a claim elsewhere;
        # a flag-declared project seals in place. Accepting -o and ignoring it
        # would report success while writing somewhere the author did not ask.
        print("ret: pack: a flag-declared project seals in place; -o is the "
              "session flow's destination (see `ret help pack`)", file=sys.stderr)
        return 2
    gate_cmd, gate_out, extra_inputs = args.gate, args.output, []
    if args.pytest:
        if args.gate or args.output:
            print("ret: pack: --pytest replaces --gate/--output; give one "
                  "or the other", file=sys.stderr)
            return 2
        suite = args.pytest.rstrip("/")
        gate_cmd = f"python3 -m pytest -q {suite} && printf ok > OK"
        gate_out = "OK"
        extra_inputs = [f"{suite}/**/*.py"]
    elif not (args.gate and args.output):
        print("ret: pack: needs --gate and --output, or --pytest",
              file=sys.stderr)
        return 2
    component = None
    if args.component:
        comp = os.path.abspath(args.component)
        cm = kernel.read_manifest(comp)
        outs = [s["output"] for s in kernel.load_recipe(comp).get("step", [])
                if s.get("kind") == "produce"]
        component = {"name": cm["name"], "claim": comp, "outputs": outs}
    name = name or os.path.basename(root.rstrip(os.sep))
    r = pack_mod.pack(root, name, args.generated,
                      args.input + extra_inputs, gate_cmd,
                      gate_out, component=component,
                      mutation_floor=args.mutation_floor, requires=args.requires,
                      by=args.by, inputs_manifest=args.inputs_manifest,
                      environment=args.environment)
    _finish("pack", r, True, "packed", args, _r_pack,
            lambda r: _line("packed", paint(short(r["root"]), "hash")))
    return 0


def _dispatch_audit(args) -> int:
    cached = reuse_mod.lookup(args.claim) if args.reuse else None
    if cached:
        # Reported as REUSED, never as earned: the reader is told the
        # gates did not run now, and when they did. Silent by the silence
        # rule; -v says when the work was actually done.
        r = {"ok": True, "reused": cached["earned"],
             "root": kernel.read_manifest(args.claim)["root"],
             "claim_ok": True,
             "gates": cached["gates"], "environment": []}
        r["name"] = kernel.read_manifest(args.claim)["name"]
        _finish("audit", r, True, "reused", args, _r_audit)
        if not getattr(args, "json", False) and not getattr(args, "verbose", False):
            _confirm("audit: reused — gates earned earlier, not re-run now")
        return 0
    t0 = time.monotonic()
    strict = not args.no_strict
    with _Progress("audit: re-running the criteria") as prog:
        def _on_gate(i, n, name):
            prog.label = f"audit: gate {i}/{n} {name}"
        r = kernel.audit(args.claim, progress=_on_gate, strict=strict) \
            if args.shallow \
            else registry_mod.audit_deep(args.claim, progress=_on_gate,
                                         strict=strict)
        if args.reuse:
            reuse_mod.remember(args.claim, r)
        r.setdefault("name", kernel.read_manifest(args.claim)["name"])
        if args.mutants and r["ok"]:
            r["mutation_score"] = kernel.mutation_score(
                args.claim, max_mutants=args.mutants)
        if args.record is not None:
            # the convenience: preserve this execution's evidence too. The
            # record re-runs the gates itself (a record freezes ITS run).
            doc = record_mod.emit(args.claim)
            out = args.record if isinstance(args.record, str) \
                else f"{doc['name']}.record.json"
            record_mod.write(doc, out)
            r["recorded"] = out
    r["elapsed"] = duration(time.monotonic() - t0)
    if r["ok"]:
        # the RECEIPT: a dated note in the store that this machine earned
        # the verdict. status reads it (only while the root still matches);
        # nothing but --reuse ever TRUSTS it. Best-effort residue.
        try:
            good = sum(1 for g in r["gates"] if _gate_ok(g))
            path = os.path.join(os.path.abspath(args.claim),
                                kernel.STORE, "audit.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime()),
                           "ok": True, "root": r.get("root"),
                           "gates": f"{good}/{len(r['gates'])}",
                           "strict": strict}, f, indent=2, sort_keys=True)
                f.write("\n")
        except OSError:
            pass

    if not r.get("claim_ok", True):
        # identity is broken: whatever gate ran did so on bytes that are not the
        # sealed claim, so its pass/fail decides nothing about the root. Mark it
        # disregarded rather than letting a reader take gates[].status — which
        # can read `ok` — for a verdict the top-level `ok: false` already denies.
        for g in r.get("gates", []):
            g["disregarded"] = True
    _finish("audit", r, r["ok"], _verdict(r), args, _r_audit)
    if r["ok"] and not getattr(args, "json", False) \
            and not getattr(args, "verbose", False):
        gates = r.get("gates", [])
        good = sum(1 for g in gates if _gate_ok(g))
        jail = gates[0].get("quarantine") if gates else None
        _confirm(f"audit: earned — {good}/{len(gates)} gate(s) re-earned here"
                 + (f" ({jail})" if jail else ""))
    if not r["ok"] and not getattr(args, "json", False):
        # class-first, per the style contract: the failure class is the word
        # a script greps and spec/verification.md defines
        verdict = _verdict(r)
        if verdict == "environment":
            _err("audit", paint("environment", "warn", stderr=True)
                 + " — missing " + ", ".join(r["environment"]),
                 hint="install what `requires` names, or audit on a host "
                      "that has it — the gates were not run")
        else:
            bad = [g for g in r.get("gates", []) if not _gate_ok(g)]
            if bad:
                _err("audit", paint("failed", "fail", stderr=True)
                     + f" — gate {bad[0]['output']} "
                       f"({bad[0].get('status', '?')})",
                     hint="the gate's own words: ret audit -v")
            else:
                _err("audit", paint(verdict, "fail", stderr=True))
    return 0 if r["ok"] else 1


def _dispatch_status(args) -> int:
    """status is the one PURE view: it reads and reports, it never executes.
    A draft's observation account, a claim's recorded state with honest
    dates, --files the per-file account, --tree the relationships, --claims
    the claim-store listing, --all everything on one page — all instant.
    Earning verdicts is audit's identity."""
    target = getattr(args, "workspace", None) or getattr(args, "claim", ".")
    if not os.path.isdir(os.path.abspath(target)):
        # a missing path is a refusal, never a fictional empty draft
        raise kernel.ClaimError(f"status: no such directory: {target}")
    if getattr(args, "claims", False):
        ws = os.path.abspath(args.workspace)
        r = {"workspace": ws, "claims": registry_mod.claims(ws)}
        _finish("status", r, True, "listed", args, _r_claims, _r_claims)
        return 0
    if getattr(args, "tree", False):
        ws = os.path.abspath(args.workspace)
        if _phase(ws) == "draft":
            r = feedback_mod.advise(ws)
            if registry_mod.claims(ws):        # the component DAG of the claim store
                r["deps"] = registry_mod.deps(ws)
            _finish("status", r, True, "draft", args, _r_tree, _r_tree)
            return 0
        r = registry_mod.structure(ws)
        _finish("status", r, True, "claim", args, _r_structure, _r_structure)
        return 0
    ws = os.path.abspath(args.workspace)
    if _phase(ws) == "draft":
        store = registry_mod.claims(ws)
        if not os.path.isdir(os.path.join(ws, kernel.STORE)) and not store:
            # no store, no claim, no claim store beneath: there is nothing
            # here to report on, and a fictional empty draft is a lie
            _err(args.cmd, f"not a reticuli workspace: {_rel(ws)}",
                 hint="ret init")
            return 1
        r = feedback_mod.advise(ws)
        if store:
            r["claims"] = store

        def _terse_draft(r):
            # the authoring triad, counted: observed = declared + unresolved
            observed = [f for f in r["files"] if f["observed"] != "-"]
            declared = [f for f in observed if f["declared"] != "-"]
            unresolved = len(r["uncovered"])
            hidden = r.get("hidden") or []
            _line("draft", f"observed={len(observed)}",
                  f"declared={len(declared)}",
                  paint(f"unresolved={unresolved}", "warn") if unresolved
                  else "unresolved=0",
                  paint(f"hidden={len(hidden)}", "warn") if hidden else None,
                  f"claims={len(r.get('claims') or [])}" if r.get("claims") else None)
            if r["uncovered"]:
                print()
                for f in r["files"]:
                    if f["path"] in r["uncovered"]:
                        _line(paint("undeclared", "warn"), f["observed"], f["path"])
            if hidden:
                print()
                for p in hidden:
                    _line(paint("hidden", "warn"), "imported by a gate, not observed", p)
            print()
            _line(paint("next", "meta"), r["nudge"])

        if args.all or getattr(args, "files", False):
            def _draft_all(r):
                _r_status_draft(r)
                if args.all and registry_mod.claims(ws):
                    print()
                    _r_deps(registry_mod.deps(ws))
            _finish("status", r, True, "draft", args, _r_status_draft, _draft_all)
        else:
            _finish("status", r, True, "draft", args, _r_status_draft, _terse_draft)
        return 0
    view = _claim_view(ws)
    if getattr(args, "files", False):
        _finish("status", view, view["ok"], "files", args, _v_status_claim,
                _files_claim)
        return 0
    if args.all:
        def _all_claim(view):
            _ledger_status_claim(view)
            print()
            _files_claim(view)
            print()
            _r_structure(registry_mod.structure(ws))
        _finish("status", view, view["ok"],
                "fresh" if view["ok"] else "broken", args,
                _v_status_claim, _all_claim)
        return 0
    _finish("status", view, view["ok"], "fresh" if view["ok"] else "broken",
            args, _v_status_claim, _t_status_claim)
    return 0


def _dispatch_crosscheck(args) -> int:
    machines = args.machines
    if len(machines) < 2:
        print("ret: crosscheck: compares at least two realizations "
              "(an original and a rebuild)", file=sys.stderr)
        return 2
    fn = (registry_mod.record_proof_deep if args.record_proof
          else registry_mod.crosscheck_deep)
    materialized = False
    with tempfile.TemporaryDirectory(prefix="ret-m2-") as tmp:
        if len(machines) == 2:
            # The byte-copy leg is mechanical — export the original and import
            # it back, which verifies the root en route — so a pair invocation
            # gets a REAL M2, made here and said so, never a silently
            # weakened two-legged test.
            m1, m3s = machines[0], machines[1:]
            tar = os.path.join(tmp, "m2.tar")
            transfer_mod.export(m1, tar)
            m2 = os.path.join(tmp, "m2")
            imp = transfer_mod.import_(tar, m2)
            if not imp["ok"]:
                raise kernel.ClaimError(
                    "crosscheck: the byte copy of M1 does not verify — "
                    "M1 itself is broken")
            materialized = True
        else:
            m1, m2, m3s = machines[0], machines[1], machines[2:]
        with _Progress("crosscheck: re-earning every leg"):
            results = [fn(m1, m2, m3, mutants=args.mutants) for m3 in m3s]
    for x in results:
        x.setdefault("proof_recorded", None)
        x.setdefault("verdict", "accept" if x["satisfied"] else "reject")
    if len(results) == 1:
        r = results[0]
    else:
        order = {"reject": 2, "incomplete": 1, "accept": 0}
        worst = max(results, key=lambda x: order[x["verdict"]])
        r = dict(worst)
        r["builds"] = [{"m3": m3, "verdict": x["verdict"],
                        "satisfied": x["satisfied"]}
                       for m3, x in zip(m3s, results, strict=True)]
        r["satisfied"] = all(x["satisfied"] for x in results)
    r["m2_materialized"] = materialized
    r.setdefault("root", (r.get("roots") or {}).get("M1"))

    _finish("crosscheck", r, r["verdict"] == "accept", r["verdict"], args,
            _r_crosscheck)              # an accepted test is silent (bar a tty note)
    if r["verdict"] == "accept" and not getattr(args, "json", False) \
            and not getattr(args, "verbose", False):
        legs = 2 + len(r.get("builds") or [{}])
        proof = " (proof recorded)" if r.get("proof_recorded") else ""
        _confirm(f"crosscheck: accept — one root across {legs} machines{proof}")
    if r["verdict"] != "accept" and not getattr(args, "json", False):
        if r["verdict"] == "incomplete":
            _err("crosscheck", paint("incomplete", "warn", stderr=True)
                 + " — " + "; ".join(r.get("incomplete") or []),
                 hint="a declared condition nobody measured can never "
                      "accept; measure it or remove the declaration")
        else:
            _err("crosscheck", paint("reject", "fail", stderr=True)
                 + " — " + ("; ".join(r.get("rejected") or []) or "see -v"),
                 hint="the full verdict and the bill: ret crosscheck -v")
    return 0 if r["verdict"] == "accept" else 1
