"""LiveCodeBench: tasks whose specifications do not do the hard part.

The EvalPlus pilots produced no usable rows, and the reason was structural
rather than a matter of sample size. A HumanEval docstring illustrates the
behaviour with worked examples *including the awkward ones*; a model writes
its tests from those examples; so the suite covers the regions the spec
illustrates, and the code is right in those same regions for the same reason.
Both models scored 8 of 8, and the correctness axis had no variance to
correlate anything against.

What the study needs is a task where the specification describes behaviour but
does not enumerate the cases that break it. Contest problems are exactly that:
a statement, two or three sample cases, and forty hidden ones chosen by a
problem setter whose job was to break wrong submissions. A model writing its
own tests from the statement is writing them from the samples, and the samples
are not where the failures are.

    problems      175, contests dated 2025-01-04 to 2025-04-06
    functional    63 of them hand the model `class Solution:` and one method,
                  which is the shape this harness already measures
    stdin         the other 112 are whole programs over standard input, a
                  different room shape; not used yet, and said so rather than
                  quietly dropped
    cases         a median of 42 per problem, against HumanEval's 7
    difficulty    80 hard, 52 medium, 43 easy over the whole set

TRUTH IS STORED HERE, NOT COMPUTED, and that is a reversal worth defending.
The EvalPlus oracle runs a reference implementation because HumanEval's own
stored tests are too weak to be truth -- EvalPlus found they accept roughly a
fifth of solutions that are wrong. That objection does not carry to a contest
judge's data: these are the cases a submission had to pass to be accepted,
written to break wrong answers rather than to illustrate right ones. There is
no reference implementation in the dataset to run even if we wanted one.

ON CONTAMINATION, which is the reason this corpus was chosen and also its
weakest point: LiveCodeBench exists to be filterable by date, and these
problems postdate HumanEval by nine years. They do not necessarily postdate a
current model's training data -- April 2025 is inside some windows -- so
`--after` is provided to cut the set by contest date, and the honest headline
benefit here is DIFFICULTY. A model fails these whether or not it has seen
them, which is what the correctness axis needs.

    python3 corpus_lcb.py                 # download and report
"""
from __future__ import annotations

import base64
import json
import os
import pickle  # the dataset ships its hidden tests pickled
import random
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "corpus")
RELEASE = ("https://huggingface.co/datasets/livecodebench/code_generation_lite/"
           "resolve/main/test6.jsonl")
LOCAL = os.path.join(CACHE, "lcb-v6.jsonl")

#: The same neutral instruction as the EvalPlus corpus, in the same words, so
#: the two runs differ in their tasks and not in how they were asked. What
#: changes is the shape of the subject: a method on a class, because that is
#: what the problem hands the model.
INSTRUCTIONS = """\
# Task

Solve the programming problem below, and write a test suite for your solution.

## The problem

{statement}

## The required signature

```python
{starter}```

## What to produce

**`impl.py`** — the complete solution, including the `class {cls}` wrapper, the
method signature above, and any imports it needs (`from typing import List` if
you use those annotations).

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
    """Download the release once and cache it next to this file (~129MB)."""
    if os.path.isfile(LOCAL) and not force:
        return LOCAL
    os.makedirs(CACHE, exist_ok=True)
    tmp = LOCAL + ".tmp"
    with urllib.request.urlopen(RELEASE, timeout=900) as response, \
            open(tmp, "wb") as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, LOCAL)
    return LOCAL


def _hidden(record: dict) -> list:
    """The private cases, which ship base64'd over zlib over a pickle."""
    raw = record.get("private_test_cases") or ""
    if not raw:
        return []
    try:
        blob = zlib.decompress(base64.b64decode(raw))
    except (ValueError, zlib.error):
        return []
    try:
        loaded = pickle.loads(blob)    # the dataset's own encoding
    except Exception:  # noqa: BLE001 - some releases store plain JSON instead
        loaded = blob.decode("utf-8", "replace")
    return json.loads(loaded) if isinstance(loaded, str) else loaded


