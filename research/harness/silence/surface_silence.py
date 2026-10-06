"""The surface silence map: the tool's own layers, sampled as a class.

The behavioral silence map probes a parser with inputs. A layer's
behavior surface is its API — the names it defines, their signatures and
call keywords, its constants' values — and the repository now holds FIVE
complete gate-passing implementations of every layer: the shipped source
and four blind lineages (two families, before and after clicks A/J).
Where they disagree about the surface is the layers' measured silence:
every such divergence is a seam a consumer could be leaning on with
nothing but the model prior holding it up — exactly the species the
succession found by regrowing the tool, found here statically.

Divergent items are ranked by CONSUMPTION, because a silent seam only
bites when something stands on it: tier 1 is divergent-and-consumed (by a
pinned file, or by another module of the shipped package — the
generated-to-generated seams of proposal specimen D), tier 2 is divergent
public surface nobody consumes, tier 3 divergent private surface
(counted, lightly reported).

    python3 surface_silence.py [--json FILE]

Research tooling — nothing here moves a root.
"""
import argparse
import ast
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

IMPLEMENTATIONS = {
    "original": REPO / "src/reticuli",
    "codex-g1": REPO / "research/harness/succession/lineages/codex/tree",
    "claude-g1": REPO / "research/harness/succession/lineages/claude/tree",
    "codex-r2": REPO / "research/harness/succession/lineages-r2/codex/tree",
    "claude-r2": REPO / "research/harness/succession/lineages-r2/claude/tree",
    "codex-r3": REPO / "research/harness/succession/lineages-r3/codex/tree",
    "claude-r3": REPO / "research/harness/succession/lineages-r3/claude/tree",
    "codex-r4": REPO / "research/harness/succession/lineages-r4/codex/tree",
    "codex-r5": REPO / "research/harness/succession/lineages-r5/codex/tree",
    "codex-r6": REPO / "research/harness/succession/lineages-r6/codex/tree",
    "codex-r7": REPO / "research/harness/succession/lineages-r7/codex/tree",
}

_spec = importlib.util.spec_from_file_location(
    "selfclaim", REPO / "scripts" / "selfclaim.py")
_selfclaim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_selfclaim)
MODULES = [rel[:-3].replace("/", ".")
           for _n, adds, _c, _v in _selfclaim.LAYERS for rel in adds]
# reference predates its own layer: this append included reference.py in the
# map before the chain carried it (pre 2026-10-04). Now LAYERS lists it too,
# so dedupe — a duplicate entry double-counts every one of its surface items
# (caught 2026-10-05 reproducing the succession-r3 record's numbers).
MODULES = list(dict.fromkeys([*MODULES, "reference"]))


# -- surface extraction --------------------------------------------------------

def _sig(fn: ast.FunctionDef) -> str:
    """A signature as consumers feel it: names, defaults, stars."""
    a = fn.args
    parts = [x.arg for x in a.posonlyargs] + (["/"] if a.posonlyargs else [])
    ndef = len(a.defaults)
    for i, x in enumerate(a.args):
        d = "=·" if i >= len(a.args) - ndef else ""
        parts.append(x.arg + d)
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        parts.append("*")
    for x, d in zip(a.kwonlyargs, a.kw_defaults):
        parts.append(x.arg + ("=·" if d is not None else ""))
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    return "(" + ", ".join(parts) + ")"


def _const(node: ast.AST) -> str:
    try:
        v = ast.literal_eval(node)
        r = repr(v)
        return r if len(r) <= 60 else f"<{type(v).__name__} len {len(r)}>"
    except (ValueError, TypeError, SyntaxError):
        # not a literal — compare the expression text itself, so a constant
        # like KINDS = frozenset({...}) still shows its content divergence
        # (the succession's KINDS seam was a VALUE difference)
        text = ast.unparse(node)
        return text if len(text) <= 60 else text[:57] + "..."


