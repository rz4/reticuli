"""The task corpus: specifications to write code against, and truth to judge it by.

HumanEval+ (EvalPlus v0.1.10) supplies both halves and keeps them apart, which
is the property the study needs. Each record holds

    prompt              a function signature and docstring -- the spec, and the
                        ONLY thing a model is ever shown
    contract            preconditions saying which inputs the task covers
    canonical_solution  a reference implementation, held back
    base_input          HumanEval's original inputs (a median of 7)
    plus_input          EvalPlus's generated inputs (a median of 972)

Nothing in the held-back half is derived from the visible half, so a model
that writes an implementation from the prompt has not seen the standard it
will be measured against.

WHY THIS CORPUS, stated plainly because it is the study's weakest joint:
HumanEval is nine years old and certainly present in every modern model's
training data, so a model may reproduce a memorised solution rather than solve
the task. That contamination inflates correctness. It does NOT reach what the
study actually measures -- a model cannot memorise the mutation score of a
test suite it is about to write -- but it does compress the range of the
correctness axis, and the README says so in the threats section.

    python3 corpus.py                 # download and report
"""
from __future__ import annotations

import gzip
import json
import os
import random
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "corpus")
RELEASE = ("https://github.com/evalplus/humanevalplus_release/releases/"
           "download/v0.1.10/HumanEvalPlus.jsonl.gz")
LOCAL = os.path.join(CACHE, "HumanEvalPlus.jsonl")

#: What the room tells the model to do. This text IS the experimental
#: condition, so it is kept deliberately neutral: it asks for an
#: implementation and for tests, in the words an ordinary instruction would
#: use, and says nothing about boundaries, edge cases or coverage. Coaching
#: here would raise the very number the study is trying to observe, and the
#: question is what a model does when nobody is watching for that.
INSTRUCTIONS = """\
# Task

Write a Python implementation of the function specified below, and write a
test suite for it.

## The specification

```python
{prompt}```

## What to produce

**`impl.py`** — the complete implementation, including the function signature
and any imports it needs. The function must be named `{entry_point}`.

**`check.py`** — your test suite for it. It runs as `python3 check.py` from
this directory, imports from `impl`, and must exit non-zero if a test fails.

Standard library only.

## Reply format

Two fenced code blocks, each preceded by its filename on its own line:

### impl.py
```python
...
```

### check.py
```python
...
```
"""


def fetch(force: bool = False) -> str:
    """Download the corpus once and cache it next to this file."""
    if os.path.isfile(LOCAL) and not force:
        return LOCAL
    os.makedirs(CACHE, exist_ok=True)
    with urllib.request.urlopen(RELEASE, timeout=180) as response:
        payload = gzip.decompress(response.read())
    tmp = LOCAL + ".tmp"
    with open(tmp, "wb") as f:
        f.write(payload)
    os.replace(tmp, LOCAL)
    return LOCAL


def load() -> dict:
    """Every task, by id."""
    with open(fetch(), encoding="utf-8") as f:
        return {json.loads(line)["task_id"]: json.loads(line) for line in f if line.strip()}


def _numeric(task_id: str) -> int:
    return int(task_id.split("/")[1])


def sample(n: int, seed: str = "reticuli", ids: list | None = None) -> list:
    """A deterministic subset, so a run can be repeated and compared.

    Seeded from a fixed string rather than the clock: which tasks were drawn
    has to be a fact about the study rather than about the afternoon it ran.

    NESTED, too: the order is one shuffle of the whole corpus and n is a prefix
    of it, so the 8 tasks of a pilot are the first 8 of the 25 that follow. A
    `random.sample` of 8 and of 25 share nothing in particular, which would
    make a pilot and the run it justified two unrelated experiments.

    `ids` names tasks outright. That is how a second model is run against the
    first one's exact task set -- comparisons key on the task id in each row,
    never on a sampler agreeing with itself across versions of this file.
    """
    tasks = load()
    if ids:
        missing = [i for i in ids if i not in tasks]
        if missing:
            raise KeyError(f"no such task: {', '.join(missing)}")
        return [tasks[i] for i in sorted(ids, key=_numeric)]
    order = sorted(tasks, key=_numeric)
    random.Random(seed).shuffle(order)
    return [tasks[i] for i in sorted(order[:n], key=_numeric)]


def room(record: dict, into: str) -> str:
    """A clean directory holding the specification and nothing else.

    The model sees this and only this. No reference implementation, no test
    inputs, no mention of how the result will be judged -- a room that leaked
    any of those would be measuring recall rather than authorship.
    """
    path = os.path.join(into, record["task_id"].replace("/", "-"))
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "TASK.md"), "w", encoding="utf-8") as f:
        f.write(INSTRUCTIONS.format(prompt=record["prompt"],
                                    entry_point=record["entry_point"]))
    return path


def main() -> int:
    tasks = load()
    inputs = [len(t.get("base_input") or []) + len(t.get("plus_input") or [])
              for t in tasks.values()]
    print(f"corpus: {len(tasks)} tasks at {LOCAL}")
    print(f"        {sum(inputs)} judging inputs, "
          f"{min(inputs)}–{max(inputs)} per task")
    print(f"        {sum(1 for t in tasks.values() if t.get('atol'))} tasks "
          f"declare a float tolerance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