def signature(record: dict) -> tuple[str, str]:
    """The class and method the problem asks for, read off the starter code."""
    cls = method = ""
    for line in (record.get("starter_code") or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("class ") and not cls:
            cls = stripped[6:].split("(")[0].split(":")[0].strip()
        elif stripped.startswith("def ") and not method:
            method = stripped[4:].split("(")[0].strip()
    return cls, method


def entry_point(record: dict) -> str:
    cls, method = signature(record)
    return f"{cls}.{method}" if cls else method


def task_id(record: dict) -> str:
    return f"lcb/{record['question_id']}"


def _arguments(text: str) -> list:
    """One JSON literal per line is one argument, which is LCB's convention."""
    args = []
    for line in str(text).splitlines():
        if not line.strip():
            continue
        try:
            args.append(json.loads(line))
        except ValueError:
            args.append(line)              # a bare string argument
    return args


def _answer(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return str(text).strip()           # a bare string answer


def cases(record: dict, shown_only: bool = False) -> list:
    """(arguments, expected) pairs. `shown_only` is what the statement shows.

    The distinction matters more here than it did for EvalPlus: the shown
    cases are literally the worked examples in the problem text, so a suite
    fitted to them is the thing the study is trying to catch, and the hidden
    cases are the contest's own attempt to break exactly that.
    """
    public = json.loads(record.get("public_test_cases") or "[]")
    chosen = public if shown_only else public + _hidden(record)
    return [(_arguments(case["input"]), _answer(case["output"]))
            for case in chosen if case.get("testtype") == "functional"]


def load(after: str | None = None, difficulty: str | None = None) -> dict:
    """Every FUNCTIONAL problem, by task id, optionally cut down.

    `difficulty` is for pilots, and it biases: a set of only hard problems
    answers "can this corpus produce a wrong implementation at all" but says
    nothing about how often one occurs, so a headline rate must come from an
    unfiltered draw.
    """
    tasks = {}
    with open(fetch(), encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("starter_code", "").strip():
                continue                   # a stdin problem: a different shape
            if after and record.get("contest_date", "") < after:
                continue
            if difficulty and record.get("difficulty") != difficulty:
                continue
            if not all(signature(record)):
                continue                   # no class/method to call
            tasks[task_id(record)] = record
    return tasks


def sample(n: int, seed: str = "reticuli", ids: list | None = None,
           after: str | None = None, difficulty: str | None = None) -> list:
    """A deterministic, nested subset -- see corpus.sample for why nested."""
    tasks = load(after, difficulty)
    if ids:
        missing = [i for i in ids if i not in tasks]
        if missing:
            raise KeyError(f"no such task: {', '.join(missing)}")
        return [tasks[i] for i in sorted(ids)]
    order = sorted(tasks)
    random.Random(seed).shuffle(order)
    return [tasks[i] for i in sorted(order[:n])]


def room(record: dict, into: str) -> str:
    """The problem statement and the required signature. Nothing else.

    In particular not the hidden cases, not the difficulty rating, and not the
    contest it came from -- a model told it is solving a `hard` problem is
    being given a hint the study did not intend to give.
    """
    path = os.path.join(into, task_id(record).replace("/", "-"))
    os.makedirs(path, exist_ok=True)
    cls, _ = signature(record)
    with open(os.path.join(path, "TASK.md"), "w", encoding="utf-8") as f:
        f.write(INSTRUCTIONS.format(statement=record["question_content"].strip(),
                                    starter=record["starter_code"], cls=cls))
    return path


def judge(impl_path: str, record: dict, *, budget: float, call_timeout: float,
          shown_only: bool = False) -> dict:
    """Agreement with the contest's own test data."""
    import oracle

    return oracle.judge_cases(impl_path, entry_point(record),
                              cases(record, shown_only=shown_only),
                              budget=budget, call_timeout=call_timeout)


def main() -> int:
    from collections import Counter
    tasks = load()
    counts = [len(cases(t)) for t in tasks.values()]
    dates = sorted(t["contest_date"][:10] for t in tasks.values())
    print(f"corpus: {len(tasks)} functional problems at {LOCAL}")
    print(f"        contests {dates[0]} to {dates[-1]}")
    print(f"        {sum(counts)} judging cases, "
          f"{min(counts)}-{max(counts)} per problem")
    print(f"        difficulty {dict(Counter(t['difficulty'] for t in tasks.values()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
