"""The action-verb renderers: what each maker says when it is done.

Under the silence rule a passing check says nothing, so most of these print
in two registers and one of them is empty.  Terse (`_t_*`) prints only the
UNKNOWABLE — the root a rebuild landed on, the file a transport wrote — or
nothing at all.  Verbose (`_r_*`) prints the explanatory account: the full
hashes, the verdict table, the bill.

Hashes are spelled in FULL under `-v`.  A shortened hash is a convenience
for a glance; a reader asking for the explanation is about to compare it
against something.
"""
import json
import os

from .. import render
from .output import _line, _rel

#: The word for a gate that ran clean AND reproduced its pinned bytes.  It
#: is not a synonym for "ok": "ok" says the command exited zero, this says
#: the claim still holds.
_REPRODUCED = "reproduced"


def _when(stamp) -> str:
    """A timestamp as a reader reads it: the moment, and how long ago."""
    if not stamp:
        return "-"
    return f"{stamp} ({render.ago(stamp)})"


def _row(label: str, value, width: int = 12) -> str:
    """One line of an account, printed."""
    text = _line(label, value, width)
    print(text)
    return text


def _generic_contract(verb: str):
    """A renderer for a verb with no shape of its own.

    Silence when it passed, the fact when it did not: a verb that has
    nothing to tell a reader should not invent something.
    """
    def renderer(data, args, status):
        if not getattr(args, "verbose", False):
            return
        print(f"[{verb}]")
        if isinstance(data, dict):
            for key in sorted(data):
                if not isinstance(data[key], (dict, list)):
                    _row(key, data[key])
    return renderer


# -- verification -----------------------------------------------------------


def _r_verify(data, args, status) -> None:
    """Identity only: a pass is silent, -v spells the hashes in full."""
    if not getattr(args, "verbose", False):
        return
    print("[verify]")
    _row("name", data.get("name"))
    print(f'root = "{data.get("root")}"')
    print(f'recomputed = "{data.get("recomputed")}"')
    _row("phase", data.get("phase"))
    _row("status", status)


def _r_audit(data, args, status) -> None:
    """The verdict table — what was earned, on which bytes, in which jail."""
    if not getattr(args, "verbose", False):
        return
    print("[audit]")
    _row("name", data.get("name"))
    print(f'root = "{data.get("root")}"')
    _row("verdict", status)
    _row("elapsed", render.duration(data.get("elapsed")))
    rows = []
    for gate in data.get("gates") or []:
        rows.append([gate.get("output"), gate.get("status"),
                     _REPRODUCED if gate.get("status") == "ok" else "-",
                     gate.get("quarantine")])
    if rows:
        print(render.table(rows, headers=["gate", "status", "pinned bytes",
                                          "quarantine"]))
    for layer in data.get("layers") or []:
        _row("layer", f"{layer.get('name')}  {layer.get('status')}")
    score = data.get("mutation_score")
    if score:
        print("[mutation_score]")
        _row("mutants", score.get("mutants"))
        _row("rate", f"{score.get('rate', 0.0):.2f}")
        _row("survivors", len(score.get("survivors") or []))


def _r_assess(data, args, status) -> None:
    """How much the criteria prove, in three buckets rather than one number."""
    if not getattr(args, "verbose", False):
        _row("measured", f"{len(data.get('measured') or [])} measured, "
                         f"{len(data.get('not_measured') or [])} not measured")
        return
    print("[assess]")
    _row("name", data.get("name"))
    for bucket in ("measured", "not_measured", "not_applicable"):
        _row(bucket, ", ".join(data.get(bucket) or []) or "nothing")
    _row("gate", ", ".join(data.get("gate") or []))
    _row("declared", json.dumps(data.get("declared") or {}, sort_keys=True))
    score = data.get("mutation_score")
    if score:
        print("[mutation_score]")
        _row("mutants", score.get("mutants"))
        _row("rate", f"{score.get('rate', 0.0):.2f}")


