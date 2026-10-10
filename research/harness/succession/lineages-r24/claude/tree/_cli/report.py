"""reticuli._cli.report: the action-verb renderers (spec/layers.md "surface").

One `_r_<verb>` function per CLI verb that does real work (`verify`,
`rebuild`, `seal`, `crosscheck`, `sign`, ...): it calls into the layer that
owns the verb, classifies the outcome into the `(ok, status, root)` triple
`output._finish` renders, and returns the finished envelope. `_generic_contract`
is the shared refusal boundary every one of them goes through, so a
`kernel.ClaimError` raised anywhere beneath is reported the same way no
matter which verb or which layer raised it -- the one-voice promise
`output._err` states for a hard refusal applies here to a verb's own result
too. `_row` and `_when` are small display primitives the renderers share
rather than each reinventing. Stdlib only.
"""
import datetime
import os

from reticuli import assess, attest, hooks, kernel, pack, record, registry, render, transfer

from . import output


def _generic_contract(cmd: str, args, action, classify=None):
    """Run `action()` once, catch the only kernel error, and finish.

    `classify(result) -> (ok, status, root)` turns the layer's own return
    value into what `output._finish` renders; the default treats a dict
    with a falsy/missing "ok" as failure and anything else as a pass with
    no root to report.
    """
    try:
        result = action()
    except kernel.ClaimError as e:
        return output._finish(cmd, {"error": str(e)}, False, "failed", args)

    if classify is None:
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else bool(result)
        status = "ok" if ok else "failed"
        root = result.get("root") if isinstance(result, dict) else None
    else:
        ok, status, root = classify(result)
    return output._finish(cmd, result, ok, status, args, root=root)


def _row(*cells) -> str:
    """One line of a plain report table: `cells` joined the same spaced
    way `output._finish`'s verbose dump already uses -- the shared
    primitive every renderer reaches for instead of reinventing it."""
    return "  ".join(str(c) for c in cells)


def _when(value) -> str:
    """A timestamp rendered for a human: a unix float (a ledger event's
    `ts`) or a record's `when` string (`YYYY-MM-DDTHH:MM:SSZ`,
    `spec/record.md`), either way as "<duration> ago"."""
    if isinstance(value, str):
        try:
            dt = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            return value
        value = dt.timestamp()
    return render.ago(value)


# -- identity: verify, audit, seal, rebuild, crosscheck ----------------------

def _r_verify(d: str, args):
    def action():
        return kernel.verify(d)

    def classify(r):
        return r["ok"], ("ok" if r["ok"] else "mismatch"), r.get("root")

    return _generic_contract("verify", args, action, classify)


def _r_audit(d: str, args):
    def action():
        return kernel.audit(d)

    def classify(r):
        if r["ok"]:
            return True, "ok", None
        if r.get("environment"):
            return False, "environment", None
        bad = {g["status"] for g in r.get("gates", []) if g.get("status") != "ok"}
        return False, next(iter(bad), "failed"), None

    return _generic_contract("audit", args, action, classify)


def _r_assess(d: str, args):
    mutants = getattr(args, "mutants", 20)

    def action():
        return assess.assess(d, mutants=mutants)

    def classify(r):
        return True, "ok", None

    return _generic_contract("assess", args, action, classify)


def _r_seal(d: str, args):
    def action():
        return kernel.seal(d)

    def classify(r):
        root = r.get("root") if isinstance(r, dict) else None
        return True, "ok", root

    return _generic_contract("seal", args, action, classify)


def _r_rebuild(d: str, args):
    producer = getattr(args, "producer", None)
    into = getattr(args, "into", None) or d

    def action():
        return kernel.rebuild(d, producer, into,
                               produce_from=getattr(args, "produce_from", None),
                               input_from=getattr(args, "input_from", None),
                               guidance=getattr(args, "guidance", True),
                               producer_env=getattr(args, "producer_env", None))

    def classify(r):
        return True, "ok", r.get("root")

    return _generic_contract("rebuild", args, action, classify)


def _r_crosscheck(m1: str, m2: str, m3: str, args):
    def action():
        return kernel.crosscheck(m1, m2, m3, mutants=getattr(args, "mutants", None))

    def classify(r):
        return r["satisfied"], r["verdict"], None

    return _generic_contract("crosscheck", args, action, classify)


