"""ret command line — the statusview layer: the status / draft / tree / claims render family."""
from __future__ import annotations

import os

from .. import render
from ..render import paint, short, table, toml, tree
from .output import (
    _line,
)
from .report import (
    _row,
    _when,
)
from .views import (
    _deciding_words,
)


def _t_status_claim(view: dict) -> None:
    """Plain status on a claim: orientation, then the next rung."""
    _row("claim", view["name"])
    _row("root", short(view["root"]), role="hash")
    _row("identity", "fresh" if view["ok"] else "broken",
         role="pass" if view["ok"] else "fail")
    aud = view["audited"]
    _row("audited", f"{_when(aud)} on this machine" if aud
         else "never on this machine", role=None if aud else "meta")
    _row("deciding", _deciding_words(view)
         + (f", {_when(view['deciding'])}" if view["deciding"] else ""),
         role=None if view["deciding"] else "meta")
    disc = view.get("discovery")
    if disc:
        bits = [f"{k} {disc[k]}" for k in ("usd", "tokens") if disc.get(k)]
        _row("discovery", ", ".join(bits) or "recorded",
             role="meta")
    _row("proof", "recorded" if view["proof"] else "none",
         role=None if view["proof"] else "meta")
    _row("signed", f"{view['signatures']} statement(s)" if view["signatures"]
         else "none", role=None if view["signatures"] else "meta")
    print()
    _line(paint("next", "meta"), view["next"])




def _ledger_status_claim(view: dict) -> None:
    """status --all on a claim: the four questions as one aligned ledger,
    every line recorded state — instant, honest about its dates."""
    fixed = view["fixed"]
    _row("claim", view["name"])
    _row("root", short(view["root"]), role="hash")
    _row("phase", view["phase"])
    print()
    if fixed["criteria"]:
        extra = max(0, fixed["inputs"] - len(fixed["criteria"]))
        crit = ", ".join(fixed["criteria"]) \
            + (f" (+ {extra} more inputs)" if extra else "")
    else:
        names = fixed["inputs_list"]
        crit = (", ".join(names[:3]) + (f" (+ {len(names) - 3} more)"
                                        if len(names) > 3 else "")) \
            if names else "(nothing pinned)"
    _row("fixed", crit, "change it and this is a different claim",
         role="pinned")
    for key in ("requires", "environment", "envelope", "mutation_floor"):
        if fixed.get(key):
            _row(key, fixed[key])
    _row("deciding", _deciding_words(view),
         f"assess, {_when(view['deciding'])}" if view["deciding"]
         else "ret assess measures this")
    _row("free", ", ".join(view["free"]) or "(nothing generated)",
         "rewrite it and the claim keeps its name")
    print("\nrecorded")
    _row("identity", "fresh" if view["ok"] else "broken",
         "bytes hash to the sealed root" if view["ok"]
         else "see ret verify for the moved files",
         role="pass" if view["ok"] else "fail", indent=2)
    aud = view["audited"]
    _row("audited", _when(aud) if aud else "never on this machine",
         (f"{aud.get('gates', '')} gates, {'strict' if aud.get('strict') else 'standard'} "
          "jail -- a receipt, not a verdict") if aud else "ret audit earns it",
         indent=2)
    disc = view.get("discovery")
    if disc:
        bits = [f"{k} {disc[k]}" for k in ("usd", "tokens") if disc.get(k)]
        _row("discovery", ", ".join(bits) or "recorded",
             "the session's bill -- reported, never banded", indent=2)
    _row("proof", "recorded" if view["proof"] else "none",
         "" if view["proof"] else "no three-machine crosscheck on record",
         indent=2)
    _row("signed", f"{view['signatures']} statement(s)" if view["signatures"]
         else "none",
         "verify with ret sign --check --signers <file>" if view["signatures"]
         else "no trust anchor configured", indent=2)
    print("\nunknown")
    _row("correctness", "the tests admit any implementation that passes them",
         indent=2, width=14)
    _row("independence", "declared, never proven from content",
         indent=2, width=14)
    print()
    _line(paint("next", "meta"), view["next"])




def _v_status_claim(view: dict) -> None:
    """-v: the fact sheet, then the four questions in their full wording."""
    aud, dec = view["audited"], view["deciding"]
    toml(("status", {"name": view["name"], "root": view["root"],
                     "phase": view["phase"],
                     "identity": "fresh" if view["ok"] else "broken",
                     "audited": aud.get("when") if aud else None,
                     "deciding": dec.get("when") if dec else None,
                     "proof": view["proof"],
                     "signatures": view["signatures"],
                     "next": view["next"]}))
    print()
    print("# the four questions: FIXED is the acceptance boundary -- change any")
    print("# of it and this is a different claim. FREE is the implementation --")
    print("# rewrite it and the claim keeps its name. RECORDED is what this")
    print("# machine has on file, with dates; a receipt is testimony, and only")
    print("# ret audit earns a verdict. UNKNOWN is established by nothing here:")
    print("# a backdoored implementation passing these tests verifies")
    print("# identically, and producer independence is declared, never proven.")