def _r_crosscheck(data, args, status) -> None:
    """The three-machine verdict, and the bill beside it.

    The discovery bill is reported BESIDE the band and never inside it: a
    154k-token authoring session must not reject a one-call redo.
    """
    if not getattr(args, "verbose", False):
        return
    print("[crosscheck]")
    print(f"satisfied = {'true' if data.get('satisfied') else 'false'}")
    print(f'verdict = "{data.get("verdict")}"')
    for label in ("M1", "M2", "M3"):
        root = (data.get("roots") or {}).get(label)
        audited = (data.get("audited") or {}).get(label)
        _row(label, f'{root}  earned={"true" if audited else "false"}')
    _row("equivalence", "true" if data.get("equivalence") else "false")
    _row("reuse", "true" if data.get("reuse") else "false")
    for reason in data.get("rejected") or []:
        _row("rejected", reason)
    for reason in data.get("incomplete") or []:
        _row("incomplete", reason)
    cost = data.get("cost") or {}
    print("[cost]")
    _row("unit", cost.get("unit") or "none shared")
    ratio = cost.get("ratio")
    _row("ratio", f"{ratio:.2f}" if isinstance(ratio, float) else "-")
    _row("tolerance", cost.get("tolerance"))
    if cost.get("declared_tolerance") is not None:
        _row("declared", cost.get("declared_tolerance"))
    if cost.get("tightened"):
        _row("tightened", "true")
    comparable = cost.get("comparable")
    _row("comparable", "unmeasured" if comparable is None
         else ("true" if comparable else "false"))
    for unit, row in sorted((cost.get("envelope") or {}).items()):
        _row(f"envelope {unit}",
             f"paid={row.get('paid')} ceiling={row.get('ceiling')} "
             f"within={row.get('within')}")
    discovery = cost.get("discovery")
    if discovery:
        parts = ", ".join(f"{unit}={value}"
                          for unit, value in sorted(discovery.items()))
        _row("discovery", f"{parts} (the session's own bill: testimony, "
                          f"reported beside the band and never inside it)")
    _row("independence", data.get("independence"))


# -- authoring and transport ------------------------------------------------


def _t_init(data, args, status) -> None:
    """Terse init: the path, because where it went is the unknowable part."""
    print(f"initialized {_rel(data.get('workspace'))}")


def _r_init(data, args, status) -> None:
    if not getattr(args, "verbose", False):
        _t_init(data, args, status)
        return
    print("[init]")
    _row("workspace", data.get("workspace"))
    _row("store", data.get("store"))
    _row("agent", data.get("agent") or "none")


def _r_pack(data, args, status) -> None:
    """Terse pack: the root, which nobody could have known in advance."""
    if not getattr(args, "verbose", False):
        print(f"packed {data.get('name')} {data.get('root')}")
        return
    print("[pack]")
    _row("name", data.get("name"))
    print(f'root = "{data.get("root")}"')
    _row("generated", data.get("generated"))
    _row("inputs", data.get("inputs"))
    _row("component", data.get("component") or "none")


def _r_seal(data, args, status) -> None:
    if not getattr(args, "verbose", False):
        print(f"sealed {data.get('name')} {data.get('root')}")
        return
    print("[seal]")
    _row("name", data.get("name"))
    print(f'root = "{data.get("root")}"')


def _r_rebuild(data, args, status) -> None:
    """Terse rebuild: the root it landed on — the whole point of the verb."""
    if not getattr(args, "verbose", False):
        print(f"rebuilt {_rel(data.get('into'))} {data.get('root')}")
        return
    print("[rebuild]")
    _row("into", data.get("into"))
    print(f'root = "{data.get("root")}"')
    _row("generated", data.get("generated"))
    _row("calls", data.get("calls"))
    _row("quarantine", data.get("quarantine"))
    _row("reused", ", ".join(data.get("reused") or []) or "nothing")


def _r_export(data, args, status) -> None:
    """Silence: the archive you named appeared where you named it."""
    if getattr(args, "verbose", False):
        print("[export]")
        _row("archive", data.get("archive"))
        _row("blind", "true" if data.get("blind") else "false")
        _row("members", len(data.get("members") or []))
        _row("bytes", data.get("bytes"))


def _r_import(data, args, status) -> None:
    if getattr(args, "verbose", False):
        print("[import]")
        _row("into", data.get("into"))
        print(f'root = "{data.get("root")}"')
        _row("verified", "true" if data.get("ok") else "false")


