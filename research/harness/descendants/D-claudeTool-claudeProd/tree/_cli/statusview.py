"""The status family: the one view.

`status` reads and reports, never executes. Every form is instant on any
claim, and every form ends with the ladder's `next` -- the first rung this
claim has not yet earned. A view never fails: a broken claim is reported and
pointed at its fix, because refusing to describe something is not a
description.
"""
import os

from .. import kernel
from .. import registry
from .. import render
from ..authoring import _session
from .output import _color, _line, _rel
from .views import _claim_view

#: What each declared class IS, in the words a reader orients by. The class is
#: the mechanism; the role is the meaning.
_DECLARED_ROLE = {
    "generated": "free",
    "pinned": "exact",
    "validated": "verdict",
    "carried": "shipped",
    "input": "criterion",
}

#: What a declared file is called in the tree lens.
_TREE_LABEL = {"generated": "generated", "pinned": "pinned",
               "validated": "pinned", "carried": "carried",
               "input": "input"}

#: The colour each class carries where colour is on.
_CLASS_COLOR = {"generated": "cyan", "pinned": "yellow",
                "validated": "green", "carried": "magenta",
                "input": "blue"}


# --------------------------------------------------------------------------
# the sealed-claim lenses

def _t_status_claim(view: dict, args) -> None:
    """The terse claim view: identity, what was earned, and what is next."""
    paint = _color(args)
    _line(f"claim      {view['name']}  {render.short(view['root'])}")
    _line(f"identity   "
          + render.paint(view["identity"], "green" if view["ok"] else "red",
                         paint)
          + f"  {view['phase']}")
    audited = view.get("audited")
    if audited:
        _line(f"audited    {audited.get('verdict', 'earned')}, "
              f"{audited.get('when')} ({render.ago(audited.get('when'))}), "
              f"on this machine")
    else:
        _line("audited    never, on this machine")
    measured = view.get("measured")
    if measured:
        score = measured.get("mutation_score") or {}
        _line(f"deciding   measured {score.get('rate')} kill rate, "
              f"{measured.get('when')}")
    else:
        _line("deciding   strength unknown")
    _line(f"discovery  {_bill(view.get('discovery'))}")
    _line(f"redo       {_bill(view.get('cost'))}")
    _line(f"proof      {'recorded' if view.get('proof') else 'none'}")
    count = (view.get("signatures") or {}).get("count") or 0
    _line(f"signed     {count} statement(s)" if count else "signed     none")
    if view.get("changed"):
        _line(f"moved      {', '.join(view['changed'])}")
    _line(f"next       {view['next']}")


def _bill(totals) -> str:
    if not totals:
        return "unmeasured"
    order = ("usd", "tokens", "calls", "seconds")
    parts = []
    for unit in order:
        if unit in totals:
            parts.append(f"{totals[unit]} {unit}")
    for unit in sorted(set(totals) - set(order)):
        parts.append(f"{totals[unit]} {unit}")
    return ", ".join(parts)


def _v_status_claim(view: dict, args) -> None:
    """The explanatory claim view: the same facts, spelled out in full."""
    _line("[status]")
    for label in ("name", "root", "recomputed", "phase", "identity"):
        _line(f"  {label:<14} = {view.get(label)}")
    _line(f"  {'declared':<14} = {', '.join(view.get('declared') or []) or 'none'}")
    _line(f"  {'generated':<14} = {', '.join(view.get('generated') or []) or 'none'}")
    _line(f"  {'deciding':<14} = {', '.join(view.get('deciding') or []) or 'none'}")
    _line(f"  {'components':<14} = {len(view.get('components') or [])}")
    _line(f"  {'discovery':<14} = {_bill(view.get('discovery'))}")
    _line(f"  {'redo':<14} = {_bill(view.get('cost'))}")
    _line(f"  {'next':<14} = {view.get('next')}")


def _files_claim(claim: str, args) -> None:
    """Every declared file by role, hiding none."""
    parsed = kernel.load_recipe(claim)
    table = parsed.get("claim") or {}
    rows = []
    for declared in table.get("inputs") or []:
        rows.append([declared, "input", _DECLARED_ROLE["input"],
                     "present" if os.path.isfile(os.path.join(claim, declared))
                     else "missing"])
    for step in parsed.get("step") or []:
        output = step.get("output")
        if not output:
            continue
        klass = kernel.step_class(step)
        rows.append([output, klass, _DECLARED_ROLE.get(klass, "unknown"),
                     "present" if os.path.isfile(os.path.join(claim, output))
                     else "absent"])
    _line(render.table(rows, ["file", "class", "role", "bytes"]))


def _ledger_status_claim(view: dict, args) -> None:
    """The whole ledger of what this claim fixes, decides, and leaves free."""
    parsed = kernel.load_recipe(view["path"])
    fixed = list((parsed.get("claim") or {}).get("inputs") or [])
    for step in parsed.get("step") or []:
        if step.get("output") and kernel.step_class(step) != "generated":
            fixed.append(step["output"])
    measured = view.get("measured") or {}
    unknown = measured.get("not_measured") if measured else \
        list(view.get("generated") or [])
    _line(f"fixed      {', '.join(sorted(set(fixed))) or 'none'}")
    _line(f"deciding   {', '.join(view.get('deciding') or []) or 'none'}")
    _line(f"free       {', '.join(view.get('generated') or []) or 'none'}")
    recorded = []
    audited = view.get("audited")
    if audited:
        recorded.append(f"audit, {audited.get('when')}: "
                        f"{audited.get('verdict')}")
    if measured:
        recorded.append(f"assess, {measured.get('when')}: "
                        f"a receipt, not a verdict")
    _line(f"recorded   {'; '.join(recorded) or 'nothing'}")
    _line(f"unknown    {', '.join(sorted(unknown or [])) or 'nothing'}")
    _line(f"next       {view['next']}")


