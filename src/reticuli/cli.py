"""ret — the command line. The invariant is the three-machine test; every stdout
is a TOML fact sheet, a pandas-style table, or a tree.

The surface speaks v2 and only v2: `seal`, `rebuild`, `crosscheck`, `sign`,
`claims`. v1 carried a compatibility bridge that accepted plain-CS spellings as
aliases for its own vocabulary; here the plain names ARE canonical, so there is
no alias layer and no old verb to accept.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from . import assess as assess_mod
from . import attest as attest_mod
from . import authoring as authoring_mod
from . import feedback as feedback_mod
from . import hooks as hooks_mod
from . import inspect as inspect_mod
from . import kernel
from . import pack as pack_mod
from . import record as record_mod
from . import registry as registry_mod
from . import reuse as reuse_mod
from . import transfer as transfer_mod
from .render import emit, short, table, toml, tree

# -- the kernel's public surface, nothing below it ---------------------------


def _phase(d: str) -> str:
    """`kernel.phase`, with a directory that holds no readable claim reported as
    `draft`.

    v1's phase answered "vapor" for any directory at all. The v2 kernel REFUSES
    one whose recipe or manifest it cannot read — a refusal is more honest than
    a positive an auditor would misread — so a surface that asks "is this a
    session or a claim?" absorbs that refusal here, exactly as the exchange
    layer does when it scans a claim store.
    """
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "draft"


def _verified(claimdir: str) -> dict:
    """`kernel.verify`, plus the phase.

    v1's verify carried a `phase`; the v2 kernel's returns identity only
    (spec/kernel-api.md). The surface asks `phase` for it — the same public
    answer, one call later — so `ret verify` and `ret status` still print what
    a reader needs to act on.
    """
    r = dict(kernel.verify(claimdir))
    r["phase"] = _phase(claimdir)
    return r


# -- session setup (git-native) ---------------------------------------------


def _ensure(path: str, lines: list[str], made: list, label: str) -> None:
    content = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            content = f.read()
    missing = [ln for ln in lines if ln not in content]
    if missing:
        with open(path, "a", encoding="utf-8") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write("\n".join(missing) + "\n")
        made.append({"path": label, "status": "updated" if content else "created"})


def init(project: str) -> dict:
    root = os.path.abspath(project)
    made: list = []
    os.makedirs(os.path.join(root, kernel.STORE), exist_ok=True)
    trace = os.path.join(root, authoring_mod.TRACE)
    rel = authoring_mod.TRACE.replace(os.sep, "/")   # git patterns are posix
    if not os.path.exists(trace):
        open(trace, "w").close()
        made.append({"path": rel, "status": "created"})
    _ensure(os.path.join(root, ".gitignore"),
            ["# Reticuli: history is local — never committed",
             rel, ".reticuli/**/ledger.jsonl",
             ".reticuli/**/tmp/"], made, ".gitignore")
    _ensure(os.path.join(root, ".gitattributes"),
            ["# Reticuli: sealed bytes are binary — no text/CRLF conversion",
             ".reticuli/** -text"], made, ".gitattributes")
    return {"project": root, "files": made}


def run(cmd: str, workspace: str) -> int:
    root = os.path.abspath(workspace)
    trace = os.path.join(root, authoring_mod.TRACE)
    os.makedirs(os.path.dirname(trace), exist_ok=True)
    print(f"ret run: {cmd}  (tracked -> {authoring_mod.TRACE})", file=sys.stderr)
    proc = subprocess.run(cmd, shell=True, cwd=root, check=False,
                          env={**os.environ, "RETICULI": "1"})
    with open(trace, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "bash", "cmd": cmd, "ts": round(time.time(), 3)}) + "\n")
    return proc.returncode


# -- renderers (TOML | table) ------------------------------------------------


def _r_init(r: dict) -> None:
    print(f"# init {r['project']}")
    table(r["files"] or [{"path": "already set up", "status": ""}],
          ("status", "status"), ("path", "path"))
    print("# ready: work, `ret run` your checks, `ret seal` when it holds")


def _r_attest(r: dict) -> None:
    toml(("attest", {"name": r["name"], "root": short(r["root"]),
                     "identity": r["identity"], "statement": r["statement"],
                     "signature": r["signature"]}))
    print("# commit the pair — the attestation travels with the claim")


def _r_attest_check(r: dict) -> None:
    toml(("attest", {"name": r["name"], "root": short(r["root"]),
                     "fresh": r["fresh"], "attested": r["ok"]}))
    print()
    table([{"identity": a["identity"], "verdict": a["verdict"],
            "root_match": a["root_match"], "when": a["when"]}
           for a in r["attestations"]] or
          [{"identity": "(none)", "verdict": "", "root_match": None, "when": ""}],
          ("identity", "identity"), ("verdict", "verdict"),
          ("root_match", "root_match"), ("when", "when"))


def _r_hooks(r: dict) -> None:
    toml(("hooks", {"settings": r["settings"], "status": r["status"],
                    "wired": r["wired"] or None}))
    print("# needs `ret` on PATH; events flow once a session exists (`ret init`)")


def _r_verify(r: dict) -> None:
    toml(("verify", {"name": r["name"], "phase": r["phase"],
                     "verdict": "fresh" if r["ok"] else "broken",
                     "root": r["root"], "recomputed": r["recomputed"]}))


def _gate_ok(g: dict) -> bool:
    """One gate's verdict. The failure classes are pinned (spec/verification.md);
    the PASSING spelling is implementation-defined, and the v2 kernel spells it
    `ok` — so the surface asks the class, never a boolean the kernel dropped."""
    return g.get("status") == "ok"


def _verdict(r: dict) -> str:
    """One word a reviewer can act on. `earned`: every verdict reproduced.
    `environment`: a declared requirement is missing here — the verdict was
    never tested. Otherwise the gate's own failure class names it."""
    if r["ok"]:
        return "earned"
    if r.get("environment"):
        return "environment"
    bad = [g for g in r.get("gates", []) if not _gate_ok(g)]
    if not bad and r.get("layers"):            # own gates earned; a component's did not
        layer = next(g for g in r["layers"] if not g["ok"])
        return f"layer {layer['name']}: {layer['status']}"
    if bad:
        return {"mismatch": "carried or broken", "failed": "failed", "timeout": "timeout",
                "environment": "environment"}.get(bad[0].get("status", ""), "carried or broken")
    return "carried or broken" if r.get("claim_ok", True) else "broken"


