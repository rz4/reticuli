"""ret — the command line. Fourteen verbs, one concept each:

    observe work -> declare a claim -> test it -> reconstruct it
    -> compare realizations -> preserve evidence

Output has three levels. The default is one terse line (`packed 91c7…`,
`fresh 91c7…`, `earned 91c7… gates=9/9`); `-v` explains in fact sheets and
tables; `--json` is the machine envelope {command, ok, status, root, data}.
Exit codes are boring: 0 the operation and its predicate held, 1 the operation
ran but the predicate failed, 2 the invocation was invalid.

Folded spellings from the earlier grammar still dispatch (seal, hooks,
tree, claims, attest) but are aliases, listed only by `ret help -a`;
the fourteen are the grammar.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

from . import _util, kernel, render
from . import assess as assess_mod
from . import attest as attest_mod
from . import authoring as authoring_mod
from . import feedback as feedback_mod
from . import hooks as hooks_mod
from . import pack as pack_mod
from . import record as record_mod
from . import registry as registry_mod
from . import reuse as reuse_mod
from . import transfer as transfer_mod
from .render import ago, duration, paint, short, table, toml, tree

# -- the kernel's public surface, nothing below it ---------------------------


def _phase(d: str) -> str:
    """`kernel.phase`, with a directory that holds no readable claim reported
    as `draft`. The kernel refuses a directory whose recipe or manifest it
    cannot read — a refusal is more honest than a positive an auditor would
    misread — so a surface that asks "is this a session or a claim?" absorbs
    that refusal here."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "draft"


def _verified(claimdir: str) -> dict:
    r = dict(kernel.verify(claimdir))
    r["phase"] = _phase(claimdir)
    return r


def _signatures(d: str) -> int:
    """How many signed statements are PRESENT on the claim — a count, not a
    verification; `ret sign --check` verifies.

    Two drawers hold statements: attestations (machine signatures over a
    build) and the signing ceremony's authorizations. Counting only the
    first made a freshly signed claim read `signed none` — found live, by
    the first user to sign one."""
    base = os.path.abspath(d)
    count = 0
    try:
        count += len([f for f in os.listdir(os.path.join(base, attest_mod.ATTEST))
                      if f.endswith(".json")])
    except OSError:
        pass
    try:
        count += len([f for f in os.listdir(os.path.join(base, attest_mod.SIGN_DIR))
                      if f.endswith(".sign.json")])
    except OSError:
        pass
    return count


def _read_residue(d: str, name: str, root) -> dict | None:
    """A store residue (an audit receipt, assess's measurements), trusted
    only while the root it stamps still matches — measurements of a
    different claim say nothing about this one."""
    try:
        with open(os.path.join(d, kernel.STORE, name), encoding="utf-8") as f:
            residue = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(residue, dict) and residue.get("root") == root:
        return residue
    return None


def _claim_view(ws: str) -> dict:
    """Everything status says about a claim, from RECORDED state only.
    A view reads; it never executes — earning verdicts is audit's identity,
    and status reporting records with honest dates is the other half of
    the same doctrine."""
    identity = kernel.verify(ws)
    recipe = kernel.load_recipe(ws)
    manifest = kernel.read_manifest(ws)
    root = manifest.get("root")
    generated = set(kernel.generated_outputs(recipe))
    deciders: list[str] = []
    for step in recipe.get("step", []):
        if step.get("kind") == "gate":
            deciders += [x for x in kernel.gate_deciders(step.get("run") or "")
                         if x not in generated]
    claim_table = recipe.get("claim") or {}
    audited = _read_residue(ws, "audit.json", root)
    if audited and not audited.get("ok"):
        audited = None                    # a receipt records an EARNED verdict
    view = {
        "name": manifest.get("name"), "root": root,
        "phase": kernel.phase(ws), "ok": identity["ok"],
        "recomputed": identity.get("recomputed"),
        "changed": identity.get("changed"),
        "audited": audited,
        "deciding": _read_residue(ws, "assess.json", root),
        "discovery": (kernel.cost(ws) or {}).get("discovery"),
        "proof": bool(manifest.get("proof")),
        "signatures": _signatures(ws),
        "fixed": {"criteria": sorted(set(deciders)),
                  "inputs": len(claim_table.get("inputs") or []),
                  "inputs_list": list(claim_table.get("inputs") or []),
                  "requires": claim_table.get("requires") or [],
                  "environment": claim_table.get("environment"),
                  "envelope": claim_table.get("envelope"),
                  "mutation_floor": claim_table.get("mutation_floor")},
        "free": sorted(generated),
        "verdicts": sorted(s.get("output") for s in recipe.get("step", [])
                           if s.get("kind") == "gate" and s.get("output")),
    }
    view["next"] = _next_step(view)
    return view


def _next_step(view: dict) -> str:
    """The ladder of confidence: the first rung this claim has not earned
    is the next command. The whole product, taught one line at a time."""
    if not view["ok"]:
        return ("restore the changed files, or reseal deliberately -- "
                "a moved criterion is a different claim")
    if not view["audited"]:
        return "earn it here: ret audit ."
    if not view["deciding"]:
        return "measure the tests: ret assess ."
    if not view["proof"]:
        # --record-proof so following this line actually advances the claim:
        # a plain crosscheck decides and prints, but records nothing, and the
        # next status would repeat this same rung.
        return ("prove it: ret rebuild . --producer openai -o ../m3 "
                "&& ret crosscheck . ../m3 --record-proof")
    if not view["signatures"]:
        return "stand behind it: ret sign . --key <ssh_key> --as <you>"
    return "share it: push with the CI workflow (M2), or ret export"


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


def init(project: str, agent: str | None = None, no_agent: bool = False) -> dict:
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
    # Agent integration is part of starting, not a separate concept. The Claude
    # Code harness is auto-wired (detected, or asked for); any other harness is
    # `--agent generic`: the workspace is set up and the harness is pointed at
    # the generic `ret hook` contract, since reticuli cannot know its config.
    wiring = None
    agent_name = None
    if agent and agent not in ("claude", "generic"):
        raise kernel.ClaimError(
            f"init: unsupported agent {agent!r} (supported: claude, generic)")
    if no_agent:
        pass
    elif agent == "generic":
        agent_name = "generic"           # workspace ready; harness targets `ret hook`
    elif agent == "claude" or (agent is None
                               and os.path.isdir(os.path.join(root, ".claude"))):
        wiring = hooks_mod.install(root)
        agent_name = "claude"
    return {"project": root, "files": made, "agent": agent_name,
            "agent_wiring": wiring, "hook_command": hooks_mod._hook_command()}


