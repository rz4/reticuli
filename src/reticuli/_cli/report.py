"""ret command line — the report layer: the terse and -v renderers for the action verbs."""
from __future__ import annotations

from .. import render
from ..render import ago, paint, short, table, toml
from .output import (
    _line,
    _rel,
)
from .views import (
    _gate_ok,
    _verdict,
)

# -- verbose renderers (TOML | table | tree), behind -v ----------------------


def _generic_contract(cmd: str) -> None:
    """The generic-agent handshake, printed so a non-Claude harness author can
    wire it: run this command at each event, one JSON object on stdin. Short by
    design, so it belongs on the DEFAULT init output, not only under -v — a
    contract the caller cannot see is a contract they cannot follow."""
    print("# generic agent: wire your harness to run, at each event:")
    print(f"#   {cmd}")
    print('#   feeding JSON on stdin: {"event": "write"|"read"|"bash"|"prompt",')
    print('#     "path"|"cmd"|"text": ..., "cwd": "<workspace>"}')




def _t_init(r: dict) -> None:
    _line("initialized", _rel(r["project"]),
          f"agent={r['agent']}" if r["agent"] else None)
    if r.get("agent") == "generic":
        _generic_contract(r.get("hook_command", "ret hook"))




def _r_init(r: dict) -> None:
    print(f"# init {r['project']}")
    table(r["files"] or [{"path": "already set up", "status": ""}],
          ("status", "status"), ("path", "path"))
    agent = r.get("agent")
    if agent == "claude":
        cmd = (r.get("agent_wiring") or {}).get("command", "ret hook")
        print(f"# agent hooks wired: claude → {cmd} (idempotent; --no-agent skips)")
    elif agent == "generic":
        _generic_contract(r.get("hook_command", "ret hook"))
    print("# ready: work, `ret run` your checks, `ret pack` when it holds")




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




def _row(label: str, value, note: str = "", role: str | None = None,
         indent: int = 0, width: int = 10) -> None:
    """One ledger line: label column, value, dim clause-length note.
    Alignment is computed on the PLAIN value, then paint is applied, so
    color never breaks a column."""
    value = str(value)
    lead = f"{' ' * indent}{label:<{width}} "
    body = paint(value, role) if role else value
    if note:
        gap = " " * max(2, 32 - len(value))
        print((lead + body + gap + paint(note, "meta")).rstrip())
    else:
        print((lead + body).rstrip())




def _when(residue: dict) -> str:
    stamp = residue.get("when", "")
    return ago(stamp) if render.colored() else stamp




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
        rows.append({"property": "re-derivation (blind)",
                     "value": "satisfied" if red["ok"] else "failed",
                     "detail": (f"rebuilt from the tests alone, no guidance; same "
                                f"root. cost {red.get('cost')}") if red["ok"] else
                               "no conforming implementation from the tests alone "
                               "-- see the causes below"})
    redg = r["measured"].get("re_derivation_guided")
    if redg:
        rows.append({"property": "re-derivation (guided)",
                     "value": "satisfied" if redg["ok"] else "failed",
                     "detail": (f"a control: rebuilt WITH the recipe's guidance; "
                                f"same root. cost {redg.get('cost')}") if redg["ok"]
                               else "even with the guidance, no conforming "
                                    "implementation"})
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

    cor = r.get("corpus")
    if cor:
        print()
        crows = [{"property": "population",
                  "detail": f"{cor['population']} prior run(s) in the corpus"}]
        cmut = cor.get("mutation")
        if cmut:
            crows.append({"property": "mutation",
                          "detail": f"rate {cmut['rate']:.2f} vs median "
                                    f"{cmut['median']:.2f} across {cmut['of']} "
                                    f"({cmut['percentile']}th percentile)"})
        for key, label in (("re_derivation_blind", "blind re-derivation"),
                           ("re_derivation_guided", "guided re-derivation")):
            k = cor.get(key)
            if k:
                crows.append({"property": label,
                              "detail": f"this {'passed' if k['this'] else 'failed'}; "
                                        f"population {k['population_rate']:.2f} of "
                                        f"{k['of']}"})
        table(crows, ("property", "against the corpus"), ("detail", ""))

    if red and not red["ok"]:
        if red.get("error"):
            print(f"\n  {red['error'].strip()[-400:]}")
        if redg and redg["ok"]:
            # The control passed where the blind run failed: this is the
            # signal the ratchet feeds on -- the guidance carried information
            # the acceptance criteria should, and did not.
            print("\n  guided rebuild passed but blind failed: the tests do not by "
                  "themselves\n  determine the code. The hint carried information the "
                  "criteria should\n  -- that is the dimension to tighten, not the "
                  "producer to replace.")
        else:
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
        # changes and the report says when the work was actually done —
        # humanized on a terminal, the stamp itself everywhere else.
        facts["verdict"] = "reused"
        facts["earned_here"] = (f"{r['reused']} ({ago(r['reused'])})"
                                if render.colored() else r["reused"])
    if r.get("environment"):
        facts["missing"] = ", ".join(r["environment"])
    if r.get("layers"):
        facts["layers"] = f"{sum(1 for g in r['layers'] if g['ok'])}/{len(r['layers'])} earned"
    facts["elapsed"] = r.get("elapsed")
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
    if r.get("recorded"):
        print(f"\n# recorded: {r['recorded']}")