def _r_inspect(r: dict) -> None:
    """The receiving end, in four blocks: what is fixed, what is free, what
    was demonstrated here, and what remains unknown."""
    toml(("inspect", {"name": r["name"], "root": short(r["root"]),
                      "phase": r["phase"]}))

    fixed = r.get("fixed") or {}
    print("\n  fixed -- change any of this and it is a different claim")
    crit = ", ".join(fixed.get("criteria") or []) or "(the gate names no pinned decider)"
    print(f"    - criteria: {crit}, plus {fixed.get('inputs', 0)} pinned input file(s)")
    for key in ("requires", "environment", "envelope", "mutation_floor"):
        if fixed.get(key):
            print(f"    - {key}: {fixed[key]}")

    free = (r.get("free") or {}).get("generated") or []
    print("\n  free -- rewrite this and the claim keeps its name")
    print(f"    - generated: {', '.join(free) or '(nothing declared generated)'}")

    print("\n  demonstrated -- here, now")
    rows = [
        {"property": "identity", "value": "ok" if r["identity"]["ok"] else "MISMATCH",
         "detail": "the bytes present hash to the sealed root"
                   if r["identity"]["ok"] else
                   f"recomputed {short(r['identity'].get('recomputed'))}"},
        {"property": "gates", "value": "earned" if r["gates"]["ok"] else "not earned",
         "detail": (f"{r['gates']['count']} re-run here, sandboxed: "
                    + ", ".join(f"{g['output']}={g['status']}" for g in r["gates"]["rows"])
                    + ("" if r["gates"].get("claim_ok", True) else
                       " -- but the identity does not hold, so a passing gate "
                       "earns nothing: these are not the sealed bytes"))},
        {"property": "proof", "value": "recorded" if r["proof"]["recorded"] else "none",
         "detail": "a recorded three-machine crosscheck (evidence, not authorization)"
                   if r["proof"]["recorded"] else "no crosscheck recorded on this claim"},
        {"property": "signatures",
         "value": "authorized" if r["signatures"]["authorized"] else "none",
         "detail": (f"{r['signatures']['count']} statement(s)")
                   if r["signatures"]["count"] else
                   ("no trust anchor configured, so nothing can be authorized to you"
                    if not r["signatures"]["anchor"] else "no signatures present")},
    ]
    table(rows, ("property", ""), ("value", ""), ("detail", ""))
    confinement = r.get("confinement") or {}
    print(f"    gates ran under: {confinement.get('backend', '?')}"
          + (" (strict)" if confinement.get("strict") else ""))

    print("\n  unknown -- established by nothing above")
    for line in r["not_established"]:
        print(f"    - {line}")


