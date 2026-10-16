# `zeta/cli.py`

**zeta -- put pressure on the class, queue what it finds, sign nothing.**

python3 zeta/cli.py population            rebuild the population registry
    python3 zeta/cli.py sweep record_surface  run a source, queue the findings
    python3 zeta/cli.py queue                 read the queue, worst lane first
    python3 zeta/cli.py show <entry>          read one entry in full
    python3 zeta/cli.py ledger                read the promotion chain

No subcommand promotes anything. Promotion is a root move in the primary
claim and it is signed by the keyholder.

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import coverage as coveragelib    # noqa: E402
from lib import entry as entrylib          # noqa: E402
from lib import ledger as ledgerlib        # noqa: E402
from lib import mutants as mutantlib       # noqa: E402
from lib import population as poplib       # noqa: E402
from lib import reduce as reducelib        # noqa: E402
from lib import selection as selectionlib  # noqa: E402
from lib import split as splitlib          # noqa: E402
from lib.sources import REGISTRY           # noqa: E402

POPULATIONS = {"reticuli": poplib.build,
               "deployment": poplib.deployment,
               "jq": poplib.jq}
REGISTRY_PATH = HERE / "population" / "reticuli.json"
QUEUE = HERE / "queue"


def queue_for(name):
    """One queue per population. Entries from different populations answer to
    different roots, so mixing them in one directory would let a reader
    compare a finding against a root it was never observed against."""
    return QUEUE / name
LEDGER = HERE / "promoted" / "ledger.jsonl"
COVERAGE = HERE / "coverage"
SELECTION = HERE / "selection"


def cmd_population(args):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    for name, builder in sorted(POPULATIONS.items()):
        if name != args.name:
            continue
        data = builder(args.repo)
        (REGISTRY_PATH.parent / f"{name}.json").write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"current root {data['current_root'][:12]}")
    for group in ("members", "retired", "refused"):
        for member in data[group]:
            tail = "" if group == "members" else f"  ({member['why']})"
            print(f"  {group[:8]:8s} {member['id']:12s} "
                  f"{member['earned_root'][:12]}{tail}")
    reconstructions = [m for m in data["members"] if m["id"] != "shipped"]
    if not reconstructions:
        print("\nOnly the authored implementation is a current-root member, so no\n"
              "pressure can tell a property of the class from a property of that\n"
              "one answer. Every sweep is a singleton until the trials are\n"
              "re-earned against this root.")
    return 0


def cmd_sweep(args):
    population = poplib.load(REGISTRY_PATH.parent / f"{args.population}.json")
    source = REGISTRY[args.source]
    workspace = extra = None
    drivers = {m.get("driver", "python-package") for m in population["members"]}
    if args.mutants and drivers != {"python-package"}:
        print(f"  mutants skipped: this population is driven by "
              f"{', '.join(sorted(drivers))}, and a control that cannot run "
              f"the pressure ranks nothing")
    elif args.mutants:
```

Mutants are controls, never members: nobody sealed them and they
would not earn the root. They only have to answer differently from
the members, which is what lets a free click be ranked.

```python
        workspace = mutantlib.session(args.repo)
        extra, missed = mutantlib.build(args.repo, workspace.name)
        for gap in missed:
            print(f"  mutant NOT BUILT  {gap['operator']}: {gap['why']} "
                  f"({gap['matches']} matches)")
        print(f"  {len(extra)} mutant control(s) built")
        population = {**population,
                      "refused": list(population.get("refused", [])) + extra}
    observed, tally = [], {}
    for pressure in source.pressures():
        result = splitlib.run(population, pressure, controls=not args.no_controls)
        tally[result["disposition"]] = tally.get(result["disposition"], 0) + 1
        if args.verbose:
            print(f"  probe  {result['disposition']:10s} "
                  f"{result['lane'] or '-':12s} {pressure['id']}")
        if splitlib.queueable(result):
            observed.append(result)
    findings = reducelib.collapse(observed)
    report = COVERAGE / "reticuli.json"
    if report.is_file() and args.population in ("reticuli", "deployment"):