# --------------------------------------------------------------------------
# the draft lens

def _observation(ws: str, name: str, session: dict) -> tuple:
    """What was observed about one file, and on whose evidence."""
    for event in session["events"]:
        if event.get("path") == name and event.get("event") in ("write",
                                                                "read"):
            return event["event"], event.get("via") or "trace"
    for command in session["commands"]:
        for piece in command.split(">"):
            tail = piece.strip().split()
            if tail and tail[0] == name:
                return "gate", "gate"
    return "-", "-"


def _declaration(name: str, session: dict) -> str:
    if name in session["accepted"]:
        return "verdict"
    if name in session["present"]:
        return "generated"
    if name in session["named"]:
        return "criterion"
    return "-"


def _workspace_files(ws: str) -> list:
    found = []
    for base, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith("."):
                continue
            found.append(os.path.relpath(os.path.join(base, name), ws))
    return sorted(found)


def _r_status_draft(ws: str, advice: dict, args, every: bool = False) -> None:
    """A session: what it observed, what it would declare, what is missing."""
    session = _session(ws, advice.get("accept") or [])
    if every:
        rows = []
        for name in _workspace_files(ws):
            observed, evidence = _observation(ws, name, session)
            rows.append([name, observed, _declaration(name, session),
                         evidence])
        _line(render.table(rows, ["path", "observed", "declared",
                                  "evidence"]))
        _line(f"next  {_draft_next(ws, advice)}")
        return
    _line(f"draft      {_rel(ws)}  observed={len(advice['observed'])} "
          f"declared={len(advice['declared'])} "
          f"unresolved={len(advice['unresolved'])}")
    if advice["unresolved"]:
        _line(f"undeclared {', '.join(advice['unresolved'])}")
    elif advice["sealable"]:
        _line("packable")
    else:
        _line(f"not yet    {'; '.join(advice['why'])}")
    _line(f"next       {_draft_next(ws, advice)}")


def _draft_next(ws: str, advice: dict) -> str:
    if advice["unresolved"]:
        return ("declare or cover the generated files: "
                f"ret pack {_rel(ws)} --generated <glob>")
    if not advice["sealable"]:
        return (f"run the check that decides this work: "
                f"ret run '<gate>' -C {_rel(ws)}")
    verdict = (advice.get("accept") or ["OK"])[0]
    return (f"declare the acceptance: ret pack {_rel(ws)} --accept "
            f"{verdict} -o <dir>")


# --------------------------------------------------------------------------
# the tree, the store, the DAG

def _r_tree(target: str, args, ws=None) -> None:
    """The claim lens where there is a claim, the session lens where there is
    not: `--tree` answers "what is this?" either way."""
    paint = _color(args)
    try:
        kernel.read_manifest(target)
    except kernel.ClaimError:
        advice_path = _rel(target)
        _line(f"draft      {advice_path}  no sealed claim here yet")
        for name in _workspace_files(target):
            _line(f"    {name}")
        return
    structure = registry.structure(target, ws)
    _line(f"{structure['name']}  {render.short(structure['root'])}  "
          f"{structure['phase']}  layers={structure['layers']}")
    parsed = kernel.load_recipe(target)
    rows = []
    for declared in (parsed.get("claim") or {}).get("inputs") or []:
        rows.append(("input", declared))
    for step in parsed.get("step") or []:
        if step.get("output"):
            rows.append((kernel.step_class(step), step["output"]))
    for klass, name in rows:
        label = _TREE_LABEL.get(klass, klass)
        if paint:
            _line("    " + render.paint(name, _CLASS_COLOR.get(klass, "grey"),
                                        True))
        else:
            _line(f"    {label:<10} {name}")
    for child in structure.get("components") or []:
        _line(f"    component  {child.get('component')}  "
              f"{render.short(child.get('root'))}  {child.get('status')}")


def _r_claims(ws: str, args) -> None:
    """Every claim this workspace keeps."""
    rows = [[entry["name"], render.short(entry["root"]), entry["phase"],
             f"components={entry['components']}"]
            for entry in registry.claims(ws)]
    if not rows:
        _line("no claims in this workspace yet")
        return
    _line(render.table(rows, ["claim", "root", "phase", "composition"]))


def _r_deps(ws: str, args) -> None:
    """The dependency DAG as the store can see it."""
    graph = registry.deps(ws)
    rows = []
    for claim in graph["claims"]:
        if not claim["depends_on"]:
            rows.append([claim["name"], "-", "-", "standalone"])
        for edge in claim["depends_on"]:
            rows.append([claim["name"], edge["component"],
                         render.short(edge["root"]), edge["status"]])
    _line(render.table(rows, ["claim", "depends on", "root", "status"]))


def _r_structure(claim: str, args, ws=None) -> None:
    """The claim and everything beneath it, drawn."""
    _line(render.tree(registry.structure(claim, ws)))