def _r_assess(r: dict) -> None:
    """Descriptive: numbers, their samples, and an explicit account of what was
    NOT measured. No grade -- the bar belongs to the claim or to the reader."""
    toml(("assess", {"claim": r["claim"], "root": short(r["root"]),
                     "gate": r["gate"]}))
    rows = []
    circ = r["measured"].get("circularity")
    if circ:
        rows.append({"property": "circularity",
                     "value": "ok" if circ["ok"] else "VACUOUS",
                     "detail": ("the gate is decided by pinned files ("
                                + ", ".join(circ["pinned_deciders"][:3] or ["-"])
                                + "), not by generated code") if circ["ok"] else
                               ("gates decided only by generated code: "
                                + ", ".join(circ["vacuous"]))})
    mut = r["measured"].get("mutation")
    if mut:
        pool, n = mut["candidates"], mut["mutants"]
        pct = f"{100.0 * n / pool:.0f}%" if pool else "-"
        rows.append({"property": "mutation", "value": f"{mut['rate']:.2f}",
                     "detail": f"{mut['killed']} of {n} injected faults detected; "
                               f"sampled {n} of {pool} sites ({pct}). "
                               "Rates are not comparable between programs."})
        # The aggregate hides where the blind spot is, and the blind spot is
        # the actionable part: 0.60 from killing every operator swap and no
        # boundary constant is a different suite from 0.60 spread evenly.
        for kind in sorted(mut.get("by_kind") or {}):
            tally = mut["by_kind"][kind]
            rows.append({"property": "", "value": f"{tally['rate']:.2f}",
                         "detail": f"{kind}: {tally['killed']} of "
                                   f"{tally['mutants']} detected, "
                                   f"{mut['pool_by_kind'].get(kind, 0)} sites"})
        for survivor in mut["survivors"][:3]:
            rows.append({"property": "", "value": "survivor", "detail": survivor})
    red = r["measured"].get("re_derivation")
    if red:
        rows.append({"property": "re-derivation",
                     "value": "satisfied" if red["ok"] else "failed",
                     "detail": (f"rebuilt from the tests alone; same root. "
                                f"cost {red.get('cost')}") if red["ok"] else
                               "no conforming implementation -- see the causes below"})
    ind = r["measured"].get("independence")
    if ind:
        who = ""
        if ind.get("original") and ind.get("rebuild"):
            who = (f"{ind['original'].get('model')} -> {ind['rebuild'].get('model')}; ")
        rows.append({"property": "independence", "value": ind["degree"],
                     "detail": who + ind["why"]})
    gen = r["measured"].get("generalization")
    if gen:
        # One row per producer, then one per pair. A rate is printed with its
        # sample and with the split it was drawn from, for the same reason the
        # mutation rate is: 3 of 3 hidden cases and 44 of 53 are not the same
        # evidence, however similar the decimal looks.
        for p in gen["producers"]:
            label = "generalization" if p is gen["producers"][0] else ""
            if not p["landed"]:
                # a producer's failure arrives as the tail of a traceback: keep
                # it to one line, because the table is columns, not a log
                why = " ".join((p["why"] or "").split())[-110:]
                rows.append({"property": label, "value": "no rebuild",
                             "detail": f"{p['name']}: {why}"})
                continue
            note = "" if p["blind"] else " (the claim's own code, not blind: a control)"
            rows.append({"property": label, "value": f"{p['pass_rate']:.2f}",
                         "detail": f"{p['name']}: {p['passed']} of {p['of']} hidden cases "
                                   f"pass, rebuilt from the {gen['kept']} kept of "
                                   f"{gen['cases']}{note}"})
        for pair in gen["pairs"]:
            if pair["excess"] is None:
                continue
            # Float noise reaches the renderer as -1e-17, and "-0.00 excess"
            # reads as a measured negative rather than as nothing to report.
            excess = 0.0 if abs(pair["excess"]) < 0.005 else pair["excess"]
            rows.append({"property": "", "value": f"{excess:+.2f}",
                         "detail": f"{pair['a']} vs {pair['b']}: agree on "
                                   f"{pair['agreement']:.2f} of the hidden cases against "
                                   f"{pair['expected']:.2f} expected of independent "
                                   "producers at those rates -- "
                                   + ("the claim accounts for the agreement"
                                      if pair["excess"] <= 0.05 else
                                      "shared structure the claim never named")})
    if rows:
        print()
        table(rows, ("property", "measured"), ("value", ""), ("detail", ""))

    absent = [(k, v) for k, v in r["not_applicable"].items()]
    if absent:
        print()
        table([{"property": k, "detail": v} for k, v in absent],
              ("property", "not applicable"), ("detail", ""))

    print()
    table([{"property": k.replace("_", "-"), "detail": v}
           for k, v in r["not_measured"].items()],
          ("property", "not measured"), ("detail", ""))

    if red and not red["ok"]:
        if red.get("error"):
            print(f"\n  {red['error'].strip()[-400:]}")
        print("\n  a failed re-derivation does not by itself mean the tests are weak:")
        for cause in red["causes"]:
            print(f"    - {cause}")
        print(f"  {red['distinguish']}")

    floor = r["declared"].get("mutation_floor")
    print()
    if floor is None:
        print("  the claim declares no mutation_floor of its own")
    else:
        got = (r["measured"].get("mutation") or {}).get("rate")
        print(f"  the claim declares mutation_floor = {floor}"
              + (f"; measured {got:.2f}" if got is not None else ""))


def _r_audit(r: dict) -> None:
    facts = {"name": r["name"], "root": short(r["root"]), "fresh": r["claim_ok"],
             "verdict": _verdict(r)}
    if r.get("reused"):
        # The gates did NOT run just now. Saying "earned" here would be the
        # stored-verdict problem wearing this tool's own colours, so the word
        # changes and the report says when the work was actually done.
        facts["verdict"] = "reused"
        facts["earned_here"] = r["reused"]
    if r.get("environment"):
        facts["missing"] = ", ".join(r["environment"])
    if r.get("layers"):
        facts["layers"] = f"{sum(1 for g in r['layers'] if g['ok'])}/{len(r['layers'])} earned"
    toml(("audit", facts))
    print()
    # `reproduced` is spec/verification.md's word for a gate that ran clean and
    # whose pinned bytes match; the kernel's own success spelling is not pinned.
    rows = [{"gate": g["output"], "status": "reproduced" if _gate_ok(g) else g.get("status", "?"),
             "quarantine": g.get("quarantine") or "", "why": (g.get("detail") or "")[-60:]}
            for g in r["gates"]] or [{"gate": "(none)", "status": "", "quarantine": "", "why": ""}]
    table(rows, ("gate", "gate"), ("status", "status"),
          ("quarantine", "quarantine"), ("why", "why"))
    if r.get("layers"):
        print()
        table([{"layer": g["name"], "root": short(g["root"]), "verdict": g["status"],
                "bytes": f"{len(g.get('bytes_from', []))} from this claim"} for g in r["layers"]],
              ("layer", "layer"), ("root", "root"), ("verdict", "verdict"), ("bytes", "bytes"))
    if r.get("mutation_score"):
        m = r["mutation_score"]
        print()
        toml(("mutation_score", {"mutants": m["mutants"], "killed": m["killed"],
                                 "rate": m["rate"], "floor": m.get("floor"),
                                 "candidates": m.get("candidates")}))
        # a survivor's representation is implementation-defined
        # (spec/verification.md), so it is printed as the kernel names it
        for sv in m["survivors"][:12]:
            print(f"  survives  {sv}")
        if len(m["survivors"]) > 12:
            print(f"  … {len(m['survivors']) - 12} more in the claim's mutation residue")


def _r_rebuild(r: dict) -> None:
    c = r.get("cost") or {}
    toml(("rebuild", {"name": r["name"], "root": short(r["root"]), "into": r["into"],
                      "calls": c.get("calls"), "seconds": c.get("seconds"),
                      "tokens": c.get("tokens"), "usd": c.get("usd")}))