```

Redundancy is judged against the criteria that were in force when
the coverage was measured, so the digest travels with the verdict.

```python
        known = coveragelib.load(report)
        findings = [coveragelib.annotate(f, known) for f in findings]
    minted = 0
    for finding in findings:
        if entrylib.mint(queue_for(args.population), population,
                         finding) is not None:
            minted += 1
    print(json.dumps({"source": args.source, "population": args.population,
                      "probes": sum(tally.values()),
                      "dispositions": tally, "phenomena": len(findings),
                      "ranked": sum(1 for f in findings if f["rank"]),
                      "newly_minted": minted}, indent=2, sort_keys=True))
    if workspace is not None:
        workspace.cleanup()
    return 0


def cmd_queue(args):
    live = poplib.load(REGISTRY_PATH.parent /
                       f"{args.population}.json")["current_root"]
    rows = entrylib.survey(queue_for(args.population), live)
    if not rows:
        print("queue is empty")
        return 0
    stale = sum(row["stale"] for row in rows)
    print(f"{len(rows)} undeclared entries against root {live[:12]}"
          f"{f'; {stale} STALE' if stale else ''}\n")
    print(f"{'lane':12s} {'rank':>4s}  {'classes':>7s}  pressure")
    for row in rows:
        result = row["split"]
        mark = f"  STALE (observed at {row['observed_root'][:12]})" if row["stale"] else ""
        print(f"{row['lane']:12s} {row['rank']:>4d}  "
              f"{result['class_count']:>7d}  {row['pressure_id']}{mark}")
    if stale:
        print("\nA stale entry records what was seen against a root that has since\n"
              "moved. Re-earn the population and sweep again before signing one.")
    return 0


def cmd_show(args):
    document = entrylib.read(queue_for(args.population) / args.entry)
    result = document["split"]
    print(f"entry      {document['id']}   state={document['state']}")
    print(f"pressure   {document['pressure_id']}")
    print(f"origin     {result['pressure']['origin']}")
    print(f"spec says  {result['pressure']['specified_reader_behaviour']}")
    print(f"lane       {document['lane']}  ({result['disposition']})")
    print(f"root       {result['current_root'][:16]}")
    print("\nbehaviour classes over current-root members:")
    for key, members in result["classes"].items():
        sample = result["observations"][members[0]]
        shown = sample.get("error_type") or json.dumps(sample.get("value"))[:60]
        print(f"  {key}  {shown:42s} {', '.join(members)}")
    if result["would_evict"]:
        print("\ndeclaring one class would evict:")
        for key, count in result["would_evict"].items():
            print(f"  {key}  {count} member(s)")
    if result["discriminates"]:
        print(f"\ndiscriminates controls: {', '.join(result['discriminates'])}")
    if result["wording_divergence"]:
        print("\nrefusal wording differs (outside the equivalence, by design):")
        for text in result["refusal_wordings"]:
            print(f"  {text[:100]}")
    return 0


def cmd_coverage(args):
    """Which mutants the criteria already kill, and so which pressure is new."""
    import tempfile
    with tempfile.TemporaryDirectory() as trees, tempfile.TemporaryDirectory() as rooms:
        built, missed = mutantlib.build(args.repo, trees)
        for gap in missed:
            print(f"  NOT BUILT  {gap['operator']}: {gap['why']}")
        print(f"  {len(built)} mutants; one full gate run each, please wait")
        report = coveragelib.report(args.repo, built, rooms)
    COVERAGE.mkdir(parents=True, exist_ok=True)
    (COVERAGE / "reticuli.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"\ncriteria {report['criteria_digest'][:12]}  "
          f"baseline earned={not report['baseline']['killed']}")
    for row in report["rows"]:
        state = "killed  " if row["killed"] else "SURVIVES"
        flag = "   <-- CONTRADICTS ITS EXPECTATION" if row["contradicts_expectation"] else ""
        print(f"  {state} expect={row['expect']:9s} "
              f"{row['control'].replace('mutant:', ''):24s} {row['breaks']}{flag}")
    gaps = [r for r in report["rows"]
            if not r["killed"] and r["expect"] != "survives"]
    if gaps:
        print(f"\n{len(gaps)} criterion gap(s): a declared obligation with "
              f"nothing behind it.\nEach is a contraction -- every current "
              f"member already satisfies it -- and\nclosing one is a root "
              f"move, which is the keyholder's to sign.")
    return 0


