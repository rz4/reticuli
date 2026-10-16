# `zeta/agents/pilot.py`

**The two-agent pilot: a walker proposes, a verifier replays, numbers out.**

python3 -m agents.pilot              # the real thing, spend-capped
    python3 -m agents.pilot --dry        # no model, canned candidates: free
                                         # end-to-end smoke of the pipeline

Two academy agents on the local exchange. The WALKER holds the spec carved
into clauses and spends capped money asking a model for probes; it executes
nothing. The VERIFIER holds the population and the hand-written baseline; it
refuses any probe whose citation is not verbatim spec text, executes the
rest, reduces, and mints what queues. The manager relays between their
handles -- the message-board topology proper comes when this stands up as
loops; the pilot's job is the yield number, not the plumbing's elegance.

What the report means:
  recall        fraction of the hand-written source's phenomenon signatures
                the agent independently rediscovered. Low recall with high
                precision = a toy that found the easy tenth.
  new           signatures the hand source never produced: the actual
                candidate silence, each one entry in the queue awaiting the
                ordinary signature path. New does not mean true -- it means
                worth a look.
  usd           what the generation cost, per side, against the ceiling.

```python
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents import jq_target  # noqa: E402
from agents import pressure  # noqa: E402

REPORTS = Path(__file__).resolve().parent
```

canned candidates for --dry: one sound probe, one that clones a hand case
(should be redundant), one bad citation, one bad call -- the pipeline's
four paths, no model, no money

```python
def _canned(clause_id, focus):
    base = dict(pressure.record_surface.BASE)
    return [
        {"call": "record_validate", "document": {**base, "when": ""},
         "cites": focus[:60], "expect": "empty when: the clause does not say"},
        {"call": "record_validate",
         "document": {k: v for k, v in base.items() if k != "when"},
         "cites": focus[:60], "expect": "missing member: should refuse"},
        {"call": "record_validate", "document": base,
         "cites": "this sentence appears nowhere in the specification text",
         "expect": "must be refused for its citation"},
        {"call": "os.system", "document": base,
         "cites": focus[:60], "expect": "must be refused for its call"},
    ]


from academy.agent import Agent, action  # noqa: E402


class Walker(Agent):
    """Carries the target's text; spends the money; executes nothing."""

    def __init__(self, dry=False, target="record"):
        super().__init__()
        self.dry = dry
        self.target = target
        self.shared = (jq_target.context() if target == "jq"
                       else pressure.context())
        self.spend = pressure.Spend()

    @action
    async def propose(self, clause_id: str, focus: str) -> dict:
        if self.dry:
            return {"candidates": _canned(clause_id, focus), "note": "dry"}
        ask = (jq_target.prompt(clause_id, focus, self.shared,
                                pressure.PROBES_PER_CLAUSE)
               if self.target == "jq" else None)
        raw, why = await asyncio.to_thread(
            pressure.propose, clause_id, focus, self.shared, self.spend, ask)
        return {"candidates": raw, "note": why,
                "spend": self.spend.report()}

    @action
    async def spent(self) -> dict:
        return self.spend.report()


class Verifier(Agent):
    """Holds the population and the salt; the only one that executes."""

    def __init__(self, target="record"):
        super().__init__()
        self.target = target
        if target == "jq":
            self.population = pressure.jq_population()
            self.authority = jq_target.citable()
        else:
            self.population = pressure.deployment_population()
            self.authority = pressure.SPEC.read_text()
        self.hand = None
        self.results = []
        self.refusals = {}
        self.proposed = 0

    @action
    async def baseline(self) -> dict:
        salt = (pressure.jq_hand_baseline if self.target == "jq"
                else pressure.hand_baseline)
        self.hand = await asyncio.to_thread(salt, self.population)
        return {"hand_signatures": len(self.hand)}

    @action
    async def verify(self, clause_id: str, candidates: list) -> dict:
        self.proposed += len(candidates)
        vetted = []
        for index, candidate in enumerate(candidates):
            vetter = jq_target.vet if self.target == "jq" else pressure.vet
            probe, why = vetter(candidate, clause_id, self.authority, index)
            if probe is None:
                self.refusals[why] = self.refusals.get(why, 0) + 1
                continue
            vetted.append(probe)
        results, tally = await asyncio.to_thread(
            pressure.execute, vetted, self.population)
        self.results.extend(results)
        return {"proposed": len(candidates), "vetted": len(vetted),
                "dispositions": tally}

    @action
    async def conclude(self) -> dict:
        queue = pressure.ZETA / "queue" / self.population["name"]
        summary = await asyncio.to_thread(
            pressure.conclude, self.results, self.hand or {},
            self.population, queue)
        summary["proposed"] = self.proposed
        summary["refused_unexecuted"] = self.refusals
        return summary


async def main(dry: bool, target: str) -> int:
    from concurrent.futures import ThreadPoolExecutor

    from academy.exchange.local import LocalExchangeFactory
    from academy.manager import Manager

    began = time.time()
    clause_list = (jq_target.clauses() if target == "jq"
                   else pressure.clauses())
    print(f"pilot[{target}]: {len(clause_list)} clause(s), "
          f"{'dry (no model, no money)' if dry else 'model ' + pressure.MODEL}"
          f"{'' if dry else f', ceiling ${pressure.SPEND_CEILING:.2f}'}",
          flush=True)

    async with await Manager.from_exchange_factory(
            factory=LocalExchangeFactory(),
            executors=ThreadPoolExecutor(max_workers=2)) as manager:
        walker = await manager.launch(
            Walker, kwargs={"dry": dry, "target": target})
        verifier = await manager.launch(Verifier, kwargs={"target": target})
        salt = await verifier.baseline()
        print(f"pilot: baseline ran, {salt['hand_signatures']} hand "
              f"signature(s) as the recall salt", flush=True)
        for clause_id, focus in clause_list:
            offer = await walker.propose(clause_id, focus)
            if offer.get("note") and not offer["candidates"]:
                print(f"pilot: {clause_id}: {offer['note']}", flush=True)
                continue
            verdict = await verifier.verify(clause_id, offer["candidates"])
            print(f"pilot: {clause_id}: {verdict['proposed']} proposed, "
                  f"{verdict['vetted']} executed, "
                  f"{verdict['dispositions']}", flush=True)
        summary = await verifier.conclude()
        summary["spend"] = await walker.spent() if not dry else {"usd": 0.0}
        summary["model"] = None if dry else pressure.MODEL
        summary["population"] = ("jq" if target == "jq" else "deployment")
        summary["target"] = target
        summary["minutes"] = round((time.time() - began) / 60, 1)
        summary["when"] = pressure.now()
        await manager.shutdown(walker, blocking=True)
        await manager.shutdown(verifier, blocking=True)

    report = REPORTS / f"pilot_report_{target}.json"
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"pilot: report -> {report}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--target", choices=("record", "jq"), default="record")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.dry, args.target)))
```

---
*Generated from `zeta/agents/pilot.py` by `docs/weave.py`. The implementation is a reproducible artifact — one member of the equivalence class its acceptance criteria define — and this page is regenerated with it. Edits belong in the source.*
