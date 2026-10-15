"""Agentic pressure, the pilot: can a model-driven walker find real silence?

The question this answers is narrow and measurable: given the record
specification's own text, clause by clause, does a model propose probes
that (a) cite the clause they test, (b) execute, (c) split or unanimously
exercise the deployment population, and (d) rediscover what the
hand-written source already found -- plus anything it never did?

The design constraints, each from a measured failure elsewhere:

  ORACLE INDEPENDENCE. A probe's citation must appear VERBATIM in the spec,
  checked mechanically, or the probe is refused unexecuted. If the agent
  supplied both the probe and its own reading of the spec, agreement would
  measure the agent, not the silence. The agent's expectation is recorded
  but decides nothing -- the lane comes from what members actually do,
  exactly as with the hand-written sources.

  RECALL, NOT JUST PRECISION. The hand-written record_surface battery runs
  first and its phenomenon signatures are the salt: a generator that is
  precise but only rediscovers the easy tenth of the map is a toy. Recall
  is |agent signatures ∩ hand signatures| / |hand signatures|, mechanical,
  using the same reduce.signature the queue uses.

  SPEND IS CAPPED AND COUNTED PER SIDE. Generation stops at the ceiling,
  and every call's input, cached and output tokens are priced at the
  gateway's quoted rates -- the blended-midpoint and deleted-usage-file
  lessons both landed this week.

Nothing here decides anything. Queueable findings are minted into the real
queue as `undeclared`, like every other source's, with the agent named in
the origin so a reader can see who proposed what the replay then re-earns.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ZETA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ZETA))

from lib import entry as entrylib          # noqa: E402
from lib import population as poplib       # noqa: E402
from lib import reduce as reducelib        # noqa: E402
from lib import split as splitlib          # noqa: E402
from lib.sources import record_surface     # noqa: E402

REPO = ZETA.parent
SPEC = REPO / "spec" / "record.md"

MAG_URL = "https://mag.genesis.americansciencecloud.org/v1"
#: haiku: cleared the capability floor on 2026-10-15 at $0.04, cheapest
#: model measured to actually read a spec well enough to act on it.
MODEL = "claude-haiku-5-5:high@google"
PRICE = (0.10, 0.50, 0.01)                 # usd per Mtok: input, output, cache
SPEND_CEILING = float(os.environ.get("ZETA_PILOT_CEILING", "0.50"))
PROBES_PER_CLAUSE = 4


# -- the spec, carved into clause groups --------------------------------------

def _section(text, heading):
    pattern = rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    found = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return found.group(1).strip() if found else ""


def clauses():
    """(id, focus excerpt) pairs, each one prompt's worth of spec.

    The Validation section is one long refusal sentence; its semicolon
    clauses are the natural probe families -- the same carving the
    hand-written source used, which is what makes recall comparable.
    """
    text = SPEC.read_text()
    out = []
    validation = _section(text, "Validation")
    for index, piece in enumerate(validation.replace("\n", " ").split(";")):
        piece = piece.strip().rstrip(".")
        if len(piece) > 40:
            out.append((f"validation-{index:02d}", piece))
    canonical = _section(text, "Canonical bytes and the record digest")
    if canonical:
        out.append(("canonical-bytes", canonical.replace("\n", " ")))
    return out


def context():
    """What every prompt carries: the member table and the surfaces."""
    text = SPEC.read_text()
    return _section(text, "The document")


# -- generation, spend-capped --------------------------------------------------

def _credential():
    key = os.environ.get("AMSC_API_KEY") or os.environ.get("AMSC_TOKEN")
    if not key:
        raise SystemExit("agentic pilot: AMSC_API_KEY/AMSC_TOKEN is not set")
    return key


def _prompt(clause_id, focus, shared):
    return f"""You are probing three implementations of one specification for \
behavioural differences. The functions under test each take ONE parsed JSON \
document as their only argument:

  record_validate(doc)   record_canonical(doc)   record_digest(doc)

Here is the specification's member table:

{shared}

Here is the clause you are probing:

  {focus}

Propose exactly {PROBES_PER_CLAUSE} probe documents that put THIS clause to the \
functions. Each probe should be a complete, self-contained document with at most \
one deliberate deviation from the spec (a deliberately conformant document is \
also a valid probe). Prefer edge readings the clause does not settle: boundary \
values, type edges, casing, emptiness, nesting.