def cmd_select(args):
    """Measure every member on declared unpinned axes; report the frontier.

    No signature, no root move: the implementation is generated, so moving
    between members preserves identity exactly. What this cannot do is pick,
    because one declared axis -- the institutional memory carried in comments
    and docstrings -- is invisible to every gate.
    """
    sys.path.insert(0, str(HERE.parent / "src"))
    from reticuli import kernel
    from reticuli._kernel import recipe as recipelib
    outputs = recipelib.generated_outputs(recipelib.load_recipe(args.repo))
    pool = selectionlib.candidates(args.repo, args.scope)
    if args.only:
        pool = [c for c in pool if c["id"] in set(args.only)]
    print(f"  {len(outputs)} generated outputs; {len(pool)} candidate(s); "
          f"axes {selectionlib.axes_digest()[:12]}")
    rows = []
    for candidate in pool:
        row = selectionlib.measure(candidate, args.repo, kernel, outputs)
        rows.append(row)
        mark = "member" if row["member"] else "NOT A MEMBER"
        print(f"  {row['candidate']:18s} {mark:12s} {row['audit_seconds']:6.1f}s"
              + (f"  {row['total_bytes']/1024:7.1f} KiB"
                 f"  code {row['code_bytes']/1024:6.1f}"
                 f"  prose {row['prose_bytes']/1024:5.1f}" if row["member"] else ""))
    result = selectionlib.survey(rows)
    SELECTION.mkdir(parents=True, exist_ok=True)
    (SELECTION / "reticuli.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"\n  frontier: {', '.join(result['frontier'])}")
    print("  no axis ranking is offered: prose_bytes runs the other way on\n"
          "  purpose, so a smaller member trades away institutional memory\n"
          "  that no gate can measure. Adoption stays a human choice.")
    return 0


def cmd_ledger(args):
    records = ledgerlib.chain(LEDGER)
    if not records:
        print("no promotions recorded; the queue has never been signed")
        return 0
    for record in records:
        print(f"{record['when']}  {record['root_before'][:10]} -> "
              f"{record['root_after'][:10]}  {record['lane']:12s} {record['pin']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="verb", required=True)
    build = sub.add_parser("population")
    build.add_argument("name", choices=sorted(POPULATIONS), nargs="?",
                       default="reticuli")
    build.add_argument("--repo", default=str(HERE.parent))
    build.set_defaults(run=cmd_population)
    sweep = sub.add_parser("sweep")
    sweep.add_argument("source", choices=sorted(REGISTRY))
    sweep.add_argument("--population", choices=sorted(POPULATIONS),
                       default="reticuli")
    sweep.add_argument("--verbose", action="store_true")
    sweep.add_argument("--no-controls", action="store_true")
    sweep.add_argument("--mutants", action="store_true",
                       help="add deliberately broken trees as controls, so a "
                            "free click can be ranked by what it would catch")
    sweep.add_argument("--repo", default=str(HERE.parent))
    sweep.set_defaults(run=cmd_sweep)
    listing = sub.add_parser("queue")
    listing.add_argument("--population", choices=sorted(POPULATIONS),
                         default="reticuli")
    listing.set_defaults(run=cmd_queue)
    show = sub.add_parser("show")
    show.add_argument("entry")
    show.add_argument("--population", choices=sorted(POPULATIONS),
                      default="reticuli")
    show.set_defaults(run=cmd_show)
    cover = sub.add_parser("coverage")
    cover.add_argument("--repo", default=str(HERE.parent))
    cover.set_defaults(run=cmd_coverage)
    pick = sub.add_parser("select")
    pick.add_argument("--repo", default=str(HERE.parent))
    pick.add_argument("--only", nargs="*", help="limit to these candidate ids")
    pick.add_argument("--scope", choices=["current", "all"], default="current",
                      help="current-root members (default) or every tree on disk")
    pick.set_defaults(run=cmd_select)
    chain = sub.add_parser("ledger")
    chain.set_defaults(run=cmd_ledger)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"zeta: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
```

---
*Generated from `zeta/cli.py` by `docs/weave.py`. The implementation is a reproducible artifact — one member of the equivalence class its acceptance criteria define — and this page is regenerated with it. Edits belong in the source.*