def _r_rebuild(r: dict) -> None:
    c = r.get("cost") or {}
    toml(("rebuild", {"name": r["name"], "root": short(r["root"]), "into": r["into"],
                      "build": short(r.get("build")),
                      "calls": c.get("calls"), "seconds": c.get("seconds"),
                      "tokens": c.get("tokens"), "usd": c.get("usd")}))




def _r_seal(r: dict) -> None:
    toml(("pack", {"verdict": "packed", "name": r["name"],
                   "root": short(r["root"]), "into": r.get("into")}),
         *[("[[depends_on]]", {"component": c["component"], "root": short(c["root"]),
                               "via": c["input"]}) for c in r.get("components", [])])
    print("# git add this claim to share it — identity is deterministic")




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
    for b in r.get("builds") or []:
        print(f"# rebuild {b['m3']}: {b['verdict']}")
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
    if r.get("m2_materialized"):
        facts["m2"] = "materialized here (a byte copy of M1, via export/import)"
    if r.get("incomplete"):
        # a declared condition nobody measured: the test has not actually
        # been evaluated, and incomplete can never accept
        facts["incomplete"] = "; ".join(r["incomplete"])
    # a per-machine environment map: a missing requirement usually folds into
    # that machine's audit; this renders only if a kernel does name it here.
    env = {k: ", ".join(v) for k, v in (r.get("environment") or {}).items() if v}
    if env:
        facts["missing"] = "; ".join(f"{k}: {v}" for k, v in env.items())
    # the envelope compares ONE unit — the strongest both machines measured
    # (spec/verification.md) — so the bill is read at that unit, never averaged.
    unit = c.get("unit")
    c1 = (c.get("M1") or {}).get(unit) if unit else None
    c3 = (c.get("M3") or {}).get(unit) if unit else None
    ratio = round(c3 / c1, 3) if c1 and c3 else None
    # an envelope nobody could compute is REPORTED, never passed off as a pass
    note = None if unit else "no unit both machines measured — not compared"
    # the discovery bill rides beside the band, never inside it: the gap
    # between what authoring cost and what the redo cost is a measurement,
    # not a violation
    disc = (c.get("M1") or {}).get("discovery") or {}
    discovery = ", ".join(f"{k} {disc[k]}" for k in ("usd", "tokens", "calls")
                          if disc.get(k)) or None
    sections = [("crosscheck", facts),
                ("cost", {"unit": unit, "c1": c1, "c3": c3, "ratio": ratio,
                          "tolerance": c.get("tolerance"),
                          "measured": c.get("compared") or None,
                          "discovery": discovery, "note": note})]
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