def surface(path: Path) -> dict:
    """{name: descriptor} for one module's top level."""
    out = {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = "def" + _sig(node)
        elif isinstance(node, ast.ClassDef):
            methods = sorted(n.name for n in node.body
                             if isinstance(n, ast.FunctionDef))
            out[node.name] = "class{" + ",".join(methods) + "}"
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = "= " + _const(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.value is not None:
            out[node.target.id] = "= " + _const(node.value)
    return out


# -- consumption (who stands on a name) ----------------------------------------

def _consumption(text: str, consumer_mod: str | None) -> dict:
    """(module -> names and call-keywords consumed), following absolute
    reticuli imports and — inside the package — relative ones."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    aliases: dict = {}
    out: dict = defaultdict(lambda: {"names": set(),
                                     "kwargs": defaultdict(set)})
    pkg = consumer_mod.split(".")[:-1] if consumer_mod else []

    def resolve(level: int, module: str | None) -> list:
        if level == 0:
            if not module or module.split(".")[0] != "reticuli":
                return []
            return module.split(".")[1:]
        base = pkg[:len(pkg) - (level - 1)] if level - 1 <= len(pkg) else None
        if base is None:
            return []
        return base + (module.split(".") if module else [])

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            target = resolve(node.level, node.module)
            if node.level == 0 and not target and node.module != "reticuli":
                continue
            if node.module == "reticuli" and node.level == 0:
                for a in node.names:
                    aliases[a.asname or a.name] = a.name
                continue
            if target is None or (node.level and target == []
                                  and node.module is None):
                pass
            if node.level and node.module is None:
                for a in node.names:   # from . import kernel
                    aliases[a.asname or a.name] = ".".join(
                        resolve(node.level, a.name))
                continue
            mod = ".".join(target)
            if not mod:
                continue
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


def consumers_index() -> dict:
    """(module, name) -> sorted list of consumers; kwargs fold in as
    (module, 'fn(kw=)') entries. Sources: the pinned .py files and the
    shipped package's own modules."""
    import tomllib
    idx: dict = defaultdict(set)
    with open(REPO / "reticuli.toml", "rb") as f:
        recipe = tomllib.load(f)
    sources = [(rel, None) for rel in recipe["claim"]["inputs"]
               if rel.endswith(".py")]
    sources.append(("gate.py", None))
    for mod in MODULES:
        sources.append((f"src/reticuli/{mod.replace('.', '/')}.py", mod))
    for rel, consumer_mod in sources:
        p = REPO / rel
        if not p.is_file():
            continue
        cons = _consumption(p.read_text(encoding="utf-8"), consumer_mod)
        label = rel if consumer_mod is None else f"src:{consumer_mod}"
        for mod, use in cons.items():
            for name in use["names"]:
                idx[(mod, name)].add(label)
            for fn, kws in use["kwargs"].items():
                for kw in kws:
                    idx[(mod, f"{fn}({kw}=)")].add(label)
    # the kernel facade re-exports the chain: a consumer of kernel.X is a
    # consumer of X wherever it lives, so fold facade consumption onto the
    # _kernel modules that define the name
    return {k: sorted(v) for k, v in idx.items()}


# -- the map -------------------------------------------------------------------

def map_surface(only: list | None = None) -> dict:
    """`only` restricts the class to the named implementations — the
    same-cardinality head-to-head comparisons the succession records cite
    must be reproducible by name, not by editing this dict."""
    chosen = {k: v for k, v in IMPLEMENTATIONS.items()
              if only is None or k in only}
    if only:
        missing = set(only) - set(chosen)
        assert not missing, f"unknown implementations: {sorted(missing)}"
    surfaces = {}
    for impl, base in chosen.items():
        if not base.is_dir():
            continue
        surfaces[impl] = {mod: surface(base / (mod.replace(".", "/") + ".py"))
                          for mod in MODULES}
    impls = sorted(surfaces)
    idx = consumers_index()

    items = []
    for mod in MODULES:
        names = set()
        for impl in impls:
            names |= set(surfaces[impl].get(mod, {}))
        for name in sorted(names):
            row = {impl: surfaces[impl].get(mod, {}).get(name, "ABSENT")
                   for impl in impls}
            if len(set(row.values())) == 1:
                continue
            consumed_by = idx.get((mod, name), [])
            # a consumed call keyword divergence shows as signature drift on
            # the function; surface its kwarg consumers too
            kw_consumers = sorted({c for (m, n), cs in idx.items()
                                   for c in cs
                                   if m == mod and n.startswith(name + "(")})
            tier = 1 if (consumed_by or kw_consumers) else \
                (2 if not name.startswith("_") else 3)
            items.append({"module": mod, "name": name, "tier": tier,
                          "outcomes": row,
                          "consumers": consumed_by,
                          "kwarg_consumers": kw_consumers})
    items.sort(key=lambda x: (x["tier"], x["module"], x["name"]))
    return {"implementations": impls,
            "modules": len(MODULES),
            "divergent_items": len(items),
            "tier1": [x for x in items if x["tier"] == 1],
            "tier2": [x for x in items if x["tier"] == 2],
            "tier3_count": sum(1 for x in items if x["tier"] == 3),
            "items": items}


def report(result: dict) -> None:
    print(f"\nsurface silence — {len(result['implementations'])} "
          f"implementations of {result['modules']} modules: "
          f"{result['divergent_items']} divergent surface items "
          f"({len(result['tier1'])} consumed, {len(result['tier2'])} public "
          f"unconsumed, {result['tier3_count']} private unconsumed)\n")
    print("TIER 1 — divergent AND consumed (live seams):")
    for x in result["tier1"]:
        who = x["consumers"] + x["kwarg_consumers"]
        print(f"\n  {x['module']}.{x['name']}   "
              f"<- {', '.join(who[:4])}{' …' if len(who) > 4 else ''}")
        for impl, desc in x["outcomes"].items():
            print(f"      {impl:10} {desc[:110]}")
    print(f"\nTIER 2 — divergent public, unconsumed "
          f"({len(result['tier2'])} items):")
    bymod = defaultdict(list)
    for x in result["tier2"]:
        bymod[x["module"]].append(x["name"])
    for mod, names in sorted(bymod.items()):
        print(f"  {mod}: {', '.join(names[:8])}"
              f"{' …' if len(names) > 8 else ''}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="FILE")
    ap.add_argument("--only", metavar="IMPL,IMPL,…",
                    help="restrict the class to these implementations "
                         f"(known: {', '.join(sorted(IMPLEMENTATIONS))})")
    a = ap.parse_args()
    r = map_surface(only=a.only.split(",") if a.only else None)
    report(r)
    if a.json:
        slim = {k: v for k, v in r.items() if k != "items"}
        Path(a.json).write_text(json.dumps(slim, indent=2, sort_keys=True))
    sys.exit(0)