def _scan_workspace(root: str) -> dict[str, str]:
    """Every real project file under root, path -> content hash. Excludes the
    reticuli store, hidden entries, and Python bytecode -- the same set the
    trace and feedback already treat as the project. A `ret run` scans before
    and after so a command's file effects are captured even when no editor hook
    saw them: content, not mtime, so a rewrite to identical bytes counts as no
    change and a real change is never missed."""
    scan: dict[str, str] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith(".") and d != "__pycache__")
        for name in sorted(files):
            if name.startswith(".") or name.endswith((".pyc", ".pyo")):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                with open(path, "rb") as fh:
                    scan[rel] = _util.hash_bytes(fh.read())
            except OSError:
                continue
    return scan


def run(cmd: str, workspace: str) -> int:
    """A silent wrapper: only the child's streams. The trace records the command
    and the file effects it left -- a before/after content scan of the
    workspace, so work a script or subprocess does is captured even though no
    editor hook saw it. Reads cannot be derived from a content diff, so they
    stay unobserved; the honest-pack warnings say what could not be seen."""
    root = os.path.abspath(workspace)
    trace = os.path.join(root, authoring_mod.TRACE)
    os.makedirs(os.path.dirname(trace), exist_ok=True)
    before = _scan_workspace(root)
    proc = subprocess.run(cmd, shell=True, cwd=root, check=False,
                          env={**os.environ, "RETICULI": "1"})
    after = _scan_workspace(root)
    touched = sorted(rel for rel, h in after.items() if before.get(rel) != h)
    # Stamped and lock-serialized: a swarm of agents and subprocesses appends to
    # this one trace at once, and each event is grouped by its run (see _util).
    _util.trace_append(trace, {"event": "bash", "cmd": cmd, "via": "shell",
                               "rc": proc.returncode})
    for rel in touched:
        _util.trace_append(trace, {"event": "write", "path": rel, "via": "shell"})
    return proc.returncode


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


def _gate_ok(g: dict) -> bool:
    """One gate's verdict. The failure classes are pinned
    (spec/verification.md); the passing spelling is implementation-defined,
    and this kernel spells it `ok`."""
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


def _deciding_words(view: dict) -> str:
    deciding = view.get("deciding")
    if not deciding:
        return "not measured"
    mut = deciding.get("mutation")
    if mut:
        return f"mutation {mut['rate']:.2f} ({mut['mutants']} mutants)"
    return "measured"


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


# -- the output contract (docs/cli-style.md): silence | -v | --json ---------


def _finish(command: str, r: dict, ok: bool, status: str, args,
            rich, terse=None) -> None:
    """One output contract for every verb: the default is `terse` — or, for
    a check succeeding, SILENCE (terse=None prints nothing: the exit code is
    the answer). `-v` is `rich` (the explanatory fact sheets), `--json` the
    envelope. The envelope's stable fields are command/ok/status/root/data;
    everything verb-specific lives under data, because the durable exchange
    object is the claim/record format, not CLI presentation JSON — the
    envelope is the only parse-stable output."""
    if getattr(args, "json", False):
        print(json.dumps({"command": command, "ok": bool(ok), "status": status,
                          "root": r.get("root"), "data": r},
                         indent=2, sort_keys=True))
    elif getattr(args, "verbose", False):
        rich(r)
    elif terse is not None:
        terse(r)


def _line(*parts) -> None:
    print("  ".join(str(p) for p in parts if p not in (None, "")))


def _warn_block(warns) -> None:
    """Honest-partial pack findings, on stderr — the packed root stays on
    stdout. A pack succeeds WITH warnings: the block says what could not be
    established, it does not withhold the claim (the cold re-earn already did
    the deciding). --json carries the same findings under data instead."""
    print("  warnings", file=sys.stderr)
    for w in warns:
        print(f"    {w['detail']}", file=sys.stderr)


def _err(verb: str, fact: str, hint: str | None = None,
         detail: list | None = None) -> None:
    """A failure, git-shaped: `ret: <verb>: <fact>`, optional indented
    detail lines, optional `hint:` — all on stderr, per the style contract."""
    print(f"ret: {verb}: {fact}", file=sys.stderr)
    for line in detail or []:
        print(f"  {line}", file=sys.stderr)
    if hint:
        print(paint(f"hint: {hint}", "hint", stderr=True), file=sys.stderr)


def _rel(path: str) -> str:
    """git's path rule: relative when under the current directory."""
    absd = os.path.abspath(path)
    cwd = os.getcwd()
    if absd == cwd:
        return "."
    if absd.startswith(cwd + os.sep):
        return os.path.relpath(absd, cwd)
    return absd


class _Progress:
    """Long work announces itself on a terminal and cleans up after: a
    stderr line rewritten in place, erased on completion — so the end state
    still honors the silence rule. Pipes and CI never see it."""

    def __init__(self, label: str):
        self.label = label
        self.live = False
        try:
            self.live = sys.stderr.isatty()
        except (AttributeError, ValueError):
            self.live = False

    def __enter__(self):
        if self.live:
            import threading
            self.stop = threading.Event()
            self.t0 = time.monotonic()

            def tick():
                while not self.stop.wait(1.0):
                    line = f"{self.label} {duration(time.monotonic() - self.t0)}"
                    print(f"\r{paint(line, 'meta', stderr=True)}\x1b[K",
                          end="", file=sys.stderr, flush=True)
            self.thread = threading.Thread(target=tick, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *exc):
        if self.live:
            self.stop.set()
            self.thread.join(timeout=2)
            print("\r\x1b[K", end="", file=sys.stderr, flush=True)
        return False


#: The shipped producers, addressable by name: `--producer openai[:model]`.
#: Naming one IS the authorization to hand it its own vendor's credential —
#: only the matched key, only for shipped names, never to gates, and never
#: for a raw command (which keeps the do-it-yourself contract unchanged).
_PRODUCERS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE",
                         "RETICULI_AGENT_TURNS")


def _expand_producer(spec: str):
    """A shipped producer's name becomes its full invocation; anything else
    passes through verbatim. Returns (command, env) — env is what the user's
    naming authorizes us to hand the producer over the scrub.

    Preflight refuses BEFORE any money moves: a missing SDK or credential is
    a one-line answer here, not a traceback from inside the room."""
    import importlib.util
    import re as _re
    import shlex
    m = _re.fullmatch(r"(openai|anthropic)(?::([\w.\-]+))?", spec)
    if not m:
        return spec, None
    name, model = m.groups()
    needs = []
    if importlib.util.find_spec(name) is None:
        needs.append(f"the {name} package (pip install {name})")
    key_var = _PRODUCERS[name]
    if not os.environ.get(key_var):
        needs.append(f"{key_var} in your environment")
    if needs:
        raise kernel.ClaimError(
            f"rebuild: the {name} producer needs: " + "; ".join(needs))
    env = {key_var: os.environ[key_var]}
    for var in _PRODUCER_PASSTHROUGH:
        if os.environ.get(var):
            env[var] = os.environ[var]
    if model:
        env["RETICULI_MODEL"] = model
        os.environ.setdefault("RETICULI_MODEL", model)   # the judge's ledger
    os.environ.setdefault("RETICULI_VENDOR", name)
    # our own package's parent rides PYTHONPATH, and -P keeps the room's
    # files from shadowing it — the producer must import THIS reticuli
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(
        os.path.abspath(kernel.__file__)))
    command = f"{shlex.quote(sys.executable)} -P -m reticuli.producers.{name}"
    return command, env


