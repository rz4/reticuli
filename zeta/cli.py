"""zeta -- put pressure on the class, queue what it finds, sign nothing.

    python3 zeta/cli.py population            rebuild the population registry
    python3 zeta/cli.py sweep record_surface  run a source, queue the findings
    python3 zeta/cli.py queue                 read the queue, worst lane first
    python3 zeta/cli.py show <entry>          read one entry in full
    python3 zeta/cli.py ledger                read the promotion chain

No subcommand promotes anything. Promotion is a root move in the primary
claim and it is signed by the keyholder.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import entry as entrylib          # noqa: E402
from lib import ledger as ledgerlib        # noqa: E402
from lib import population as poplib       # noqa: E402
from lib import reduce as reducelib        # noqa: E402
from lib import split as splitlib          # noqa: E402
from lib.sources import REGISTRY           # noqa: E402

REGISTRY_PATH = HERE / "population" / "reticuli.json"
QUEUE = HERE / "queue"
LEDGER = HERE / "promoted" / "ledger.jsonl"


def cmd_population(args):
    data = poplib.build(args.repo)
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"current root {data['current_root'][:12]}")
    for group in ("members", "retired", "refused"):
        for member in data[group]:
            tail = "" if group == "members" else f"  ({member['why']})"
            print(f"  {group[:8]:8s} {member['id']:12s} "
                  f"{member['earned_root'][:12]}{tail}")
    return 0


def cmd_sweep(args):
    population = poplib.load(REGISTRY_PATH)
    source = REGISTRY[args.source]
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
    minted = 0
    for finding in findings:
        if entrylib.mint(QUEUE, population, finding) is not None:
            minted += 1
    print(json.dumps({"source": args.source, "probes": sum(tally.values()),
                      "dispositions": tally, "phenomena": len(findings),
                      "newly_minted": minted}, indent=2, sort_keys=True))
    return 0


def cmd_queue(args):
    rows = entrylib.survey(QUEUE)
    if not rows:
        print("queue is empty")
        return 0
    print(f"{len(rows)} undeclared entries\n")
    print(f"{'lane':12s} {'rank':>4s}  {'classes':>7s}  pressure")
    for row in rows:
        result = row["split"]
        print(f"{row['lane']:12s} {row['rank']:>4d}  "
              f"{result['class_count']:>7d}  {row['pressure_id']}")
    return 0


def cmd_show(args):
    document = entrylib.read(QUEUE / args.entry)
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
    build.add_argument("--repo", default=str(HERE.parent))
    build.set_defaults(run=cmd_population)
    sweep = sub.add_parser("sweep")
    sweep.add_argument("source", choices=sorted(REGISTRY))
    sweep.add_argument("--verbose", action="store_true")
    sweep.add_argument("--no-controls", action="store_true")
    sweep.set_defaults(run=cmd_sweep)
    listing = sub.add_parser("queue")
    listing.set_defaults(run=cmd_queue)
    show = sub.add_parser("show")
    show.add_argument("entry")
    show.set_defaults(run=cmd_show)
    chain = sub.add_parser("ledger")
    chain.set_defaults(run=cmd_ledger)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"zeta: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