def _r_seal(r: dict) -> None:
    toml(("seal", {"verdict": "sealed", "name": r["name"],
                   "root": short(r["root"]), "into": r["into"]}),
         *[("[[depends_on]]", {"component": c["component"], "root": short(c["root"]),
                               "via": c["input"]}) for c in r.get("components", [])])
    print("# git add this claim to share it — identity is deterministic")


def _r_claims(r: dict) -> None:
    print(f"# claims in {os.path.basename(r['workspace']) or r['workspace']}")
    table([{"name": x["name"], "phase": x["phase"], "store": x["store"],
            "root": short(x["root"]), "path": x["path"]} for x in r["claims"]],
          ("name", "name"), ("phase", "phase"), ("store", "store"),
          ("root", "root"), ("path", "path"))


def _r_deps(r: dict) -> None:
    total = sum(len(n["depends_on"]) for n in r["claims"])
    node = {"children": [
        {"label": f"{n['phase']:<7} {n['name']}  {short(n['root'])}",
         "children": [{"label": f"{e['input']}  ⇐  {e['component']}@{short(e['root'])}"
                       + ("" if e["status"] == "ok" else "  (missing)")}
                      for e in n["depends_on"]]}
        for n in r["claims"]]}
    ws = os.path.basename(r["workspace"].rstrip(os.sep)) or r["workspace"]
    tree(f"deps  {ws}  ·  {len(r['claims'])} claim(s), {total} link(s)", node)


def _r_pull(r: dict) -> None:
    toml(("pull", {"component": r["component"], "root": short(r["root"]),
                   "store": r["store"], "registered": r["registered"],
                   "materialized": r["materialized"]}))


def _r_review(r: dict) -> None:
    toml(("review", {"name": r["name"], "root": short(r["root"]),
                     "sign_root": short(r["sign_root"]),
                     "build_digest": short(r["build_digest"]),
                     "fresh": r["fresh"], "audit": r["audit"]["ok"],
                     "gates": len(r["gates"]), "components": len(r["components"])}))
    print("# review the packet, then authorize: ret sign <claim> --key <ssh_key> --as you@lab")


def _r_sign(r: dict) -> None:
    toml(("sign", {"name": r["name"], "root": short(r["root"]),
                   "sign_root": short(r["sign_root"]),
                   "identity": r["identity"], "ceremony": r["ceremony"],
                   "statement": r["statement"], "signature": r["signature"]}))
    print("# accountable authorization recorded — commit the signature pair "
          "to travel with the claim")


def _r_sign_check(r: dict) -> None:
    toml(("sign", {"name": r["name"], "sign_root": short(r["sign_root"]),
                   "authorized": r["ok"]}))
    print()
    table([{"identity": a["identity"], "verdict": a["verdict"],
            "chain_holds": a["chain_holds"], "packet_holds": a.get("packet_holds"),
            "proof_recorded": a.get("proof_recorded"), "ceremony": a["ceremony"]}
           for a in r["authorizations"]] or
          [{"identity": "(none)", "verdict": "", "chain_holds": None,
            "packet_holds": None, "proof_recorded": None, "ceremony": ""}],
          ("identity", "identity"), ("verdict", "verdict"),
          ("chain_holds", "chain_holds"), ("packet_holds", "packet_holds"),
          ("proof_recorded", "proof_recorded"), ("ceremony", "ceremony"))


def _r_export(r: dict) -> None:
    facts = {"tar": r["tar"], "members": r["members"]}
    if r.get("blind"):
        facts["blind"] = True
    toml(("export", facts))
    if r.get("blind"):
        print("# the rebuilder's room: criteria and verdicts travel, the "
              "implementation stays home")


def _r_record(r: dict) -> None:
    toml(("record", {"name": r["name"], "root": short(r["root"]),
                     "digest": short(r["digest"]), "file": r["file"],
                     "earned": r["earned"], "signed": bool(r["signed"])}))
    if not r["earned"]:
        print("# a failing gate still records -- the failure is evidence, "
              "and the exit code says so")


def _r_import(r: dict) -> None:
    toml(("import", {"into": r["into"], "verdict": r["verdict"], "root": short(r["root"])}))


def _r_crosscheck(r: dict) -> None:
    c = r.get("cost") or {}
    m = r.get("mutation_score")
    env_c = c.get("envelope")
    facts = {"verdict": r.get("verdict") or
                        ("accept" if r["satisfied"] else "reject"),
             "satisfied": r["satisfied"],
             "reuse": r["reuse"], "equivalence": r["equivalence"],
             "audited": all(r.get("audited", {}).values()) or False,
             "cost": c.get("comparable"),
             "envelope": (None if not env_c else
                          all(v["within"] is not False for v in env_c.values())),
             "mutation_score": (m["ok"] if m else None),
             "independence": r.get("independence"),
             "proof_recorded": r.get("proof_recorded")}
    if r.get("incomplete"):
        # a declared condition nobody measured: the test has not actually
        # been evaluated, and incomplete can never accept
        facts["incomplete"] = "; ".join(r["incomplete"])
    # a per-machine environment map: v2's kernel folds a missing requirement into
    # that machine's audit instead of reporting it here, so this renders only if a
    # conforming kernel does name it.
    env = {k: ", ".join(v) for k, v in (r.get("environment") or {}).items() if v}
    if env:
        facts["missing"] = "; ".join(f"{k}: {v}" for k, v in env.items())
    # the envelope compares ONE unit — the strongest both machines measured
    # (spec/verification.md) — so the bill is read at that unit, never averaged.
    unit = c.get("unit")
    c1 = (c.get("M1") or {}).get(unit) if unit else None
    c3 = (c.get("M3") or {}).get(unit) if unit else None
    ratio = round(c3 / c1, 3) if c1 and c3 else None
    # an envelope nobody could compute is REPORTED, never passed off as a pass:
    # v1's kernel supplied this note, v2's does not, so the surface says it.
    note = None if unit else "no unit both machines measured — not compared"
    sections = [("crosscheck", facts),
                ("cost", {"unit": unit, "c1": c1, "c3": c3, "ratio": ratio,
                          "tolerance": c.get("tolerance"),
                          "measured": c.get("compared") or None, "note": note})]
    if env_c:
        # the claim's own commitment, read against the redo's ledger: spent
        # over limit per declared unit, with unmeasured said in words
        sections.append(("envelope", {
            u: (f"untested (limit {v['limit']}, unmeasured)" if v["within"] is None
                else f"{v['spent']} / {v['limit']}"
                + ("" if v["within"] else "  EXCEEDED"))
            for u, v in env_c.items()}))
    if m:
        sections.append(("mutation_score", {"floor": m["floor"], "rate": m["rate"],
                                            "killed": m["killed"], "mutants": m["mutants"]}))
    toml(*sections)
    print()
    table([{"machine": k, "root": short(h), "audit": "earned" if r["audited"].get(k) else "failed"}
           for k, h in r["roots"].items()],
          ("machine", "machine"), ("root", "root"), ("audit", "audit"))