def _version_line() -> str:
    try:
        from importlib import metadata
        version = metadata.version("reticuli")
    except (ImportError, OSError, metadata.PackageNotFoundError):
        version = "unversioned"
    repo = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    try:
        with open(os.path.join(repo, kernel.MANIFEST), encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("name") == "reticuli" and manifest.get("root"):
            return f"ret {version} (root {short(manifest['root'])})"
    except (OSError, ValueError):
        pass
    return f"ret {version}"


# -- dispatch ----------------------------------------------------------------

_DESC = """\
Reticuli records and reproduces software claims.

Authoring
    init        initialize a workspace
    run         run and observe a command
    status      show work, claims, and unresolved inputs
    pack        create a claim from a project

Composition and transport
    pull        add another claim as a dependency
    export      write a portable claim archive
    import      restore a claim archive

Verification
    verify      verify claim identity
    audit       rerun acceptance criteria
    assess      measure specification strength

Reconstruction
    rebuild     rebuild an implementation from a claim
    crosscheck  compare independent realizations

Evidence
    record      write an execution record
    sign        authorize a claim or proof"""

_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists "
           "everything,\nincluding accepted older spellings.")

#: The fourteen: each survives the test that removing it would erase a
#: distinction, not merely a view. Everything else is an alias or plumbing.
PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")

#: Accepted older spellings — they dispatch, `ret help -a` lists them, the
#: fourteen-verb map does not. Removing each would break invocations without
#: preserving a distinction: their meaning survives inside a porcelain verb.
ALIASES = {"seal": "pack (a session, declared with --accept)",
           "hooks": "init (agent wiring rides initialization)",
           "tree": "status --tree",
           "claims": "status --all (the claim store listing)",
           "attest": "record --key / sign (machine vs human signature)"}

