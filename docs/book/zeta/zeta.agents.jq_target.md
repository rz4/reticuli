# `zeta/agents/jq_target.py`

**The pilot's second target: the jq language, three foreign implementations.**

The record target was saturated -- the most-probed surface in the project,
put to the most convergent population, and the agent rediscovered the whole
hand-written map and found nothing new. That measured the target, not the
generator. This target is the opposite in every way that matters:

  THE POPULATION GENUINELY DIVERGES. jq, gojq and jaq are three good-faith
  implementations of one documented language, written by people who were not
  coordinating. The project has already measured splits here.

  THE AUTHORITY IS FOREIGN. The citation the vetting demands is a line from
  UPSTREAM'S OWN test corpus, not from anything written here. An agent
  cannot satisfy it by paraphrasing this project's vocabulary back at it,
  which is a stronger oracle-independence guarantee than the record target
  could offer.

  NOTHING HERE AUTHORED THE CRITERIA. So a new split found here cannot be
  an artefact of criteria and candidates sharing a lineage.

What this cannot do is reach the fourth rung by itself. A split among
strangers is third-kind contact; carrying it INTO reticuli as a candidate
pin is the transfer source's job, with provenance, and that remains a
separate step requiring a signature.

```python
from __future__ import annotations

import re
from pathlib import Path

ZETA = Path(__file__).resolve().parents[1]
REPO = ZETA.parent
CORPUS = REPO / "research" / "external" / "jq" / "corpus"
```

Topics to walk, each a keyword family. Named rather than derived so the
walk is reproducible and the per-topic yield is comparable run to run.

```python
TOPICS = [
    ("paths", ("getpath", "setpath", "delpaths", "paths", "leaf_paths",
               "path(")),
    ("numbers", ("tojson", "floor", "sqrt", "infinite", "nan", "have_decnum")),
    ("strings", ("ltrimstr", "rtrimstr", "split", "join", "ascii", "explode",
                 "implode", "@base64", "@csv", "@tsv")),
    ("errors", ("try", "catch", "error", "halt_error", "//")),
    ("ordering", ("sort_by", "group_by", "unique_by", "min_by", "max_by",
                  "to_entries", "keys")),
    ("reduction", ("reduce", "foreach", "limit", "first", "last", "until")),
    ("regex", ("test(", "match(", "capture(", "sub(", "gsub(", "splits(")),
    ("types", ("type", "has(", "in(", "contains", "inside", "any", "all")),
]


def _programs():
    """Program lines from upstream's corpus: the citable text.

    The .test format is a triple per blank-line-separated block -- program,
    input, expected -- so the first line of each block is a program somebody
    upstream wrote deliberately.
    """
    out = []
    for path in sorted(CORPUS.glob("*.test")):
        for block in re.split(r"\n\s*\n", path.read_text(errors="replace")):
            lines = [ln for ln in block.splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")]
            if len(lines) >= 2 and 1 <= len(lines[0]) <= 160:
                out.append(lines[0].strip())
    return out


def clauses():
    """(topic, excerpt of real upstream programs) pairs."""
    programs = _programs()
    out = []
    for topic, keywords in TOPICS:
        hits = [p for p in programs if any(k in p for k in keywords)]
        if len(hits) < 3:
            continue
```

a bounded, deterministic sample: the shortest are the clearest

```python
        sample = sorted(set(hits), key=lambda p: (len(p), p))[:14]
        out.append((f"jq-{topic}", "\n".join(sample)))
    return out


def context():
    return ("Each line below is a jq program taken verbatim from the jq "
            "project's own conformance corpus.")


def citable():
    """Every line a probe may cite: upstream's programs, nothing of ours."""
    return set(_programs())


def prompt(clause_id, focus, shared, per_clause):
    topic = clause_id.removeprefix("jq-")
    return f"""Three independent implementations of the jq language -- jq, gojq \
and jaq -- are under test. They agree on most of the language and diverge where \
the language is documented loosely: error behaviour, number printing, ordering \
promises, what a path expression does to something missing.

{shared} They concern {topic}:

{focus}

Propose exactly {per_clause} NEW jq programs, each with an input document, that \
probe edges these examples leave open for {topic}. Aim at places where two \
good-faith implementers could reasonably differ without either being wrong. \
Keep each program short.

Reply with ONLY a JSON array of {per_clause} objects, no prose:
[{{"program": "<the jq program>",
   "input": "<the input document as a JSON text, e.g. {{\\"a\\":1}} or null>",
   "cites": "<ONE of the program lines above, copied EXACTLY>",
   "expect": "<one line: which divergence you expect and why the language leaves it open>"}}]"""


def vet(candidate, clause_id, allowed, index):
    """A pressure dict, or (None, why). The citation must be upstream's."""
    if not isinstance(candidate, dict):
        return None, "not an object"
    program = candidate.get("program")
    if not isinstance(program, str) or not program.strip():
        return None, "no program"
    if len(program) > 400:
        return None, "program longer than 400 characters"
    document = candidate.get("input")
    if not isinstance(document, str):
        return None, "input must be a JSON text, as a string"
    cites = str(candidate.get("cites", "")).strip()
    if cites not in allowed:
        return None, "citation is not a line from upstream's corpus"
    expect = " ".join(str(candidate.get("expect", "")).split())[:200]
    return {"schema": "zeta.pressure.1",
            "source": "agent-jq",
            "id": f"jq/agent-{clause_id}-{index:02d}",
            "clause": clause_id,
            "simplicity": 1000 + index,
            "call": "run",
            "args": [program, document],
            "specified_reader_behaviour":
                f"agent-expected (decides nothing): {expect}",
            "origin": f"agentic pilot, jq target; cites upstream corpus: "
                      f"\"{cites[:90]}\""}, None
```

---
*Generated from `zeta/agents/jq_target.py` by `docs/weave.py`. The implementation is a reproducible artifact — one member of the equivalence class its acceptance criteria define — and this page is regenerated with it. Edits belong in the source.*