def _r_pull(data, args, status) -> None:
    if not getattr(args, "verbose", False):
        print(f"pulled {data.get('name')} "
              f"({len(data.get('materialized') or [])} claim(s))")
        return
    print("[pull]")
    _row("name", data.get("name"))
    print(f'root = "{data.get("root")}"')
    _row("materialized", ", ".join(data.get("materialized") or []))


def _r_hooks(data, args, status) -> None:
    if not getattr(args, "verbose", False):
        return
    print("[hooks]")
    _row("status", data.get("status"))
    _row("wired", ", ".join(data.get("wired") or []))
    _row("settings", data.get("settings"))


# -- evidence ---------------------------------------------------------------


def _r_record(data, args, status) -> None:
    """Silence: the file you named appears, and nothing else is said."""
    if not getattr(args, "verbose", False):
        return
    print("[record]")
    doc = data.get("record") or {}
    _row("name", doc.get("name"))
    print(f'root = "{doc.get("root")}"')
    print(f'build_digest = "{doc.get("build_digest")}"')
    print(f'digest = "{data.get("digest")}"')
    for gate in doc.get("gates") or []:
        _row("gate", f"{gate.get('output')}  {gate.get('status')}  "
                     f"{gate.get('sandbox')}")
    if data.get("path"):
        _row("wrote", _rel(data["path"]))
    if data.get("signature"):
        _row("signature", _rel(data["signature"]))


def _r_attest(data, args, status) -> None:
    if getattr(args, "verbose", False):
        print("[attest]")
        _row("identity", data.get("identity"))
        print(f'root = "{data.get("root")}"')
        _row("statement", data.get("statement"))


def _r_attest_check(data, args, status) -> None:
    if not getattr(args, "verbose", False):
        return
    print("[attest --check]")
    _row("anchored", "true" if data.get("anchored") else "false")
    for row in data.get("attestations") or []:
        _row("statement", f"{row.get('identity')}  {row.get('verdict')}  "
                          f"drifted={row.get('drifted')}")


def _r_review(data, args, status) -> None:
    """The packet a signer stands behind — a view, so it speaks."""
    if not getattr(args, "verbose", False):
        print(f"review {data.get('name')} {data.get('sign_root')} "
              f"audit={'ok' if (data.get('audit') or {}).get('ok') else 'no'}")
        return
    print("[review]")
    _row("name", data.get("name"))
    print(f'root = "{data.get("root")}"')
    print(f'build_digest = "{data.get("build_digest")}"')
    print(f'sign_root = "{data.get("sign_root")}"')
    audit = data.get("audit") or {}
    _row("audit", f"{audit.get('verdict')} "
                  f"({'ok' if audit.get('ok') else 'refused'})")
    for gate in audit.get("gates") or []:
        _row("gate", f"{gate.get('output')}  {gate.get('status')}")
    for layer in audit.get("layers") or []:
        _row("layer", f"{layer.get('name')}  {layer.get('status')}")
    _row("proof", "recorded" if data.get("proof") else "none")


def _r_sign(data, args, status) -> None:
    """Silence: an authorization is an act, not an announcement."""
    if getattr(args, "verbose", False):
        print("[sign]")
        _row("ceremony", data.get("ceremony"))
        _row("identity", data.get("identity"))
        print(f'sign_root = "{data.get("sign_root")}"')
        _row("statement", data.get("statement"))
        _row("packet", data.get("packet"))
        _row("proof", "recorded" if data.get("proof_recorded") else "none")


def _r_sign_check(data, args, status) -> None:
    if not getattr(args, "verbose", False):
        return
    print("[sign --check]")
    _row("anchored", "true" if data.get("anchored") else "false")
    print(f'sign_root = "{data.get("sign_root")}"')
    for row in data.get("authorizations") or []:
        _row("authorization",
             f"{row.get('identity')}  {row.get('verdict')}  "
             f"packet={'ok' if row.get('packet_holds') else 'no'}  "
             f"proof={'recorded' if row.get('proof_recorded') else 'none'}")
