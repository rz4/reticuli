"""reticuli._cli.report -- the action-verb renderers.

One `_r_*` function per CLI verb (`spec/layers.md`'s CLI verb table): each
resolves the claim directory a verb acts on, does the one thing the verb
in `reticuli.kernel` or a layer above it already implements, and ends
through the shared envelope (`_cli.output._finish`) -- so every verb
speaks the same `--json` shape and the same one-voice refusal
(`_cli.output._err`), whatever it does underneath. `_generic_contract` is
that shared shape, factored out once; most verbs are a one-line `work`
closure handed to it. `_row` and `_when` are the small formatting pieces
the `-v` views (here and in `statusview`) are built from.

This module never runs a gate or seals a claim on its own authority --
it only calls the layer that does and reports what happened.

Stdlib only. Never the network.
"""
import calendar
import os
import time

from . import output
from .. import assess as _assess
from .. import attest as _attest
from .. import hooks as _hooks
from .. import kernel
from .. import pack as _pack
from .. import record as _record
from .. import registry as _registry
from .. import render
from .. import transfer as _transfer


def _claim_dir(args) -> str:
    """The claim directory a verb acts on: `args.claim` if given, else
    the current directory."""
    claim = getattr(args, "claim", None)
    return claim if claim else os.getcwd()


def _row(label: str, value) -> str:
    """One `label: value` line -- the smallest unit the `-v` views are
    built from."""
    return f"{label}: {value}"


def _when(value) -> str:
    """A recorded `when` timestamp (`YYYY-MM-DDTHH:MM:SSZ`, the shape
    every layer below stamps) as a human phrase; the raw value unchanged
    if it does not parse."""
    if not isinstance(value, str):
        return str(value)
    try:
        parsed = time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return value
    return render.ago(calendar.timegm(parsed))


def _generic_contract(command: str, args, work) -> int:
    """Run one verb's `work(d) -> (data, ok, status)` against the claim
    directory `args` names, and end through the shared envelope. A
    refusal (`kernel.ClaimError`) is spoken once, in the one-voice error
    line, and never reaches a caller as a traceback. This is the shape
    every `_r_*` verb below shares."""
    d = _claim_dir(args)
    try:
        data, ok, status = work(d)
    except kernel.ClaimError as exc:
        output._err(command, str(exc))
        return 1
    return output._finish(command, data, ok, status, args)


# ---------------------------------------------------------------------------
# Identity and the deep verbs
# ---------------------------------------------------------------------------
def _r_verify(args) -> int:
    def work(d):
        data = kernel.verify(d)
        return data, data["ok"], ("ok" if data["ok"] else "mismatch")
    return _generic_contract("verify", args, work)


def _r_audit(args) -> int:
    def work(d):
        data = kernel.audit(d)
        ok = bool(data.get("ok"))
        status = data.get("verdict") or ("ok" if ok else "failed")
        return data, ok, status
    return _generic_contract("audit", args, work)


def _r_assess(args) -> int:
    def work(d):
        data = _assess.assess(d, mutants=getattr(args, "mutants", None))
        ok = not data["not_measured"]
        return data, ok, ("complete" if ok else "partial")
    return _generic_contract("assess", args, work)


def _r_seal(args) -> int:
    def work(d):
        manifest = kernel.seal(d)
        return manifest, True, "sealed"
    return _generic_contract("seal", args, work)


def _r_rebuild(args) -> int:
    def work(d):
        manifest = kernel.rebuild(
            d, args.producer, args.into,
            produce_from=getattr(args, "produce_from", None),
            input_from=getattr(args, "input_from", None))
        return manifest, True, "rebuilt"
    return _generic_contract("rebuild", args, work)


def _r_crosscheck(args) -> int:
    def work(d):
        result = kernel.crosscheck(d, args.m2, args.m3, mutants=getattr(args, "mutants", None))
        return result, result["satisfied"], result["verdict"]
    return _generic_contract("crosscheck", args, work)


def _r_record(args) -> int:
    def work(d):
        doc = _record.emit(d)
        out = getattr(args, "out", None)
        if out:
            _record.write(doc, out)
            key = getattr(args, "key", None)
            if key:
                _record.sign(out, key)
        return doc, True, "emitted"
    return _generic_contract("record", args, work)


# ---------------------------------------------------------------------------
# Exchange: transfer, registry, attest
# ---------------------------------------------------------------------------
def _r_export(args) -> int:
    def work(d):
        _transfer.export(d, args.out, blind=getattr(args, "blind", False))
        return {"path": args.out}, True, "exported"
    return _generic_contract("export", args, work)


def _r_import(args) -> int:
    def work(d):
        data = _transfer.import_(args.tar, d)
        return data, data["ok"], ("ok" if data["ok"] else "mismatch")
    return _generic_contract("import", args, work)


def _r_pull(args) -> int:
    def work(d):
        data = _registry.pull(d, args.into)
        return data, data["materialized"], "pulled"
    return _generic_contract("pull", args, work)


def _r_attest(args) -> int:
    def work(d):
        data = _attest.attest(d, args.key, args.identity)
        return data, True, "attested"
    return _generic_contract("attest", args, work)


def _r_attest_check(args) -> int:
    def work(d):
        data = _attest.check(d, signers=getattr(args, "signers", None))
        return data, data["ok"], ("ok" if data["ok"] else "drifted")
    return _generic_contract("attest_check", args, work)


def _r_review(args) -> int:
    def work(d):
        data = _attest.review_packet(d, ws=getattr(args, "workspace", None))
        ok = bool(data["audit"]["ok"])
        return data, ok, ("ready" if ok else "not_ready")
    return _generic_contract("review", args, work)


def _r_sign(args) -> int:
    def work(d):
        data = _attest.sign(d, args.key, args.identity, ws=getattr(args, "workspace", None))
        return data, True, "signed"
    return _generic_contract("sign", args, work)


def _r_sign_check(args) -> int:
    def work(d):
        data = _attest.sign_check(d, ws=getattr(args, "workspace", None),
                                   signers=getattr(args, "signers", None))
        return data, data["ok"], ("authorized" if data["ok"] else "untrusted")
    return _generic_contract("sign_check", args, work)


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------
def _r_pack(args) -> int:
    def work(d):
        data = _pack.pack(d, args.name, args.generated, args.inputs, args.run, args.output)
        return data, data.get("ok", True), "packed"
    return _generic_contract("pack", args, work)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
def _r_hooks(args) -> int:
    def work(d):
        data = _hooks.install(d)
        return data, True, data["status"]
    return _generic_contract("hooks", args, work)


# ---------------------------------------------------------------------------
# init: the one verb with no root or gates to report -- it just gives a
# session a `.reticuli` store to write its trace into, so `_t_init` gets
# its own terse line instead of the generic `command: status (root)`
# shape `output._finish` prints for every other verb.
# ---------------------------------------------------------------------------
def _t_init(data: dict) -> str:
    """The terse, one-line render of an `init` result."""
    return f"initialized {data['claim']}"


def _r_init(args) -> int:
    d = _claim_dir(args)
    os.makedirs(os.path.join(d, kernel.STORE), exist_ok=True)
    data = {"claim": d}
    if not getattr(args, "json", False):
        output._line(_t_init(data), args, color="cyan")
    return output._finish("init", data, True, "initialized", args)
