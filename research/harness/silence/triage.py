"""Triage the tier-1 seams: how many clicks stand between here and a
quiet map?

The surface map counts every consumed divergence as a live seam, but the
consumers are not alike. This triage splits them:

  A  consumed by a PINNED file — governed by the closure criterion, which
     forces the owning layer's check to exercise the name, and exercised
     surface converges (r3 proved it). Divergence left here should be
     FORM-ONLY (a parameter name nobody passes, star placement no caller
     crosses). Anything SUBSTANTIVE — a name absent from some
     implementation, a consumed call keyword missing from some signature,
     a constant value differing — is a real residue: a closure blind spot
     that needs a pin.
  B  consumed only by other GENERATED modules — the intra-package seams.
     Each lineage is internally coherent, and mixed trees are not a goal
     (the succession settled that), so these are declarable free as a
     set, with a sentence in the spec rather than a pin per seam.

The kernel facade complicates A: the original defines names in _kernel/*
and re-exports through kernel.py, while lineages define them directly, so
the raw map shows ABSENT where the original merely re-exports. The triage
resolves each tree's EFFECTIVE kernel surface (kernel.py plus its
_kernel re-exports) before judging substance.

    python3 triage.py [--json FILE]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import surface_silence as ss  # noqa: E402


def effective_kernel_surface(base: Path) -> dict:
    """kernel.py's own surface plus everything its _kernel modules define —
    the surface a consumer of `kernel.X` actually reaches."""
    merged = dict(ss.surface(base / "kernel.py"))
    kdir = base / "_kernel"
    if kdir.is_dir():
        for p in sorted(kdir.glob("*.py")):
            if p.name == "__init__.py":
                continue
            for name, desc in ss.surface(p).items():
                merged.setdefault(name, desc)
    return merged


def main() -> None:
    impls = {k: v for k, v in ss.IMPLEMENTATIONS.items() if v.is_dir()}
    result = ss.map_surface()
    kernel_eff = {impl: effective_kernel_surface(base)
                  for impl, base in impls.items()}
    idx = ss.consumers_index()

    verdicts = []
    for x in result["tier1"]:
        mod, name = x["module"], x["name"]
        consumers = x["consumers"] + x["kwarg_consumers"]
        pinned_consumers = [c for c in consumers if not c.startswith("src:")]
        src_consumers = [c for c in consumers if c.startswith("src:")]
        outcomes = dict(x["outcomes"])
        # resolve the facade for kernel.* items
        if mod == "kernel":
            outcomes = {impl: kernel_eff[impl].get(name, "ABSENT")
                        for impl in outcomes}
        if not pinned_consumers:
            verdicts.append({"module": mod, "name": name, "class": "B",
                             "verdict": "internal seam — declarable free",
                             "src_consumers": src_consumers})
            continue
        # A: substantive if absent anywhere, a consumed kwarg missing from
        # some signature, or a non-function value differing
        absent = [i for i, d in outcomes.items() if d == "ABSENT"]
        kw_missing = []
        # the call keywords PINNED files use on this function
        wanted_kws = {n.split("(")[1][:-2]
                      for (m, n), cs in idx.items()
                      if m == mod and n.startswith(name + "(")
                      and any(not c.startswith("src:") for c in cs)}
        for impl, desc in outcomes.items():
            if desc == "ABSENT" or not desc.startswith("def("):
                continue
            for kw in wanted_kws:
                if kw not in desc:
                    kw_missing.append(f"{impl} lacks {kw}=")
        is_value = any(d.startswith("= ") for d in outcomes.values()
                       if d != "ABSENT")
        value_diverges = is_value and len(
            {d for d in outcomes.values() if d != "ABSENT"}) > 1
        if absent or kw_missing or (value_diverges and absent):
            verdicts.append({"module": mod, "name": name, "class": "A-SUBST",
                             "verdict": "pinned-consumed, substantive residue",
                             "absent_in": absent, "kwarg_gaps": kw_missing,
                             "pinned_consumers": pinned_consumers})
        elif value_diverges:
            verdicts.append({"module": mod, "name": name, "class": "A-VALUE",
                             "verdict": "pinned-consumed constant, values differ",
                             "outcomes": {i: d for i, d in outcomes.items()},
                             "pinned_consumers": pinned_consumers})
        else:
            verdicts.append({"module": mod, "name": name, "class": "A-FORM",
                             "verdict": "pinned-consumed, form-only variance",
                             "pinned_consumers": pinned_consumers})

    counts = defaultdict(int)
    for v in verdicts:
        counts[v["class"]] += 1
    print(f"tier-1 triage over {len(result['tier1'])} seams "
          f"({len(impls)} implementations):")
    print(f"  A-FORM   {counts['A-FORM']:4}  pinned-consumed, form-only "
          f"— already governed, free")
    print(f"  A-VALUE  {counts['A-VALUE']:4}  pinned-consumed constants with "
          f"differing values — pin candidates")
    print(f"  A-SUBST  {counts['A-SUBST']:4}  pinned-consumed, substantive "
          f"— closure blind spots, REAL residue")
    print(f"  B        {counts['B']:4}  internal-only — one spec sentence "
          f"declares them free as a set")
    print()
    for v in verdicts:
        if v["class"] in ("A-SUBST", "A-VALUE"):
            print(f"  [{v['class']}] {v['module']}.{v['name']}"
                  f"   <- {', '.join(v['pinned_consumers'][:3])}")
            for key in ("absent_in", "kwarg_gaps"):
                if v.get(key):
                    print(f"      {key}: {v[key]}")
            if v.get("outcomes"):
                for i, d in v["outcomes"].items():
                    print(f"      {i:10} {d[:80]}")
    return verdicts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="FILE")
    a = ap.parse_args()
    vs = main()
    if a.json:
        Path(a.json).write_text(json.dumps(vs, indent=2, sort_keys=True))