# -- the exchange verbs: export/import, pull, record -------------------------

def _r_export(d: str, args):
    def action():
        transfer.export(d, args.out, blind=getattr(args, "blind", False))
        return {"ok": True, "out": args.out}

    def classify(r):
        return True, "ok", None

    return _generic_contract("export", args, action, classify)


def _r_import(args):
    def action():
        return transfer.import_(args.tar, args.into)

    def classify(r):
        return r["ok"], ("ok" if r["ok"] else "mismatch"), r.get("root")

    return _generic_contract("import", args, action, classify)


def _r_pull(d: str, args):
    def action():
        return registry.pull(d, args.into)

    def classify(r):
        return True, "ok", r.get("root")

    return _generic_contract("pull", args, action, classify)


def _r_record(d: str, args):
    def action():
        doc = record.emit(d)
        out = getattr(args, "out", None)
        if out:
            record.write(doc, out)
            key = getattr(args, "key", None)
            if key:
                record.sign(out, key)
        return doc

    def classify(r):
        return True, "ok", r.get("root")

    return _generic_contract("record", args, action, classify)


# -- attestation and the signing ceremony -------------------------------------

def _r_attest(d: str, args):
    def action():
        return attest.attest(d, args.key, args.identity)

    def classify(r):
        return True, "ok", r.get("root")

    return _generic_contract("attest", args, action, classify)


def _r_attest_check(d: str, args):
    def action():
        return attest.check(d, signers=getattr(args, "signers", None))

    def classify(r):
        return r["ok"], ("ok" if r["ok"] else "unverified"), None

    return _generic_contract("attest_check", args, action, classify)


def _r_sign(d: str, args):
    def action():
        return attest.sign(d, args.key, args.identity, ws=getattr(args, "ws", None))

    def classify(r):
        return True, "ok", r.get("root")

    return _generic_contract("sign", args, action, classify)


def _r_sign_check(d: str, args):
    def action():
        return attest.sign_check(d, ws=getattr(args, "ws", None), signers=getattr(args, "signers", None))

    def classify(r):
        return r["ok"], ("ok" if r["ok"] else "unauthorized"), None

    return _generic_contract("sign_check", args, action, classify)


def _r_review(d: str, args):
    def action():
        return attest.review_packet(d, ws=getattr(args, "ws", None))

    def classify(r):
        ok = bool(r.get("audit", {}).get("ok"))
        return ok, ("ok" if ok else "failed"), r.get("root")

    return _generic_contract("review", args, action, classify)


# -- authoring/agents: pack a project, wire the hook handshake ---------------

def _r_pack(d: str, args):
    def action():
        return pack.pack(d, args.name, args.generated, args.inputs, args.gate,
                          gate_output=args.gate_output,
                          component=getattr(args, "component", None),
                          claim_format=getattr(args, "format", None),
                          envelope=getattr(args, "envelope", None),
                          mutation_floor=getattr(args, "mutation_floor", None),
                          requires=getattr(args, "requires", None),
                          by=getattr(args, "by", None),
                          inputs_manifest=getattr(args, "inputs_manifest", None),
                          environment=getattr(args, "environment", None))

    def classify(r):
        return True, "ok", r.get("root")

    return _generic_contract("pack", args, action, classify)


def _r_hooks(args):
    def action():
        return hooks.install(getattr(args, "path", "."))

    def classify(r):
        return True, "ok", None

    return _generic_contract("hooks", args, action, classify)


# -- init: the skeleton a draft claim starts from ----------------------------

def _t_init(name: str) -> str:
    """The skeleton `reticuli.toml` text `ret init` writes: a draft claim
    naming itself and declaring nothing else yet, ready to grow
    `[[step]]` entries."""
    return render.dump_recipe({"claim": {"name": name}, "step": []})


def _r_init(d: str, args):
    def action():
        name = getattr(args, "name", None) or os.path.basename(os.path.abspath(d))
        path = os.path.join(d, kernel.RECIPE)
        if os.path.isfile(path):
            raise kernel.ClaimError(f"refused: {path!r} already exists")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_t_init(name))
        return {"ok": True, "name": name, "path": path}

    def classify(r):
        return True, "ok", None

    return _generic_contract("init", args, action, classify)