def _files_claim(view: dict) -> None:
    """status --files on a claim: EVERY declared file, by role — the
    per-file account hides nothing behind a count."""
    criteria = set(view["fixed"]["criteria"])
    rows = []
    for p in view["fixed"]["inputs_list"]:
        rows.append({"path": p, "class": "pinned",
                     "note": "decider" if p in criteria else "input"})
    for p in sorted(criteria - set(view["fixed"]["inputs_list"])):
        rows.append({"path": p, "class": "pinned", "note": "decider"})
    env = view["fixed"].get("environment")
    if env and all(r["path"] != env for r in rows):
        rows.append({"path": env, "class": "pinned", "note": "environment"})
    for p in view["free"]:
        rows.append({"path": p, "class": "generated", "note": "free"})
    for p in view.get("verdicts") or []:
        rows.append({"path": p, "class": "validated", "note": "verdict"})
    table(rows, ("path", "path"), ("class", "class"), ("note", "note"))




def _r_claims(r: dict) -> None:
    _line("claims", os.path.basename(r["workspace"]) or r["workspace"],
          f"count={len(r['claims'])}")
    if r["claims"]:
        print()
        table([{"name": x["name"], "phase": x["phase"], "store": x["store"],
                "root": short(x["root"]), "path": x["path"]} for x in r["claims"]],
              ("name", "name"), ("phase", "phase"), ("store", "store"),
              ("root", "root"), ("path", "path"))




def _r_deps(r: dict) -> None:
    total = sum(len(n["depends_on"]) for n in r["claims"])
    node = {"children": [
        {"label": f"{n['phase']:<7} {n['name']}  {short(n['root'])}",
         "children": [{"label": f"{e['input']}  <-  {e['component']}@{short(e['root'])}"
                       + ("" if e["status"] == "ok" else "  (missing)")}
                      for e in n["depends_on"]]}
        for n in r["claims"]]}
    ws = os.path.basename(r["workspace"].rstrip(os.sep)) or r["workspace"]
    tree(f"deps  {ws}  claims={len(r['claims'])}  links={total}", node)




def _r_status_draft(r: dict) -> None:
    """The observation account in full: the three-column triad the authoring
    model defines — how each file was observed, what pack would declare it
    as, and where the observation came from. Dashes are honest: an untraced
    file is declared nothing."""
    _line("draft", os.path.basename(r["session"]) or r["session"],
          f"events={r['trace_events']}")
    print()
    table([{"path": f["path"], "observed": f["observed"],
            "declared": f["declared"], "evidence": f["evidence"]}
           for f in r["files"]],
          ("path", "path"), ("observed", "observed"),
          ("declared", "declared"), ("evidence", "evidence"))
    print()
    _line("next", r["nudge"])
    if r.get("claims"):
        print()
        _r_claims({"workspace": r["session"], "claims": r["claims"]})




_DECLARED_ROLE = {"input": "pinned", "generated": "generated",
                  "validated": "validated", "-": "meta"}




def _r_tree(r: dict) -> None:
    def gloss(f):
        flag = "" if f["covered"] else "  " + paint("(uncovered)", "warn")
        if render.colored():
            # the ls rule: on a terminal the class is the color, and the
            # label words return wherever color is off
            return paint(f["path"], _DECLARED_ROLE.get(f["declared"], "meta")) + flag
        return f"{f['path']}   {f['observed']}/{f['declared']}" + flag
    node = {"children": [{"label": gloss(f)} for f in r["files"]]}
    ws = os.path.basename(r["session"].rstrip(os.sep)) or r["session"]
    tree(f"draft  {ws}  events={r['trace_events']}", node)
    print()
    _line("next", r["nudge"])
    if r.get("deps"):
        print()
        _r_deps(r["deps"])




def _r_structure(r: dict) -> None:
    def leaf(word, path, role, note=""):
        if render.colored():
            return {"label": paint(path, role)}
        return {"label": f"{word:<9}  {path}" + (f"   ({note})" if note else "")}

    def nodeify(n):
        kids = [leaf("input", s, "pinned", "the claim") for s in n["inputs"]]
        kids += [leaf("generated", f, "generated") for f in n["generated"]]
        for c in n["components"]:
            kids.append({"label": f"{len(c['files'])} file(s)  <-  "
                                  f"{c['component']}@{short(c['root'])}"})
        kids += [leaf("pinned", p, "validated", "the verdict") for p in n["pinned"]]
        for c in n["components"]:
            if c["layer"]:
                kids.append({"label": f"layer  {c['layer']['name']}  "
                                      f"{short(c['layer']['root'])}  {c['layer']['phase']}",
                             "children": nodeify(c["layer"])})
            else:
                kids.append({"label": f"layer  {c['component']}@{short(c['root'])}"
                                      "  (missing from the registry)"})
        return kids

    def count(n):
        return 1 + sum(count(c["layer"]) for c in n["components"] if c["layer"])

    claim = r["claim"]
    tree(f"claim  {claim['name']}  {short(claim['root'])}  {claim['phase']}"
         f"  layers={count(claim)}", {"children": nodeify(claim)})
