"""The closure check: the gate must not consume what no check exercises.

The succession's central finding: pinned machinery consumed names from the
generated package that no criterion exercised, so a conforming
implementation — one that satisfies every check — could still fail the
gate's own scripts. The gate was not closed over the equivalence class it
names. This check makes closure testable:

    for every (module, name) and (module, name, keyword) that a PINNED file
    consumes from the generated package, the check of the layer that OWNS
    that module must exercise the same name (and keyword).

Consumers are the repository's pinned .py inputs (criteria, gate.py,
scripts/selfclaim.py). Ownership comes from the layer chain
(scripts/selfclaim.py); a criterion that is itself a layer's check
trivially exercises what it consumes from its own layer, so the teeth are
in the CROSS-layer consumption — selfclaim using pack, a criterion using
the kernel, and so on.

Validated against history: at the root before click A, selfclaim consumed
``pack(..., gate_output=, component=, envelope=, claim_format=)`` while
authoring_check exercised pack positionally only — this check must FLAG
that revision and PASS the present one. Run with ``--rev <git-rev>`` to
judge any committed boundary.

Research tooling today; the staged transition promotes it into criteria/
so closure stops being an audit finding and becomes a property the gate
enforces. Nothing here moves a root.
"""
import argparse
import ast
import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def _read(rev: str | None, relpath: str) -> str | None:
    """A file's bytes at a git revision, or from the working tree."""
    if rev is None:
        p = REPO / relpath
        return p.read_text(encoding="utf-8") if p.is_file() else None
    r = subprocess.run(["git", "show", f"{rev}:{relpath}"], cwd=str(REPO),
                       capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


def _layers(rev: str | None) -> list:
    """The layer chain as declared at that revision."""
    text = _read(rev, "scripts/selfclaim.py")
    ns: dict = {}
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "LAYERS"
                for t in node.targets):
            ns["LAYERS"] = ast.literal_eval(node.value)
    return ns["LAYERS"]


def _module_owner(rev: str | None) -> dict:
    """src module name (e.g. 'pack', 'kernel', '_kernel.core') -> the check
    file of the layer that owns it."""
    owner = {}
    for name, adds, check, _verdict in _layers(rev):
        for rel in adds:
            mod = rel[:-3].replace("/", ".")          # pack.py -> pack
            owner[mod] = check
    return owner


def _consumption(text: str) -> dict:
    """What this file consumes from the reticuli package: a map of
    module -> {"names": set, "kwargs": {name: set-of-keywords}}. Tracks
    `from reticuli import X` aliases and attribute/call use on them, plus
    `from reticuli.mod import name` directly."""
    tree = ast.parse(text)
    aliases: dict = {}                # local alias -> module name
    out: dict = defaultdict(lambda: {"names": set(),
                                     "kwargs": defaultdict(set)})
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[0] != "reticuli":
                continue
            if len(parts) == 1:
                for a in node.names:   # from reticuli import kernel, pack
                    aliases[a.asname or a.name] = a.name
            else:                      # from reticuli.mod import name
                mod = ".".join(parts[1:])
                for a in node.names:
                    out[mod]["names"].add(a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("reticuli."):
                    aliases[a.asname or a.name.split(".")[-1]] = \
                        ".".join(a.name.split(".")[1:])
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and \
                isinstance(node.value, ast.Name) and \
                node.value.id in aliases:
            out[aliases[node.value.id]]["names"].add(node.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in aliases:
            mod, name = aliases[node.func.value.id], node.func.attr
            for kw in node.keywords:
                if kw.arg:
                    out[mod]["kwargs"][name].add(kw.arg)
    return out


def _pinned_py(rev: str | None) -> list:
    """The repository claim's pinned .py files at that revision."""
    recipe = tomllib.loads(_read(rev, "reticuli.toml"))
    pinned = [i for i in recipe["claim"]["inputs"] if i.endswith(".py")]
    for extra in ("gate.py",):
        if extra not in pinned:
            pinned.append(extra)
    return pinned


def closure(rev: str | None = None) -> dict:
    """Every cross-layer consumption a pinned file makes, judged against
    what the owning layer's check exercises."""
    owner = _module_owner(rev)
    consumers, exercised = {}, {}
    for rel in _pinned_py(rev):
        text = _read(rev, rel)
        if text is None:
            continue
        try:
            consumers[rel] = _consumption(text)
        except SyntaxError:
            continue
    for check in set(owner.values()):
        text = _read(rev, check)
        exercised[check] = _consumption(text) if text else {}

    violations = []
    for rel, cons in consumers.items():
        for mod, use in cons.items():
            check = owner.get(mod)
            if check is None:
                continue                  # producers/, reference: no layer owns
            if rel == check:
                continue                  # a layer's own check exercises itself
            ex = exercised.get(check, {}).get(mod, {"names": set(),
                                                    "kwargs": {}})
            for name in sorted(use["names"] - set(ex["names"])):
                if name.startswith("__"):
                    continue
                violations.append({"consumer": rel, "module": mod,
                                   "name": name, "kind": "name",
                                   "owning_check": check})
            for fn, kws in use["kwargs"].items():
                have = set(ex["kwargs"].get(fn, set()))
                for kw in sorted(set(kws) - have):
                    violations.append({"consumer": rel, "module": mod,
                                       "name": f"{fn}(..., {kw}=)",
                                       "kind": "kwarg", "owning_check": check})
    return {"rev": rev or "worktree", "violations": violations}


def report(result: dict) -> None:
    v = result["violations"]
    print(f"closure @ {result['rev']}: "
          f"{'CLOSED' if not v else str(len(v)) + ' unexercised consumptions'}")
    by = defaultdict(list)
    for x in v:
        by[(x["consumer"], x["module"], x["owning_check"])].append(x["name"])
    for (consumer, mod, check), names in sorted(by.items()):
        print(f"  {consumer} consumes reticuli.{mod}: "
              f"{', '.join(names)}")
        print(f"      not exercised by {check}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default=None,
                    help="judge a committed boundary (default: worktree)")
    ap.add_argument("--json", metavar="FILE")
    a = ap.parse_args()
    r = closure(a.rev)
    report(r)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2, sort_keys=True))
    sys.exit(0 if not r["violations"] else 1)
