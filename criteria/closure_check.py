"""closure conformance gate — the gate consumes nothing no check exercises.

The succession run of 2026-09-29 regrew this whole tool blind, twice, and
found that conforming implementations — ones satisfying every layer suite —
still failed the repository's own machinery, because PINNED files consumed
names from the generated package that no criterion exercised. The gate was
not closed over the equivalence class it names: scripts/selfclaim.py called
pack with keyword names authoring_check never used, and a regrown pack,
conforming, had different ones.

This criterion makes closure a property the gate enforces rather than an
audit finding:

    for every name — and every call keyword — that a pinned file consumes
    from the generated package, the check of the layer that OWNS that
    module must exercise the same name (and keyword).

Consumers are the repository's pinned .py inputs (the criteria, gate.py,
scripts/selfclaim.py). Ownership comes from the layer chain declared in
scripts/selfclaim.py. A criterion that is a layer's own check trivially
exercises what it consumes from its own layer; the teeth are in CROSS-layer
consumption. Modules no layer owns (producers/, reference.py — judged by
vectors_check, outside the chain) are out of scope here.

Validated against history before promotion (research/harness/closure/): at
the boundary before click A this flags exactly the pack seam the
succession found by regrowing the tool — and it found the MANIFEST/ledger/
RECIPE gaps that kernel_check pins as of the same transition that
promoted this file. Static, so it runs in seconds, every time, over
whatever boundary is in the room.
"""
import ast
import os
import sys
import tomllib
from collections import defaultdict


def _read(relpath: str) -> str | None:
    return open(relpath, encoding="utf-8").read() \
        if os.path.isfile(relpath) else None


def _layers() -> list:
    """The layer chain as declared beside this boundary."""
    tree = ast.parse(_read("scripts/selfclaim.py"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "LAYERS"
                for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("scripts/selfclaim.py declares no LAYERS")


def _module_owner() -> dict:
    owner = {}
    for _name, adds, check, _verdict in _layers():
        for rel in adds:
            owner[rel[:-3].replace("/", ".")] = check
    return owner


def _consumption(text: str) -> dict:
    """module -> names and call keywords this file consumes from reticuli."""
    tree = ast.parse(text)
    aliases: dict = {}
    out: dict = defaultdict(lambda: {"names": set(),
                                     "kwargs": defaultdict(set)})
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[0] != "reticuli":
                continue
            if len(parts) == 1:
                for a in node.names:
                    aliases[a.asname or a.name] = a.name
            else:
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
                isinstance(node.value, ast.Name) and node.value.id in aliases:
            out[aliases[node.value.id]]["names"].add(node.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in aliases:
            mod, name = aliases[node.func.value.id], node.func.attr
            for kw in node.keywords:
                if kw.arg:
                    out[mod]["kwargs"][name].add(kw.arg)
    return out


def main() -> int:
    with open("reticuli.toml", "rb") as f:
        recipe = tomllib.load(f)
    pinned = [i for i in recipe["claim"]["inputs"] if i.endswith(".py")]
    if "gate.py" not in pinned:
        pinned.append("gate.py")

    owner = _module_owner()
    consumers, exercised = {}, {}
    for rel in pinned:
        text = _read(rel)
        if text is not None:
            consumers[rel] = _consumption(text)
    for check in set(owner.values()):
        text = _read(check)
        exercised[check] = _consumption(text) if text else {}

    violations = []
    for rel, cons in sorted(consumers.items()):
        for mod, use in sorted(cons.items()):
            check = owner.get(mod)
            if check is None or rel == check:
                continue
            ex = exercised.get(check, {}).get(
                mod, {"names": set(), "kwargs": {}})
            for name in sorted(use["names"] - set(ex["names"])):
                if name.startswith("__"):
                    continue
                violations.append(
                    f"{rel} consumes reticuli.{mod}.{name}, "
                    f"which {check} never exercises")
            for fn, kws in sorted(use["kwargs"].items()):
                have = set(ex["kwargs"].get(fn, set()))
                for kw in sorted(set(kws) - have):
                    violations.append(
                        f"{rel} calls reticuli.{mod}.{fn}(..., {kw}=), "
                        f"a keyword {check} never exercises")

    assert not violations, (
        "the gate is not closed over its class — pinned files consume "
        "surface no check exercises, so a conforming implementation can "
        "fail the gate's own machinery:\n  " + "\n  ".join(violations))
    print(f"closure-ok ({len(consumers)} pinned consumers, "
          f"{len(owner)} owned modules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