_FULL_HELP = {
    "init": """\
NAME
    ret init — initialize a workspace

SYNOPSIS
    ret init [<path>] [--agent <name> | --no-agent]

DESCRIPTION
    Creates the session store (.reticuli/), the trace file, and git-native
    skin (.gitignore/.gitattributes entries for local residue). When a
    supported coding-agent environment is detected — a .claude/ directory —
    the nonblocking observation hooks are installed idempotently; --agent
    claude forces that, --no-agent skips it. The wired command adapts to how
    reticuli is reachable (the installed `ret`, or this interpreter's `-m
    reticuli` from a source checkout), so hooks are never wired to a command
    that is not there. For any other harness, --agent generic sets up the
    workspace and prints the contract to target: run `ret hook` at each event
    with a JSON event on stdin ({"event":"write"|"read"|"bash"|"prompt", ...}).
    Observation discovers possible dependencies; nothing observed becomes part
    of a claim until declared.

EXIT STATUS
    0 initialized; 1 refused (with a reason); 2 invalid invocation.""",
    "run": """\
NAME
    ret run — run and observe a command

SYNOPSIS
    ret run <command> [-C <workspace>]
    ret run -- <argv>...

DESCRIPTION
    Executes the command in the workspace and appends it to the session
    trace. Useful even when agent hooks are present: it is an explicit,
    human-authored execution boundary. The child's exit code is returned
    unchanged.""",
    "status": """\
NAME
    ret status — where am I, and what's next

SYNOPSIS
    ret status [<path>] [--files] [--tree] [--all] [--json]

DESCRIPTION
    The pure view: status reads and reports, it never executes anything —
    every form is instant. In a draft session it counts the authoring
    triad (observed, declared, unresolved) and names each undeclared
    file. On a sealed claim it shows the recorded state with honest
    dates: identity (a hash comparison), when this machine last EARNED
    the verdicts (audit's receipt — testimony, not a verdict), the
    tests' measured strength (assess's evidence), whether a proof is
    recorded, and what is signed. Every view ends with `next`: the
    first rung of the ladder this claim has not yet earned.

    --files is the per-file account: what each file is to this claim.
    --tree is the dependency and evidence graph. --all is everything on
    one page. Earning a verdict is `ret audit`; measuring the tests is
    `ret assess`; status only ever tells you which is next.

    Observation is not complete provenance, and a receipt is not a
    verdict: status reports what was seen and what is recorded; it
    never implies the rest.

EXIT STATUS
    0 (a view); 1 the path holds no readable state; 2 invalid invocation.""",
    "pack": """\
NAME
    ret pack — create a claim from a project

SYNOPSIS
    ret pack [<path>] [-o <directory>] [--name <name>] [--force]
    ret pack [<path>] --accept <verdict>... -o <directory>       (a session)
    ret pack [<path>] --generated <glob>... --gate <cmd> --output <verdict>
    ret pack [<path>] --generated <glob>... --pytest <dir>

DESCRIPTION
    The single authoring boundary: observed work or a declared project
    becomes a claim. Three sources, one verb:

    - A directory with reticuli.toml and no build flags: the recipe IS the
      declaration; the gates run warm and the claim seals in place. The
      specification belongs in reticuli.toml, not in a growing flag language.
    - A draft session (an observed trace): --accept names the verdict files
      that decide acceptance, -o is where the claim materializes; the gates
      re-run COLD in a clean workspace, so the trace has no authority. A
      session with unresolved observations is refused unless --force.
    - A project declared by flags: --generated (the implementation), --input
      (pinned criteria), --gate/--output or --pytest, plus --environment,
      --component, --requires, --mutation-floor, --inputs-manifest, --by.

    Acceptance criteria must pass before the claim is created, in every path.

EXIT STATUS
    0 packed; 1 the gates or the declaration refused; 2 invalid invocation.""",
    "pull": """\
NAME
    ret pull — add another claim as a dependency

SYNOPSIS
    ret pull <claim> [-C <into>]

DESCRIPTION
    Copies a sealed claim into this workspace's claim store and registers it
    as a dependency. Pull changes the dependency graph; export/import move
    bytes without composition semantics — that is the difference.""",
    "export": """\
NAME
    ret export — write a portable claim archive

SYNOPSIS
    ret export [<claim>] [<archive>] [-o <archive>] [--blind]

DESCRIPTION
    Writes the claim's declared content to a deterministic tar. No
    dependency semantics. --blind writes the rebuilder's room: criteria,
    verdicts, and the manifest travel; the generated implementation stays
    home — the root never covered it, so the room still verifies.
    The archive defaults to <name>.tar in the current directory.""",
    "import": """\
NAME
    ret import — restore a claim archive

SYNOPSIS
    ret import <archive> [<directory>] [-o <directory>]

DESCRIPTION
    Extracts an archive into a new directory and verifies the root from the
    bytes alone. Restores a portable claim without adding it as a
    dependency (that is pull). export and import are as close to inverses
    as practical.

EXIT STATUS
    0 imported and fresh; 1 the extracted bytes do not verify; 2 invalid.""",
    "verify": """\
NAME
    ret verify — verify claim identity

SYNOPSIS
    ret verify [<claim>] [--json]

DESCRIPTION
    Recomputes the claim root from its declared contents and compares it
    with the sealed manifest. Does not execute acceptance criteria — this
    answers "is this still the same claim?", in milliseconds, and nothing
    else. audit answers whether the bytes currently earn the verdict.

OUTPUT
    fresh <root>                       the identity holds
    broken expected=<root> got=<root>  a declared byte changed

EXIT STATUS
    0 fresh; 1 broken; 2 invalid invocation.""",
    "audit": """\
NAME
    ret audit — rerun acceptance criteria

SYNOPSIS
    ret audit [<claim>] [--record [<file>]] [--shallow] [--mutants N]
              [--reuse] [--no-strict] [--json]

DESCRIPTION
    Re-executes every gate in a sandboxed scratch workspace built from the
    claim's declared files: do these bytes currently earn the declared
    verdict? An environment failure (a missing declared requirement, an
    unfurnishable declared environment) is distinct from the claim failing:
    the gates were not run, nothing proven, nothing disproven.

    Auditing is the act of judging bytes, so the gates run under the
    STRICT jail by default: writes confined, network denied, and your
    own files masked — a claim's gates never get to read your home
    directory while you judge them, yours or a stranger's. --no-strict
    opts down to the standard jail. This is the receiving flow: someone
    hands you a claim, `ret audit theirclaim` is the answer, and
    `ret status --all` is the account of what you are trusting.

    An earned audit leaves a dated receipt in the claim's store; status
    reports it (only while the root still matches), and nothing but
    --reuse ever trusts it.

    --record preserves the execution as a portable record (spec/record.md)
    — a convenience; `ret record` remains the full evidence verb.
    --shallow audits this claim only, skipping its component chain.
    --reuse accepts this machine's own prior earned verdict for identical
    bytes, reported as reused, never as earned.

OUTPUT
    earned <root> gates=N/N            every verdict reproduced
    failed gate=<name>                 a criterion rejected the bytes
    environment missing=<what>         this host cannot test the claim

EXIT STATUS
    0 earned (or honestly reused); 1 anything else; 2 invalid invocation.""",
    "assess": """\
NAME
    ret assess — measure specification strength

SYNOPSIS
    ret assess [<claim>] [--mutants N] [--rebuild <producer> [--guided]]
               [--heldout F --heldout-producer NAME=CMD ...] [--json]

DESCRIPTION
    Attacks the specification itself: verify asks whether identity
    survived, audit asks whether this implementation passes, assess asks
    whether the acceptance boundary is meaningful. Measurements include
    fault injection (mutation), gate circularity, blind re-derivation from
    the tests alone (--guided adds a guided control), held-out
    generalization, producer independence, and
    excess cross-producer agreement. Numbers are reported with their
    samples and never collapsed into a grade — the output is evidence for
    refining the specification. Does not change the claim: the root never
    moves; the measurements are left in the store as residue, and
    `ret status --all` reads them back as the claim's DECIDING evidence
    (trusted only while their recorded root still matches).""",
    "rebuild": """\
NAME
    ret rebuild — rebuild an implementation from a claim

SYNOPSIS
    ret rebuild [<claim>] --producer <name>[:<model>] [-o <directory>]
    ret rebuild [<claim>] --producer <command> [-o <directory>]
                [--recursive] [--without-guidance]

DESCRIPTION
    Builds a new implementation from the claim in a blind workspace.
    Generated implementation files from the source realization are
    withheld from the producer — it writes them from the criteria (and, by
    default, the recipe's guidance). --without-guidance withholds the
    hints too, measuring what the criteria alone carry; at claim format 3
    guidance is outside the root, so both target the same root.

    The shipped producers answer to their names: `--producer openai` or
    `--producer anthropic:claude-opus-5`. Naming one authorizes forwarding
    its own vendor's key (OPENAI_API_KEY / ANTHROPIC_API_KEY) from your
    environment — only the matched key, never to gates — and a missing SDK
    or credential refuses in one line before any money moves. Set
    RETICULI_PRICE ("in,out" usd/Mtok) if you want dollars in the ledger;
    without it tokens are recorded and a declared usd envelope reads
    incomplete, honestly. Any other value is run verbatim as a command —
    a producer is any program, a compiler and a Makefile included.

    PRODUCER CONTRACT
    A command producer is run with its working directory set to the blind
    workspace: the criteria and (by default) the recipe's guidance are
    already there, the generated implementation files are not. The command
    must write those implementation files into that directory — that is its
    whole job. Its exit code is ignored; the rebuilt claim is judged only by
    re-running the gates cold, so a producer that writes nothing (or the
    wrong bytes) simply fails to reach the source root. A minimal offline
    producer is a script that emits the withheld file, e.g.
    `--producer "python3 producer.py"` where producer.py writes solver.py.

    A claim can have arbitrarily many rebuilds; disagreement between
    producers is information about the specification. Every gate re-runs;
    the cost is ledgered.""",
    "crosscheck": """\
NAME
    ret crosscheck — compare independent realizations

SYNOPSIS
    ret crosscheck <realization> <realization>... [--record-proof]
                   [--mutants N]

DESCRIPTION
    The three-machine test over realizations of one claim: identity
    equality, byte-level reuse, every machine's verdicts re-earned, the
    declared envelope and mutation floor held. Given exactly two
    directories, the byte-copy leg (M2) is materialized here via
    export/import and said so; given three or more, they are original,
    copy, and rebuilds, each rebuild tested. M1/M2/M3 are roles inferred
    from how realizations were produced, not commands.

    The verdict is three-valued: accept, reject, or incomplete — a
    condition the claim declared but this run did not measure can never
    accept (spec/verification.md).

EXIT STATUS
    0 accept; 1 reject or incomplete; 2 invalid invocation.""",
    "record": """\
NAME
    ret record — write an execution record

SYNOPSIS
    ret record [<claim>] [-o <file>] [--key <ssh_key> | --sign]

DESCRIPTION
    Re-runs the claim's gates and freezes this machine's results as the one
    portable file other programs may parse (spec/record.md): root, build
    digest, per-gate results, environment, cost, producer declaration.
    Records represent failures as well as successes — a negative result is
    still evidence, and the exit code says which kind you hold. --key (or
    --sign, using $RETICULI_KEY) signs the record detached in its own
    namespace: a machine signature means "this execution produced these
    observations" — accountability for an observation, never human
    authorization (that is `ret sign`, and one must not substitute for the
    other).

EXIT STATUS
    0 recorded and earned; 1 recorded a failure; 2 invalid invocation.""",
    "sign": """\
NAME
    ret sign — authorize a claim or proof

SYNOPSIS
    ret sign [<claim>]                        review the packet (no key)
    ret sign [<claim>] --key <ssh_key> --as <identity>
    ret sign [<claim>] --check [--signers <allowed_signers>]

DESCRIPTION
    Human authorization, distinct from machine execution records and their
    signatures: "I reviewed this claim and evidence and accept
    responsibility for it." With no key it emits the review packet — the
    chain and evidence a signer is about to stand behind. With a key it
    authorizes; --check verifies an authorization against a trust anchor.
    A signed machine record never substitutes for this.""",
}