def _r_pack(r: dict) -> None:
    toml(("pack", {"name": r["name"], "root": short(r["root"]),
                   "generated": r["generated"], "inputs": r["inputs"]}))
    print("# sealed as a claim — `ret verify .` holds; `ret rebuild .` regrows it")


def _r_status(r: dict) -> None:
    if r["phase"] != "draft":
        toml(("claim", {"name": r["name"], "phase": r["phase"],
                        "freshness": "fresh" if r["ok"] else "broken",
                        "root": short(r["root"])}))
        return
    print(f"# session {os.path.basename(r['session']) or r['session']}"
          f"  ~ draft · {r['trace_events']} trace events")
    table([{"role": f["role"], "kind": f["kind"], "covered": f["covered"], "path": f["path"]}
           for f in r["files"]],
          ("role", "role"), ("kind", "kind"), ("covered", "covered"), ("path", "path"))
    print(f"# {r['nudge']}")


def _r_tree(r: dict) -> None:
    def gloss(f):
        tag = f"{f['role']}/{f['kind']}"
        return f"{f['path']}   {tag}" + ("" if f["covered"] else "  ✗ uncovered")
    node = {"children": [{"label": gloss(f)} for f in r["files"]]}
    ws = os.path.basename(r["session"].rstrip(os.sep)) or r["session"]
    tree(f"session {ws}  ~ draft · {r['trace_events']} events", node)
    print(f"  {r['nudge']}")
    if r.get("deps"):
        print()
        _r_deps(r["deps"])


def _r_structure(r: dict) -> None:
    def nodeify(n):
        kids = [{"label": f"input      {s}   (the claim)"} for s in n["inputs"]]
        kids += [{"label": f"generated  {f}"} for f in n["generated"]]
        for c in n["components"]:
            kids.append({"label": f"{len(c['files'])} file(s)  ⇐  "
                                  f"{c['component']}@{short(c['root'])}"})
        kids += [{"label": f"pinned     {p}   (the verdict)"} for p in n["pinned"]]
        for c in n["components"]:
            if c["layer"]:
                kids.append({"label": f"layer  {c['layer']['name']}  "
                                      f"{short(c['layer']['root'])}  · {c['layer']['phase']}",
                             "children": nodeify(c["layer"])})
            else:
                kids.append({"label": f"layer  {c['component']}@{short(c['root'])}"
                                      "  (missing from the registry)"})
        return kids

    def count(n):
        return 1 + sum(count(c["layer"]) for c in n["components"] if c["layer"])

    claim = r["claim"]
    tree(f"claim {claim['name']}  {short(claim['root'])}  · {claim['phase']}"
         f" · {count(claim)} layer(s), top to leaf", {"children": nodeify(claim)})


def status(workspace: str) -> dict:
    ws = os.path.abspath(workspace)
    if _phase(ws) == "draft":
        return feedback_mod.advise(ws)
    return _verified(ws)


# -- dispatch ----------------------------------------------------------------

_DESC = """\
Sealed, reproducible claims of model-assisted computation. Validity is the
three-machine test: M1 claim, M2 byte-copy, M3 independent redo, one root.

session (draft):
    init        initialize a session store (.reticuli/) and git skin
    hooks       install agent hooks into .claude/settings.json
    status      print phase and freshness

author (draft -> sealed, M1):
    run         run a command; append it to the session trace
    seal        propose a claim from the trace, re-run gates cold, seal
    verify      recompute the root; compare with the sealed manifest

transfer (sealed, M2):
    export      write the claim's declared content to a deterministic tar
    import      extract a tar into a new directory; verify the root
    audit       re-run gates in a scratch workspace; pinned outputs must reproduce
    assess      measure how much the tests actually constrain the code
    inspect     someone handed you a claim: what holds, and what it does not prove
    record      freeze this machine's results as the one file other programs may parse

redo (sealed -> signed, M3):
    rebuild     regrow generated outputs with --producer in a clean workspace; seal
    crosscheck  three-machine test over M1 M2 M3 (--record-proof: record on pass)
    attest      sign with ssh-keygen -Y (--check: verify signatures)
    sign        review the chain and packet (no key), or authorize it (--key --as)

compose:
    pack        seal a project directory as a claim (code generated, checks pinned)
    pull        copy a sealed claim into this workspace as a dependency
    tree        print session files and the dependency graph, or a claim's structure
    claims      list sealed claims"""

_EPILOG = ("`ret <verb> -h` for verb options. `ret hook` is internal, invoked by "
           "installed\nagent hooks. The format and the verdicts: spec/claim-format.md, "
           "spec/verification.md")