Reply with ONLY a JSON array of {PROBES_PER_CLAUSE} objects, no prose:
[{{"call": "<one of the three function names>",
   "document": <the probe document, inline JSON>,
   "cites": "<a phrase of at least 25 characters copied VERBATIM from the text above>",
   "expect": "<one line: what you expect and why the clause leaves it open or settles it>"}}]"""


class Spend:
    def __init__(self):
        self.usd = 0.0
        self.calls = 0
        self.tokens = {"input": 0, "output": 0, "cached": 0}

    def add(self, usage):
        self.calls += 1
        if not usage:
            return
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
        out = getattr(usage, "completion_tokens", 0) or 0
        self.tokens["input"] += max(0, prompt - cached)
        self.tokens["cached"] += cached
        self.tokens["output"] += out
        self.usd += (max(0, prompt - cached) * PRICE[0]
                     + out * PRICE[1] + cached * PRICE[2]) / 1e6

    def report(self):
        return {"usd": round(self.usd, 6), "calls": self.calls,
                "rates": {"input": PRICE[0], "output": PRICE[1],
                          "cache_read": PRICE[2]}, **self.tokens}


def propose(clause_id, focus, shared, spend):
    """One generation call; returns raw candidates (possibly empty)."""
    if spend.usd >= SPEND_CEILING:
        return [], "spend ceiling reached; no call made"
    from openai import OpenAI
    client = OpenAI(base_url=MAG_URL, api_key=_credential())
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": _prompt(clause_id, focus, shared)}],
        max_completion_tokens=6000)
    spend.add(response.usage)
    text = response.choices[0].message.content or ""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return [], "no JSON array in the reply"
    try:
        raw = json.loads(text[start:end + 1])
    except ValueError as exc:
        return [], f"unparseable reply: {exc}"
    if not isinstance(raw, list):
        return [], "reply is not an array"
    return raw, None


# -- vetting: mechanical, before anything executes -----------------------------

def _squash(text):
    return " ".join(str(text).split())


def vet(candidate, clause_id, spec_text, index):
    """A pressure dict, or (None, why). Refusals never execute."""
    if not isinstance(candidate, dict):
        return None, "not an object"
    call = candidate.get("call")
    if call not in record_surface.SURFACES:
        return None, f"call {call!r} is not a probed surface"
    cites = _squash(candidate.get("cites", ""))
    if len(cites) < 25:
        return None, "citation shorter than 25 characters"
    if cites not in _squash(spec_text):
        return None, "citation is not verbatim spec text"
    if "document" not in candidate:
        return None, "no document"
    expect = _squash(candidate.get("expect", ""))[:200]
    return {"schema": "zeta.pressure.1",
            "source": "agent",
            "id": f"{call}/agent-{clause_id}-{index:02d}",
            "clause": clause_id,
            "simplicity": 1000 + index,
            "call": call,
            "args": [candidate["document"]],
            "specified_reader_behaviour": f"agent-expected (decides nothing): {expect}",
            "origin": f"agentic pilot ({MODEL}); cites spec/record.md: "
                      f"\"{cites[:90]}\""}, None


# -- the baseline the agent is measured against --------------------------------

def _sig(result):
    return json.dumps(reducelib.signature(result), sort_keys=True, default=str)


def hand_baseline(population):
    """Run the hand-written source; its signatures are the recall salt."""
    signatures = {}
    for pressure in record_surface.pressures():
        result = splitlib.run(population, pressure, controls=False)
        if splitlib.queueable(result):
            signatures.setdefault(_sig(result), result["pressure"]["id"])
    return signatures


# -- the verifier's pipeline ----------------------------------------------------

def execute(pressures, population):
    results, tally = [], {}
    for pressure in pressures:
        result = splitlib.run(population, pressure, controls=False)
        tally[result["disposition"]] = tally.get(result["disposition"], 0) + 1
        results.append(result)
    return results, tally


def conclude(results, hand, population, queue_dir):
    """Reduce, compare against the salt, mint what queues. The numbers."""
    queueable = [r for r in results if splitlib.queueable(r)]
    agent_sigs = {}
    for result in queueable:
        agent_sigs.setdefault(_sig(result), result["pressure"]["id"])
    overlap = set(agent_sigs) & set(hand)
    new = set(agent_sigs) - set(hand)
    findings = reducelib.collapse(queueable)
    minted = []
    for finding in findings:
        path = entrylib.mint(Path(queue_dir), population, finding)
        if path is not None:
            minted.append(str(path))
    return {
        "executed": len(results),
        "queueable": len(queueable),
        "phenomena": len(findings),
        "signatures": {"agent": len(agent_sigs), "hand": len(hand),
                       "rediscovered": len(overlap), "new": len(new)},
        "recall": round(len(overlap) / len(hand), 3) if hand else None,
        "new_signature_pressures": sorted(agent_sigs[s] for s in new),
        "minted": minted,
    }


def deployment_population():
    return poplib.load(ZETA / "population" / "deployment.json", repo=REPO)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")