def _add_verbose_json(q) -> None:
    q.add_argument("--json", action="store_true")
    q.add_argument("-v", "--verbose", action="store_true")
    q.add_argument("--color", choices=("auto", "always", "never"), default=None)


def _parser() -> tuple[argparse.ArgumentParser, dict]:
    """The argv grammar, and the verbs it registers.

    Built in one place so the documented map in `_DESC` can be checked against
    what `ret` really dispatches — a verb that exists but is undocumented, or
    documented but absent, is a drift the surface gate catches.
    """
    p = argparse.ArgumentParser(prog="ret", usage="ret <command> [<args>]",
                                description=_DESC, epilog=_EPILOG,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # verbs carry no parser-level help= — the grouped map in _DESC is the one
    # listing (argparse only auto-lists verbs that set help=). Group order and
    # membership are structure, ratified by surface_check; wording stays free.
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")

    def add(name, usage=None, description=None):
        return sub.add_parser(
            name, usage=usage, description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter)

    # -- authoring
    q = add("init", usage="ret init [<path>] [--agent <name> | --no-agent]",
            description="Initialize a Reticuli workspace.\n\n"
                        "When a supported coding-agent environment is detected,\n"
                        "nonblocking observation hooks are installed idempotently.")
    q.add_argument("project", nargs="?", default=".")
    q.add_argument("--agent", default=None, metavar="NAME",
                   help="agent integration: claude (auto-wired), or generic "
                        "for any other harness (targets the `ret hook` contract)")
    q.add_argument("--no-agent", action="store_true",
                   help="do not configure agent integration")
    q = add("run", usage="ret run <command> [-C <workspace>]\n       ret run -- <argv>...",
            description="Run a command and record its execution in the session trace.")
    q.add_argument("command", nargs="*", default=[])
    q.add_argument("-C", "--workspace", default=".")
    q = add("status", usage="ret status [<path>] [--all] [--tree] [--json]",
            description="Show observed work and declared claims.\n\n"
                        "During authoring, status highlights observed but\n"
                        "undeclared or uncovered files. On a sealed claim it\n"
                        "shows identity and recorded evidence; --all is the\n"
                        "full account, --tree the relationships.")
    q.add_argument("workspace", nargs="?", default=".")
    q.add_argument("--all", action="store_true",
                   help="everything, one page: the ledger, the files, the tree")
    q.add_argument("--files", action="store_true",
                   help="the per-file account: what each file is to this claim")
    q.add_argument("--tree", action="store_true",
                   help="dependency and evidence relationships")
    q = add("pack", usage="ret pack [<path>] [-o <directory>] [--name <name>] [--force]",
            description="Create a claim from a project.\n\n"
                        "A directory with reticuli.toml seals in place after its\n"
                        "gates pass warm. A draft session needs --accept and -o;\n"
                        "its gates re-run cold. Explicit declaration flags\n"
                        "(--generated, --gate/--output or --pytest, ...) build\n"
                        "the recipe first. Criteria must pass before a claim\n"
                        "is created.")
    q.add_argument("path", nargs="?", default=".")
    q.add_argument("-o", "--into", default=None, metavar="DIR",
                   help="where the claim materializes (session flow)")
    q.add_argument("--name", default=None,
                   help="the claim's name (default: the directory's)")
    q.add_argument("-C", "--root", dest="root", default=None, metavar="DIR",
                   help="the project directory (older spelling; with it, a "
                        "positional argument is read as the name, as it "
                        "used to be)")
    q.add_argument("--force", action="store_true",
                   help="pack a session despite unresolved observations")
    q.add_argument("--accept", action="append", default=[], metavar="PATH",
                   help="a verdict file that decides acceptance (session flow)")
    q.add_argument("--claim", action="append", default=[], metavar="PATH",
                   help="force a file into the claim (a pinned input), whoever wrote it")
    q.add_argument("--generated", nargs="+", default=None, metavar="GLOB",
                   help="the implementation: files declared generated (project flow)")
    q.add_argument("--input", nargs="*", default=[], metavar="GLOB")
    q.add_argument("--gate", default=None)
    q.add_argument("--output", default=None)
    q.add_argument("--pytest", default=None, metavar="DIR",
                   help="shorthand for an ordinary pytest suite: the gate runs "
                        "`python3 -m pytest -q DIR`, DIR's tests become pinned "
                        "inputs, and the verdict is OK")
    q.add_argument("--environment", default=None, metavar="FILE",
                   help="a hash-pinned requirements file the gates run inside; "
                        "pinned into the root, because dependency versions "
                        "decide what passing means")
    q.add_argument("--component", default=None, metavar="CLAIM",
                   help="a sealed claim this one layers on")
    q.add_argument("--mutation-floor", type=float, default=None, metavar="FLOOR",
                   help="declare the mutation kill rate crosscheck holds a redo to (0..1)")
    q.add_argument("--requires", nargs="*", default=[], metavar="TOOL",
                   help="what the gate needs from the host: a binary, python:module, python>=X.Y")
    q.add_argument("--inputs-manifest", default=None, metavar="FILE",
                   help="write the pinned input list to FILE and declare it (format 2)")
    q.add_argument("--by", default=None, metavar="MODEL",
                   help="who produced the implementation (ledger residue, never identity)")
    # -- composition and transport
    q = add("pull", usage="ret pull <claim> [-C <into>]",
            description="Add another claim as a dependency of the current project.")
    q.add_argument("component")
    q.add_argument("-C", "--into", default=".")
    q = add("export", usage="ret export [<claim>] [<archive>] [--blind]",
            description="Write a portable representation of a claim.\n"
                        "--blind omits the generated implementation: the rebuilder's room.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("tar", nargs="?", default=None)
    q.add_argument("-o", "--out", dest="tar_opt", default=None, metavar="ARCHIVE")
    q.add_argument("--blind", action="store_true",
                   help="the rebuilder's room: omit the generated outputs and "
                        "signing residue; criteria, verdicts, and the manifest travel")
    q = add("import", usage="ret import <archive> [<directory>]",
            description="Restore a portable claim without adding it as a dependency.")
    q.add_argument("tar")
    q.add_argument("into", nargs="?", default=None)
    q.add_argument("-o", "--out", dest="into_opt", default=None, metavar="DIR")
    # -- verification
    q = add("verify", usage="ret verify [<claim>] [--json]",
            description="Verify the identity of a claim.\n\n"
                        "Recomputes the claim root from its declared contents.\n"
                        "Does not execute acceptance criteria.")
    q.add_argument("claim", nargs="?", default=".")
    q = add("audit", usage="ret audit [<claim>] [--record [<file>]] [--json]",
            description="Rerun a claim's acceptance criteria, cold and sandboxed.\n\n"
                        "Gates run under the STRICT jail: a claim's gates never\n"
                        "get to read your own files while you judge them.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--no-strict", action="store_true",
                   help="run the gates under the standard jail instead of the "
                        "strict one (which masks your own files from them)")
    q.add_argument("--record", nargs="?", const=True, default=None, metavar="FILE",
                   help="preserve the execution as a record")
    q.add_argument("--shallow", action="store_true",
                   help="this claim's gates only (default: the whole component chain)")
    q.add_argument("--mutants", type=int, default=0, metavar="N",
                   help="also mutate the generated code N times and report the check's kill rate")
    q.add_argument("--reuse", action="store_true",
                   help="skip the gates if THIS machine already earned this exact claim, "
                        "these exact generated bytes, and this environment (off by "
                        "default: a stored verdict is never trusted)")
    q = add("assess", usage="ret assess [<claim>] [<options>]",
            description="Measure how strongly a claim constrains implementations.\n\n"
                        "May evaluate fault detection, re-derivation, held-out\n"
                        "behavior, and producer agreement. Does not change the claim.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--mutants", type=int, default=assess_mod.DEFAULT_MUTANTS, metavar="N",
                   help="how many faults to inject (default: %(default)s)")
    q.add_argument("--rebuild", metavar="PRODUCER",
                   help="ask this producer to rebuild BLIND, from the tests alone (costs money)")
    q.add_argument("--rebuild-into", metavar="DIR",
                   help="keep the blind rebuild workspace here instead of a temp dir")
    q.add_argument("--guided", action="store_true",
                   help="also run a guided rebuild (the recipe's hint is kept) as a "
                        "control: guided passing while blind fails points at the "
                        "tests, not the producer")
    q.add_argument("--corpus", metavar="FILE",
                   help="record this run into a reference corpus and report where "
                        "it sits in the population (residue; never changes identity)")
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
    # -- reconstruction
    q = add("rebuild", usage="ret rebuild [<claim>] --producer <command> [-o <directory>]",
            description="Build a new implementation from a claim.\n\n"
                        "Generated implementation files from the source realization\n"
                        "are withheld from the producer.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--producer", required=True,
                   help="command used to produce the implementation")
    q.add_argument("-o", "--into", required=True, metavar="DIR",
                   help="destination for the rebuilt project")
    q.add_argument("--recursive", action="store_true",
                   help="DAG-aware: also rebuild component dependencies, bottom-up")
    q.add_argument("--without-guidance", action="store_true",
                   help="hand the producer the outputs to write but NOT the "
                        "hints for how: a pass then measures what the criteria "
                        "alone carry (format 3, where guidance is not in the root)")
    q = add("crosscheck", usage="ret crosscheck <realization> <realization>...",
            description="Compare realizations of the same claim.\n\n"
                        "Checks claim identity, earned criteria, implementation\n"
                        "reuse, and available provenance evidence. With exactly\n"
                        "two, the byte-copy leg is materialized here and said so.")
    q.add_argument("machines", nargs="+", metavar="realization")
    q.add_argument("--record-proof", action="store_true",
                   help="record the three-machine proof on M1 (residue; signed is the "
                        "signing ceremony's)")
    q.add_argument("--mutants", type=int, default=30, metavar="N",
                   help="mutants for the mutation floor, when the claim declares one")
    # -- evidence
    q = add("record", usage="ret record [<claim>] [-o <file>] [--key <ssh_key> | --sign]",
            description="Write a portable execution record.\n\n"
                        "Records may describe successful or failed executions.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("-o", "--out", default=None, metavar="FILE",
                   help="where to write the record (default: <name>.record.json here)")
    q.add_argument("--key", default=None, metavar="SSH_KEY",
                   help="also sign the record, detached, in the reticuli.record namespace")
    q.add_argument("--sign", action="store_true",
                   help="sign with the configured identity ($RETICULI_KEY)")
    q = add("sign", usage="ret sign [<claim>] [--key <ssh_key> --as <identity>] [--check]",
            description="Authorize a claim and its evidence.\n\n"
                        "A human authorization, distinct from machine execution\n"
                        "records and their signatures.")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--key", default=None, metavar="SSH_KEY")
    q.add_argument("--as", dest="identity", default=None, metavar="IDENTITY")
    q.add_argument("--check", action="store_true")
    q.add_argument("--signers", default=None, metavar="ALLOWED_SIGNERS")

    # -- aliases: accepted older spellings (unlisted; `ret help -a` names them)
    q = add("seal")
    q.add_argument("session", nargs="?", default=".")
    q.add_argument("--accept", action="append", default=[], metavar="PATH", required=True)
    q.add_argument("--into", required=True)
    q.add_argument("--name", default=None)
    q.add_argument("--claim", action="append", default=[], metavar="PATH")
    q.add_argument("--generated", action="append", default=[], metavar="PATH")
    q.add_argument("--mutation-floor", type=float, default=None, metavar="FLOOR")
    q.add_argument("--requires", nargs="*", default=[], metavar="TOOL")
    q.add_argument("--inputs-manifest", default=None, metavar="FILE")
    q.add_argument("--by", default=None, metavar="MODEL")
    add("hooks").add_argument("project", nargs="?", default=".")
    add("tree").add_argument("workspace", nargs="?", default=".")
    add("claims").add_argument("workspace", nargs="?", default=".")
    q = add("attest")
    q.add_argument("claim", nargs="?", default=".")
    q.add_argument("--key", default=None, metavar="SSH_KEY")
    q.add_argument("--as", dest="identity", default=None, metavar="IDENTITY")
    q.add_argument("--check", action="store_true")
    q.add_argument("--signers", default=None, metavar="ALLOWED_SIGNERS")
    # -- plumbing: agent event sink (invoked by installed hooks), help,
    #    and shell completion, generated from this parser so it cannot drift
    q = add("hook")
    q.add_argument("-C", "--workspace", default=None)
    q = add("completion", usage="ret completion bash|zsh")
    q.add_argument("shell", choices=("bash", "zsh"))
    q = add("help", usage="ret help [<command>] [-a]",
            description="Detailed help for a command; -a lists the whole "
                        "command set,\nincluding accepted older spellings and plumbing.")
    q.add_argument("topic", nargs="?", default=None)
    q.add_argument("-a", "--all", action="store_true")

    for name in (*PORCELAIN, *ALIASES):
        if name not in ("run",):        # run's output is the child's, verbatim
            _add_verbose_json(sub.choices[name])
    return p, sub.choices


def verbs() -> list[str]:
    """Every verb `ret` accepts, in declaration order — the parser is the source."""
    return list(_parser()[1])


def _help_topic(topic: str) -> int:
    if topic in _FULL_HELP:
        print(_FULL_HELP[topic])
        return 0
    if topic in ALIASES:
        print(f"`ret {topic}` is an accepted older spelling of: {ALIASES[topic]}\n"
              f"See `ret help {ALIASES[topic].split()[0]}`.")
        return 0
    if topic == "hook":
        print("ret hook — plumbing: the agent event sink. Installed hooks pipe\n"
              "their payloads here; it appends trace events and prints nothing.")
        return 0
    if topic == "completion":
        print("ret completion bash|zsh — plumbing: print a shell completion\n"
              "script, generated from the parser itself. Install with e.g.\n"
              "    ret completion bash > ~/.local/share/bash-completion/completions/ret")
        return 0
    if topic == "environment":
        print("""\
ENVIRONMENT VARIABLES

Presentation
    RETICULI_COLOR       auto | always | never (--color overrides)
    NO_COLOR             any value disables color (the standard)

Evidence and identity
    RETICULI_KEY         private ssh key `record --sign` uses
    RETICULI_SIGNERS     allowed-signers file for --check verbs

Producers (read inside the scrubbed rebuild environment)
    RETICULI_MODEL       model a shipped producer drives
    RETICULI_PRICE       "in,out" usd per Mtok, so the ledger prices tokens;
                         unset means tokens-only (there is no built-in
                         price table — tables drift)
    RETICULI_AGENT_TURNS producer tool-loop cap (default 40)
    OPENAI_API_KEY / ANTHROPIC_API_KEY / OPENAI_BASE_URL
                         vendor credentials. A NAMED producer
                         (--producer openai) forwards its own vendor's key
                         from your environment automatically; a raw
                         command producer must inject it itself
                         (`. keyfile && exec ...`) — the scrub strips
                         inherited secrets by design, and gates never see
                         any of this either way

Hosts
    RETICULI_ENV_CACHE   where furnished environments are cached
    RETICULI_GATE_TIMEOUT / RETICULI_TOLERANCE
                         host ceilings; a claim can tighten, never loosen

The scrub is the point: a gate or producer sees an allowlist (PATH, HOME,
TMPDIR, LANG, LC_ALL, TZ) plus what reticuli itself sets — inherited
secrets never reach a stranger's gate.""")
        return 0
    print(f"ret: no help for {topic!r} (try `ret help -a`)", file=sys.stderr)
    return 2


def _help_all() -> int:
    print(_DESC)
    print("\nAccepted older spellings (aliases; the fourteen are the grammar)")
    for name, meaning in ALIASES.items():
        print(f"    {name:<11} -> {meaning}")
    print("\nPlumbing\n    hook        agent event sink (invoked by installed hooks)"
          "\n    help        this listing; `ret help <command>` for detail"
          "\n    completion  shell completion script (bash|zsh), from the parser"
          "\n\nTopics\n    environment `ret help environment`: every variable the "
          "tool reads")
    return 0


def _completion(shell: str) -> int:
    """A completion script generated from the one parser, so the shell can
    never disagree with the grammar."""
    _, choices = _parser()
    verbs = [n for n in choices if n != "hook"]
    flags = {n: " ".join(sorted({s for a in choices[n]._actions
                                 for s in a.option_strings}))
             for n in verbs}
    if shell == "bash":
        arms = "\n".join(f'    {n}) COMPREPLY=($(compgen -W "{flags[n]}" -- "$cur"));;'
                         for n in verbs)
        print(f"""_ret() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}"
  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=($(compgen -W "{' '.join(verbs)}" -- "$cur")); return
  fi
  case "${{COMP_WORDS[1]}}" in
{arms}
  esac
  if [ "${{#COMPREPLY[@]}}" -eq 0 ] || [ "${{cur:0:1}}" != "-" ]; then
    COMPREPLY+=($(compgen -o default -- "$cur"))
  fi
}}
complete -F _ret ret""")
        return 0
    arms = "\n".join(f'    {n}) _arguments -- ; compadd -- {flags[n]} ;;'
                     for n in verbs)
    print(f"""#compdef ret
_ret() {{
  if (( CURRENT == 2 )); then
    compadd -- {' '.join(verbs)}
    return
  fi
  case "$words[2]" in
{arms}
  esac
  _files
}}
_ret""")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--version", "-V"):
        print(_version_line())
        return 0
    if not argv:
        # bare `ret`: show the command map, the way `git` does — the classic
        # first move should teach the verbs, not print an argparse error with
        # nothing to act on.
        p, _ = _parser()
        print(p.format_help())
        return 0
    # `-h` is concise usage (argparse); `--help` and `ret help` are the fuller
    # account — the conventional two-level help of mature Unix tools.
    if "--help" in argv:
        head = argv[0] if argv and not argv[0].startswith("-") else None
        if head and (head in _FULL_HELP or head in ALIASES or head == "hook"):
            return _help_topic(head)
        p, _ = _parser()
        print(p.format_help())
        return 0
    p, choices = _parser()
    if argv and not argv[0].startswith("-") and argv[0] not in choices:
        # git-shaped: name the mistake, suggest the near misses, exit 2
        import difflib
        close = difflib.get_close_matches(
            argv[0], sorted(set(choices) - {"hook"}), n=3, cutoff=0.6)
        print(f"ret: {argv[0]!r} is not a ret command. See 'ret -h'.",
              file=sys.stderr)
        if close:
            render.init_color(None)
            print(paint("hint: the most similar "
                        + ("commands are: " if len(close) > 1 else "command is: ")
                        + ", ".join(close), "hint", stderr=True), file=sys.stderr)
        return 2
    args = p.parse_args(argv)
    render.init_color(getattr(args, "color", None))
    render.FULL_HASHES = bool(getattr(args, "verbose", False))
    j = getattr(args, "json", False)
    try:
        if args.cmd == "help":
            if args.all:
                return _help_all()
            if args.topic:
                return _help_topic(args.topic)
            print(p.format_help())
            return 0
        if args.cmd == "init":
            if args.agent not in (None, "claude", "generic"):
                # a value the grammar does not know is an invalid invocation
                print(f"ret: init: unsupported agent {args.agent!r} "
                      "(supported: claude, generic)", file=sys.stderr)
                return 2
            r = init(args.project, agent=args.agent, no_agent=args.no_agent)
            _finish("init", r, True, "initialized", args, _r_init, _t_init)
            return 0
        if args.cmd == "completion":
            return _completion(args.shell)
        if args.cmd == "hook":
            hooks_mod.consume(args.workspace)   # silent: hook stdout can leak into the agent
            return 0
        if args.cmd == "hooks":
            r = hooks_mod.install(args.project)
            _finish("hooks", r, True, r["status"], args, _r_hooks,
                    lambda r: _line("wired", r["settings"]))
            return 0
        if args.cmd == "run":
            cmd = " ".join(args.command)
            if not cmd.strip():
                print("ret: run: needs a command", file=sys.stderr)
                return 2
            return run(cmd, args.workspace)
        if args.cmd in ("pack", "seal"):
            return _dispatch_pack(args, j)
        if args.cmd == "verify":
            r = _verified(args.claim)
            _finish("verify", r, r["ok"], "fresh" if r["ok"] else "broken", args,
                    _r_verify)          # a passing check is silent
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
        if args.cmd == "audit":
            return _dispatch_audit(args)
        if args.cmd in ("status", "tree", "claims"):
            return _dispatch_status(args)
        if args.cmd == "assess":
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
                if mut:
                    bits.append(f"mutation={mut['rate']:.2f}")
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
            _finish("assess", r, True, "measured", args, _r_assess, _terse_assess)
            return 0
        if args.cmd == "rebuild":
            producer, penv = _expand_producer(args.producer)
            with _Progress("rebuild: producer running"):
                if args.recursive:
                    r = registry_mod.rebuild_chain(args.claim, producer,
                                                   args.into, producer_env=penv)
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
        if args.cmd == "crosscheck":
            return _dispatch_crosscheck(args)
        if args.cmd == "pull":
            r = registry_mod.pull(args.component, args.into)
            _finish("pull", r, True, "pulled", args, _r_pull)   # target was named
            return 0
        if args.cmd == "attest":
            if args.check:
                r = attest_mod.check(args.claim, args.signers)
                _finish("attest", r, r["ok"], "attested" if r["ok"] else "unattested",
                        args, _r_attest_check)     # a passing check is silent
                if not r["ok"] and not j:
                    _err("attest", "unattested — no signature matches these bytes",
                         hint="re-attest the current build: ret attest --key "
                              "<ssh_key> --as <identity>")
                return 0 if r["ok"] else 1
            if not args.key or not args.identity:
                print("ret: attest needs --key and --as (or --check)", file=sys.stderr)
                return 2
            r = attest_mod.attest(args.claim, args.key, args.identity)
            _finish("attest", r, True, "attested", args, _r_attest)
            return 0
        if args.cmd == "sign":
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
        if args.cmd == "export":
            tar = args.tar_opt or args.tar
            if not tar:
                tar = kernel.read_manifest(args.claim)["name"] + ".tar"
            r = transfer_mod.export(args.claim, tar, blind=args.blind)
            if tar == "-":              # the archive owns stdout; say nothing
                return 0
            _finish("export", r, True, "exported", args, _r_export)
            return 0
        if args.cmd == "record":
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
            # a failing gate still records -- the failure is evidence -- but
            # the exit code tells a script which kind of record it is holding
            if not r["earned"] and not j:
                _err("record", "failed — the gates did not pass "
                     f"(recorded anyway: {out})",
                     hint="a negative result is still evidence; the record "
                          "carries the per-gate detail")
            return 0 if r["earned"] else 1
        if args.cmd == "import":
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
    except kernel.ClaimError as e:
        # one voice for every refusal: `ret: <verb>: <fact>`, never doubled
        # when the layer below already named the verb
        msg = str(e)
        if msg.startswith(f"{args.cmd}: "):
            msg = msg[len(args.cmd) + 2:]
        if j:
            # the envelope holds on the refusal path too: ok:false on stdout,
            # stderr empty, so `ret <verb> --json | jq` never chokes on an empty
            # stdout for the "is this even a claim?" refusals automation hits
            # first. A `hint:` line, if the fact carried one, rides under data.
            fact, _, hint = msg.partition("\nhint:")
            data = {"error": fact.strip()}
            if hint.strip():
                data["hint"] = hint.strip()
            print(json.dumps({"command": args.cmd, "ok": False,
                              "status": "error", "root": None, "data": data},
                             indent=2, sort_keys=True))
        else:
            print(f"ret: {args.cmd}: {msg}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:               # a grown tool dies quietly: 128+SIGINT
        print(file=sys.stderr)
        return 130
    except BrokenPipeError:                 # `ret … | head`: the reader left; not an error
        try:
            # silence the interpreter's own flush at exit
            sys.stdout = open(os.devnull, "w")   # noqa: SIM115
        except OSError:
            pass
        return 0
    return 2


# -- the composite dispatches ------------------------------------------------


def _dispatch_pack(args, j: bool) -> int:
    """One authoring boundary. A declared project (reticuli.toml, no build
    flags) seals in place after its gates pass warm; a draft session needs
    --accept and -o and its gates re-run cold; declaration flags build the
    recipe first. The `seal` alias is the session flow under its old grammar."""
    if args.cmd == "seal":
        r = authoring_mod.build_claim(args.session, args.accept, args.into, args.name,
                                      args.claim, args.generated, args.mutation_floor,
                                      args.requires)
        r.setdefault("into", args.into)
        _finish("seal", r, True, "packed", args, _r_seal,
                lambda r: _line("packed", paint(short(r["root"]), "hash")))
        return 0
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
    dates, --files the per-file account, --tree the relationships, --all
    everything on one page — all instant. Earning verdicts is audit's
    identity; the tree/claims spellings are aliases into these views."""
    target = getattr(args, "workspace", None) or getattr(args, "claim", ".")
    if not os.path.isdir(os.path.abspath(target)):
        # a missing path is a refusal, never a fictional empty draft
        raise kernel.ClaimError(f"{args.cmd}: no such directory: {target}")
    if args.cmd == "claims":
        ws = os.path.abspath(args.workspace)
        r = {"workspace": ws, "claims": registry_mod.claims(ws)}
        _finish("claims", r, True, "listed", args, _r_claims, _r_claims)
        return 0
    if args.cmd == "tree" or getattr(args, "tree", False):
        ws = os.path.abspath(args.workspace)
        if _phase(ws) == "draft":
            r = feedback_mod.advise(ws)
            if registry_mod.claims(ws):        # the component DAG of the claim store
                r["deps"] = registry_mod.deps(ws)
            _finish("status" if args.cmd == "status" else "tree", r, True,
                    "draft", args, _r_tree, _r_tree)
            return 0
        r = registry_mod.structure(ws)
        _finish("status" if args.cmd == "status" else "tree", r, True,
                "claim", args, _r_structure, _r_structure)
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
            _r_crosscheck)              # an accepted test is silent
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


if __name__ == "__main__":
    sys.exit(main())