def _parser() -> tuple[argparse.ArgumentParser, dict]:
    """The argv grammar, and the verbs it registers.

    Built in one place so the documented map in `_DESC` can be checked against
    what `ret` really dispatches — a verb that exists but is undocumented, or
    documented but absent, is a drift the surface gate catches.
    """
    p = argparse.ArgumentParser(prog="ret", description=_DESC, epilog=_EPILOG,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # verbs carry no parser-level help= — the sectioned map in _DESC is the one
    # listing (argparse only auto-lists verbs that set help=). Section order and
    # membership are structure, ratified by surface_check; the wording is free.
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<verb>")

    def add(name):
        return sub.add_parser(name)

    # -- session (draft)
    add("init").add_argument("project", nargs="?", default=".")
    add("hooks").add_argument("project", nargs="?", default=".")
    add("status").add_argument("workspace", nargs="?", default=".")
    # -- author (M1)
    q = add("run")
    q.add_argument("command")
    q.add_argument("-C", "--workspace", default=".")
    q = add("seal")
    q.add_argument("session", nargs="?", default=".")
    q.add_argument("--accept", action="append", default=[], metavar="PATH", required=True)
    q.add_argument("--into", required=True)
    q.add_argument("--name", default=None)
    q.add_argument("--claim", action="append", default=[], metavar="PATH",
                   help="force a file into the claim (a pinned input), whoever wrote it")
    q.add_argument("--generated", action="append", default=[], metavar="PATH",
                   help="force a file into the generated implementation (produce step)")
    q.add_argument("--mutation-floor", type=float, default=None, metavar="FLOOR",
                   help="declare the mutation kill rate crosscheck holds a redo to (0..1)")
    q.add_argument("--requires", nargs="*", default=[], metavar="TOOL",
                   help="what the gate needs from the host: a binary, python:module, python>=X.Y")
    q.add_argument("--inputs-manifest", default=None, metavar="FILE",
                   help="write the pinned input list to FILE and declare it, instead "
                        "of enumerating hundreds of paths in the recipe (format 2)")
    q.add_argument("--by", default=None, metavar="MODEL",
                   help="who produced the implementation (ledger residue, never identity) "
                        "so `ret assess` can tell whether a rebuild used a different model")
    add("verify").add_argument("claim")
    # -- transfer (M2)
    q = add("export")
    q.add_argument("claim")
    q.add_argument("tar")
    q.add_argument("--blind", action="store_true",
                   help="the rebuilder's room: omit the generated outputs and "
                        "signing residue; criteria, verdicts, and the manifest travel")
    q = add("import")
    q.add_argument("tar")
    q.add_argument("into")
    q = add("audit")
    q.add_argument("claim")
    q.add_argument("--shallow", action="store_true",
                   help="this claim's gates only (default: the whole component chain)")
    q.add_argument("--mutants", type=int, default=0, metavar="N",
                   help="also mutate the generated code N times and report the check's kill rate")
    q.add_argument("--reuse", action="store_true",
                   help="skip the gates if THIS machine already earned this exact claim, "
                        "these exact generated bytes, and this environment (off by "
                        "default: a stored verdict is never trusted)")
    q = add("inspect")
    q.add_argument("claim")
    q.add_argument("--signers", default=None, metavar="ALLOWED_SIGNERS")
    q.add_argument("--no-strict", action="store_true",
                   help="run the stranger's gates under the standard jail "
                        "instead of the strict one (which also masks your "
                        "own files from them)")
    q = add("record")
    q.add_argument("claim")
    q.add_argument("-o", "--out", default=None, metavar="FILE",
                   help="where to write the record (default: <name>.record.json here)")
    q.add_argument("--key", default=None, metavar="SSH_KEY",
                   help="also sign the record, detached, in the reticuli.record namespace")
    q = add("assess")
    q.add_argument("claim")
    q.add_argument("--mutants", type=int, default=assess_mod.DEFAULT_MUTANTS, metavar="N",
                   help="how many faults to inject (default: %(default)s)")
    q.add_argument("--rebuild", metavar="PRODUCER",
                   help="also ask this producer to rebuild from the tests alone (costs money)")
    q.add_argument("--rebuild-into", metavar="DIR",
                   help="keep the rebuild workspace here instead of a temp dir")
    q.add_argument("--heldout", type=float, default=None, metavar="FRACTION",
                   help="hide this fraction of the claim's case corpus, re-seal on the rest, "
                        "and judge each --heldout-producer's blind rebuild on the hidden cases")
    q.add_argument("--heldout-producer", action="append", default=[], metavar="NAME=COMMAND",
                   help="a producer to regrow the implementation from the kept cases alone; "
                        "repeatable, and two or more also give the pairwise excess agreement")
    q.add_argument("--heldout-cases", default=None, metavar="GLOB",
                   help="which pinned inputs are the case corpus (default: the largest "
                        "family of inputs under one directory)")
    q.add_argument("--heldout-into", metavar="DIR",
                   help="keep the held-out workspace here instead of a temp dir")
    # -- redo (M3)
    q = add("rebuild")
    q.add_argument("claim")
    q.add_argument("--producer", required=True)
    q.add_argument("--into", required=True)
    q.add_argument("--recursive", action="store_true",
                   help="DAG-aware: also rebuild component dependencies, bottom-up")
    q.add_argument("--without-guidance", action="store_true",
                   help="hand the producer the outputs to write but NOT the "
                        "hints for how: a pass then measures what the criteria "
                        "alone carry (format 3, where guidance is not in the root)")
    q = add("crosscheck")
    q.add_argument("m1")
    q.add_argument("m2")
    q.add_argument("m3")
    q.add_argument("--record-proof", action="store_true",
                   help="record the three-machine proof on M1 (residue; signed is the "
                        "signing ceremony's)")
    q.add_argument("--mutants", type=int, default=30, metavar="N",
                   help="mutants for the mutation floor, when the claim declares one")
    q = add("attest")
    q.add_argument("claim")
    q.add_argument("--key", default=None, metavar="SSH_KEY")
    q.add_argument("--as", dest="identity", default=None, metavar="IDENTITY")
    q.add_argument("--check", action="store_true")
    q.add_argument("--signers", default=None, metavar="ALLOWED_SIGNERS")
    q = add("sign")
    q.add_argument("claim")
    q.add_argument("--key", default=None, metavar="SSH_KEY")
    q.add_argument("--as", dest="identity", default=None, metavar="IDENTITY")
    q.add_argument("--check", action="store_true")
    q.add_argument("--signers", default=None, metavar="ALLOWED_SIGNERS")
    # -- compose
    q = add("pack")
    q.add_argument("name")
    q.add_argument("--generated", nargs="+", required=True, metavar="GLOB")
    q.add_argument("--input", nargs="*", default=[], metavar="GLOB")
    q.add_argument("--gate", default=None)
    q.add_argument("--output", default=None)
    q.add_argument("--pytest", default=None, metavar="DIR",
                   help="shorthand for an ordinary pytest suite: the gate runs "
                        "`python3 -m pytest -q DIR`, DIR's tests become pinned "
                        "inputs, and the verdict is OK. pytest itself must be "
                        "in the claim's --environment, or on the host PATH")
    q.add_argument("--environment", default=None, metavar="FILE",
                   help="a hash-pinned requirements file the gates run inside; "
                        "pinned into the root, because dependency versions "
                        "decide what passing means")
    q.add_argument("-C", "--root", default=".")
    q.add_argument("--component", default=None, metavar="CLAIM",
                   help="a sealed claim this one layers on: generated files it also outputs "
                        "are declared `from` it, and its verdict is re-earned by `ret audit`")
    q.add_argument("--mutation-floor", type=float, default=None, metavar="FLOOR",
                   help="declare the mutation kill rate crosscheck holds a redo to (0..1)")
    q.add_argument("--requires", nargs="*", default=[], metavar="TOOL",
                   help="what the gate needs from the host: a binary, python:module, python>=X.Y")
    q.add_argument("--inputs-manifest", default=None, metavar="FILE",
                   help="write the pinned input list to FILE and declare it, instead "
                        "of enumerating hundreds of paths in the recipe (format 2)")
    q.add_argument("--by", default=None, metavar="MODEL",
                   help="who produced the implementation (ledger residue, never identity) "
                        "so `ret assess` can tell whether a rebuild used a different model")
    q = add("pull")
    q.add_argument("component")
    q.add_argument("-C", "--into", default=".")
    add("tree").add_argument("workspace", nargs="?", default=".")
    add("claims").add_argument("workspace", nargs="?", default=".")
    # -- internal: agent plumbing, invoked by installed hooks (unlisted)
    q = add("hook")
    q.add_argument("-C", "--workspace", default=None)

    # Both `assess` and `inspect` already emit through the same path; they were
    # simply never given the flag, so the two verbs a script is most likely to
    # want — the measurement and the recipient's report — were the two it could
    # not read.
    for name in ("verify", "audit", "rebuild", "crosscheck", "seal", "pack", "claims",
                 "pull", "export", "import", "status", "tree", "hooks", "attest", "sign",
                 "assess", "inspect", "record"):
        sub.choices[name].add_argument("--json", action="store_true")
    return p, sub.choices


def verbs() -> list[str]:
    """Every verb `ret` accepts, in declaration order — the parser is the source."""
    return list(_parser()[1])


def main(argv: list[str] | None = None) -> int:
    p, _ = _parser()
    args = p.parse_args(argv)
    j = getattr(args, "json", False)
    try:
        if args.cmd == "init":
            return emit(init(args.project), False, _r_init)
        if args.cmd == "hook":
            hooks_mod.consume(args.workspace)   # silent: hook stdout can leak into the agent
            return 0
        if args.cmd == "hooks":
            return emit(hooks_mod.install(args.project), j, _r_hooks)
        if args.cmd == "run":
            return run(args.command, args.workspace)
        if args.cmd == "seal":
            r = authoring_mod.build_claim(args.session, args.accept, args.into, args.name,
                                          args.claim, args.generated, args.mutation_floor,
                                          args.requires)
            return emit(r, j, _r_seal)
        if args.cmd == "verify":
            r = _verified(args.claim)
            emit(r, j, _r_verify)
            return 0 if r["ok"] else 1
        if args.cmd == "audit":
            cached = reuse_mod.lookup(args.claim) if args.reuse else None
            if cached:
                # Reported as REUSED, never as earned: the reader is told the
                # gates did not run now, and when they did.
                r = {"ok": True, "reused": cached["earned"],
                     "root": kernel.read_manifest(args.claim)["root"],
                     "claim_ok": True,
                     "gates": cached["gates"], "environment": []}
                r["name"] = kernel.read_manifest(args.claim)["name"]
                emit(r, j, _r_audit)
                return 0
            r = kernel.audit(args.claim) if args.shallow else registry_mod.audit_deep(args.claim)
            if args.reuse:
                reuse_mod.remember(args.claim, r)
            # the v2 kernel's audit reports the verdict, not a label
            # (spec/kernel-api.md), so the name is read from the manifest
            r.setdefault("name", kernel.read_manifest(args.claim)["name"])
            if args.mutants and r["ok"]:
                r["mutation_score"] = kernel.mutation_score(args.claim, max_mutants=args.mutants)
            emit(r, j, _r_audit)
            return 0 if r["ok"] else 1
        if args.cmd == "inspect":
            r = inspect_mod.inspect(args.claim, signers=args.signers,
                                    strict=not args.no_strict)
            emit(r, j, _r_inspect)
            return 0 if (r["identity"]["ok"] and r["gates"]["ok"]) else 1
        if args.cmd == "assess":
            r = assess_mod.assess(args.claim, mutants=args.mutants,
                                  rebuild=args.rebuild, rebuild_into=args.rebuild_into,
                                  heldout=args.heldout,
                                  heldout_producers=args.heldout_producer,
                                  heldout_cases=args.heldout_cases,
                                  heldout_into=args.heldout_into)
            return emit(r, j, _r_assess)
        if args.cmd == "rebuild":
            if args.recursive:
                r = registry_mod.rebuild_chain(args.claim, args.producer, args.into)
            else:
                r = kernel.rebuild(args.claim, args.producer, args.into,
                                   guidance=not args.without_guidance)
            # v2's rebuild returns {root, claim, …}: the name and the bill are read
            # back off the claim it just sealed, through the pinned public surface
            r.setdefault("into", r["claim"])
            r.setdefault("name", kernel.read_manifest(r["claim"])["name"])
            r.setdefault("cost", kernel.cost(r["claim"]))
            return emit(r, j, _r_rebuild)
        if args.cmd == "crosscheck":
            fn = (registry_mod.record_proof_deep if args.record_proof
                  else registry_mod.crosscheck_deep)
            r = fn(args.m1, args.m2, args.m3, mutants=args.mutants)
            r.setdefault("proof_recorded", None)
            emit(r, j, _r_crosscheck)
            return 0 if r["satisfied"] else 1
        if args.cmd == "pack":
            gate_cmd, gate_out, extra_inputs = args.gate, args.output, []
            if args.pytest:
                if args.gate or args.output:
                    print("ret: --pytest replaces --gate/--output; give one "
                          "or the other", file=sys.stderr)
                    return 2
                suite = args.pytest.rstrip("/")
                gate_cmd = f"python3 -m pytest -q {suite} && printf ok > OK"
                gate_out = "OK"
                extra_inputs = [f"{suite}/**/*.py"]
            elif not (args.gate and args.output):
                print("ret: pack needs --gate and --output, or --pytest",
                      file=sys.stderr)
                return 2
            component = None
            if args.component:
                comp = os.path.abspath(args.component)
                cm = kernel.read_manifest(comp)
                outs = [s["output"] for s in kernel.load_recipe(comp).get("step", [])
                        if s.get("kind") == "produce"]
                component = {"name": cm["name"], "claim": comp, "outputs": outs}
            r = pack_mod.pack(args.root, args.name, args.generated,
                              args.input + extra_inputs, gate_cmd,
                              gate_out, component=component,
                              mutation_floor=args.mutation_floor, requires=args.requires,
                              by=args.by, inputs_manifest=args.inputs_manifest,
                              environment=args.environment)
            return emit(r, j, _r_pack)
        if args.cmd == "claims":
            ws = os.path.abspath(args.workspace)
            return emit({"workspace": ws, "claims": registry_mod.claims(ws)}, j, _r_claims)
        if args.cmd == "pull":
            return emit(registry_mod.pull(args.component, args.into), j, _r_pull)
        if args.cmd == "attest":
            if args.check:
                r = attest_mod.check(args.claim, args.signers)
                emit(r, j, _r_attest_check)
                return 0 if r["ok"] else 1
            if not args.key or not args.identity:
                print("ret: attest needs --key and --as (or --check)", file=sys.stderr)
                return 2
            return emit(attest_mod.attest(args.claim, args.key, args.identity), j, _r_attest)
        if args.cmd == "sign":
            if args.check:
                # v1 declared --signers here and then dropped it; the anchor is
                # what turns "intact" into "authorized", so it is passed through
                r = attest_mod.sign_check(args.claim, None, args.signers)
                emit(r, j, _r_sign_check)
                return 0 if r["ok"] else 1
            if not args.key or not args.identity:      # review, don't authorize
                return emit(attest_mod.review_packet(args.claim), j, _r_review)
            return emit(attest_mod.sign(args.claim, args.key, args.identity), j, _r_sign)
        if args.cmd == "export":
            return emit(transfer_mod.export(args.claim, args.tar, blind=args.blind),
                        j, _r_export)
        if args.cmd == "record":
            doc = record_mod.emit(args.claim)
            out = args.out or f"{doc['name']}.record.json"
            record_mod.write(doc, out)
            r = {"name": doc["name"], "root": doc["root"],
                 "digest": record_mod.digest(doc), "file": out,
                 "earned": all(g["status"] == "ok" for g in doc["gates"]),
                 "signed": record_mod.sign(out, args.key) if args.key else None,
                 "record": doc}
            emit(r, j, _r_record)
            # a failing gate still records -- the failure is evidence -- but
            # the exit code tells a script which kind of record it is holding
            return 0 if r["earned"] else 1
        if args.cmd == "import":
            r = transfer_mod.import_(args.tar, args.into)
            emit(r, j, _r_import)
            return 0 if r["ok"] else 1
        if args.cmd == "status":
            return emit(status(args.workspace), j, _r_status)
        if args.cmd == "tree":
            ws = os.path.abspath(args.workspace)
            if _phase(ws) == "draft":
                r = feedback_mod.advise(ws)
                if registry_mod.claims(ws):        # the component DAG of the claim store
                    r["deps"] = registry_mod.deps(ws)
                return emit(r, j, _r_tree)
            return emit(registry_mod.structure(ws), j, _r_structure)
    except kernel.ClaimError as e:
        print(f"ret: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:                 # `ret … | head`: the reader left; not an error
        try:
            # silence the interpreter's own flush at exit
            sys.stdout = open(os.devnull, "w")   # noqa: SIM115
        except OSError:
            pass
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
