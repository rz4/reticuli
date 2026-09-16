"""The experiment: does a model's own test suite predict whether its code works?

One task at a time, and for each of them two numbers that are measured in
completely different ways:

    x   the mutation score of the model's tests against the model's code.
        Everything here is the model's: the artifact, the oracle, and the
        agreement between them. This is what self-verification claims.

    y   agreement with a held-back reference implementation over about a
        thousand inputs the model never saw. This is whether the code works.

The interesting cell is high x with low y -- tests that look thorough over
code that is wrong -- because mutation testing is structurally incapable of
detecting it. Mutating an implementation can only ever measure agreement
between the code and the tests; when both encode the same misreading of the
specification, they agree perfectly and the misreading is invisible. That is
the failure mode particular to a single process writing both halves, and it is
why the study needs an oracle from outside.

Also recorded, as a control: the number of assertions in the suite. If
counting asserts predicts correctness as well as a mutation score does, the
mutation score is not earning what it costs, and saying so is a result.

    python3 run.py --backend stub --n 12           # free, no model calls
    python3 run.py --backend claude --model claude-sonnet-5 --n 25

`--backend stub` is not a model. It fabricates submissions with known
properties -- correct code, code with a boundary fault, code that is plainly
broken -- and exists so the harness can be shown to measure what it claims
before a single dollar is spent on it.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

import author as author_mod
import corpus as corpus_mod
import oracle as oracle_mod

from reticuli import assess as assess_mod
from reticuli import kernel, pack

GATE = "python3 check.py && printf ok > OK"

#: How many candidate faults the stub tries before giving up on finding one its
#: fitted suite misses. Only the stub uses this; it bounds a search, not a
#: measurement.
STUB_SEARCH = 40


# ------------------------------------------------------------------- the stub


def _fitted_check(record: dict, cases: list) -> str:
    """The suite a fitted submission comes with: one assertion per known case.

    This is what "the model wrote tests too" looks like at its weakest -- the
    tests restate values the author already had, so they pass by construction
    and exclude almost nothing.
    """
    entry = record["entry_point"]
    lines = ["import sys", "", "sys.path.insert(0, '.')",
             f"from impl import {entry}", ""]
    lines += [f"assert {entry}(*{args!r}) == {expected!r}" for args, expected in cases]
    return "\n".join(lines) + "\n"


def _stub(record: dict, room: str, index: int) -> dict:
    """A submission whose quadrant we already know, for validating the harness.

    Three kinds, cycled so a small run contains all of them:

      correct           the reference implementation. y must come out at 1.000
                        exactly, or the oracle is broken.
      surviving-mutant  the reference with one fault injected BY THE KERNEL'S
                        OWN INJECTOR, chosen so the fitted suite still passes.
                        Wrong code that its own tests accept: y below 1.
      overfit           a lookup table over exactly the cases the suite tests.
                        It passes every one of them and computes nothing, so it
                        should land in the dangerous cell -- high x, low y --
                        which is the cell the study exists to count.

    If the harness cannot place these three where they belong, no number it
    reports about a real model means anything.
    """
    kind = ("correct", "surviving-mutant", "overfit")[index % 3]
    entry = record["entry_point"]
    canonical = record["prompt"] + record["canonical_solution"]

    reference: dict = {}
    exec(compile(oracle_mod.reference_source(record), "<ref>", "exec"), reference)  # noqa: S102
    cases = []
    for args in (record.get("base_input") or [])[:4]:
        try:
            cases.append((args, reference[entry](*args)))
        except Exception:  # noqa: BLE001,S112 - outside the task's contract
            continue
    check = _fitted_check(record, cases)

    body = canonical
    if kind == "surviving-mutant":
        # Search the injector's own candidates for one the fitted suite misses.
        # Using the instrument under test to build the test case is deliberate:
        # a fault it cannot express is a fault this study cannot see either.
        body, kind = canonical, "correct"
        author_mod.write(room, {"impl.py": canonical, "check.py": check})
        # Bounded in two ways, because a mutated loop condition does not
        # terminate and an unbounded search over hundreds of candidates spends
        # its afternoon waiting for them: a stratified prefix of the pool, and
        # a few seconds each.
        order = kernel._draw_order(kernel._mutants("impl.py", canonical),
                                   record["task_id"])
        for candidate in order[:STUB_SEARCH]:
            source = canonical
            for start, end, replacement in sorted(candidate["edits"], reverse=True):
                source = kernel._splice(source, start, end, replacement)
            if source is None:
                continue
            try:
                compile(source, "<mutant>", "exec")
            except (SyntaxError, ValueError):
                continue
            author_mod.write(room, {"impl.py": source, "check.py": check})
            if author_mod.run_check(room, timeout=5.0)[0]:
                body, kind = source, f"surviving-mutant:{candidate['kind']}"
                break
    elif kind == "overfit":
        table = {repr(tuple(args)): expected for args, expected in cases}
        body = (f"# computes nothing; answers exactly the cases it was shown\n"
                f"TABLE = {table!r}\n\n\n"
                f"def {entry}(*args):\n"
                f"    return TABLE[repr(args)]\n")

    shutil.rmtree(os.path.join(room, "__pycache__"), ignore_errors=True)
    author_mod.write(room, {"impl.py": body, "check.py": check})
    passed, detail = author_mod.run_check(room)
    return {"ok": passed, "turns": 1, "spend": {"tokens": 0, "usd": 0.0},
            "history": [{"turn": 0, "outcome": f"stub:{kind}"}],
            "why": None if passed else " ".join(detail.split())[:160],
            "stub_kind": kind}


# ------------------------------------------------------------------ measuring


def size_of_suite(path: str, entry: str) -> dict:
    """How big the suite is -- the control predictors, counted two ways.

    `asserts` counts `assert` statements and unittest-style assert methods.
    That was the only count at first, and the pilot immediately showed why it
    is not enough: models frequently write a little harness of their own --
    `check(actual, expected, "empty string")` printing PASS -- and a suite full
    of those contains no `assert` at all. Counting zero would have made the
    control look uninformative for a reason that has nothing to do with the
    tests.

    `cases` counts call SITES for the function under test. It is a floor, not a
    count: a table-driven suite calls the subject from one place inside a loop
    and exercises twenty rows, which this reads as 1. `runtime_cases` below is
    the number that should be believed; this one is kept because it is free and
    because the gap between the two says whether a suite is table-driven.
    """
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return {"asserts": None, "cases": None}
    asserts = cases = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            asserts += 1
        elif isinstance(node, ast.Call):
            named = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if named and named.startswith("assert"):
                asserts += 1
            if named == entry:
                cases += 1
    return {"asserts": asserts, "cases": cases}


#: Wraps the function under test so the suite's own run counts itself. Written
#: into a COPY of the room, never the room, so the claim is untouched.
_COUNTER = '''\
import atexit
import os

from _subject import *          # noqa: F403 - re-export whatever the suite imports
import _subject

_seen = [0]
_real = getattr(_subject, {entry!r})


def {entry}(*args, **kwargs):
    _seen[0] += 1
    return _real(*args, **kwargs)


@atexit.register
def _report():
    with open(os.environ["RETICULI_STUDY_COUNT"], "w") as fh:
        fh.write(str(_seen[0]))
'''


def runtime_cases(room: str, entry: str) -> int | None:
    """How many times the suite ACTUALLY calls the function under test.

    Counting call sites in the source is a floor and a misleading one: the
    pilot's suites were mostly table-driven, so a suite exercising twelve
    inputs read as one call. The honest number is dynamic, so the subject is
    replaced by a proxy that tallies its own invocations and the suite is run
    against it. atexit does the reporting, so a suite that fails part way still
    reports what it managed to run.
    """
    work = tempfile.mkdtemp(prefix="study-count-")
    try:
        copy = os.path.join(work, "room")
        shutil.copytree(room, copy, ignore=shutil.ignore_patterns("__pycache__"))
        os.replace(os.path.join(copy, "impl.py"), os.path.join(copy, "_subject.py"))
        with open(os.path.join(copy, "impl.py"), "w", encoding="utf-8") as f:
            f.write(_COUNTER.format(entry=entry))
        tally = os.path.join(work, "count")
        env = dict(os.environ, RETICULI_STUDY_COUNT=tally,
                   PYTHONDONTWRITEBYTECODE="1")
        subprocess.run([sys.executable, "check.py"], cwd=copy, env=env, check=False,
                       capture_output=True, timeout=60)
        with open(tally, encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None                        # the proxy did not survive: say so
    finally:
        shutil.rmtree(work, ignore_errors=True)


def measure(record: dict, room: str, *, mutants: int, budget: float) -> dict:
    """Seal the room as a claim, then take both numbers off it."""
    row: dict = {}
    result = pack.pack(room, record["task_id"].replace("/", "-"),
                       ["impl.py"], ["check.py"], GATE, "OK")
    row["root"] = result.get("root")

    report = assess_mod.assess(room, mutants=mutants)
    row["gate"] = report["gate"]
    score = report["measured"].get("mutation")
    row["x"] = None if not score else score["rate"]
    row["x_by_kind"] = None if not score else {
        k: v["rate"] for k, v in score["by_kind"].items()}
    row["x_sample"] = None if not score else score["mutants"]
    row["x_pool"] = None if not score else score["candidates"]
    row["x_missing"] = None if score else (
        report["not_measured"].get("mutation")
        or report["not_applicable"].get("mutation"))

    impl = os.path.join(room, "impl.py")
    base = len(record.get("base_input") or [])
    weak = oracle_mod.judge(impl, record, budget=budget, inputs=base or None)
    full = oracle_mod.judge(impl, record, budget=budget)
    row["y"] = full["rate"]
    row["y_detail"] = {k: full[k] for k in
                       ("n", "agree", "disagree", "skipped", "slow", "truncated",
                        "candidate_error", "total")}
    row["y_base"] = weak["rate"]
    row.update(size_of_suite(os.path.join(room, "check.py"), record["entry_point"]))
    row["runtime_cases"] = runtime_cases(room, record["entry_point"])
    with open(impl, encoding="utf-8") as f:
        row["impl_lines"] = sum(1 for _ in f)
    return row


# ---------------------------------------------------------------------- main


def one(record: dict, work: str, index: int, args) -> dict:
    started = time.time()
    room = corpus_mod.room(record, work)
    row = {"task_id": record["task_id"], "entry_point": record["entry_point"],
           "backend": args.backend, "model": args.model}
    try:
        if args.backend == "stub":
            written = _stub(record, room, index)
        else:
            written = author_mod.author(room, backend=args.backend,
                                        model=args.model, repairs=args.repairs)
    except Exception as exc:  # noqa: BLE001 - a backend failure is data, not a crash
        row.update({"authored": False, "why": f"{type(exc).__name__}: {exc}"[:300],
                    "seconds": round(time.time() - started, 1)})
        return row

    row["authored"] = written["ok"]
    row["turns"] = written["turns"]
    row["spend"] = written["spend"]
    row["history"] = written["history"]
    row["why"] = written["why"]
    if "stub_kind" in written:
        row["stub_kind"] = written["stub_kind"]

    if written["ok"]:
        try:
            row.update(measure(record, room, mutants=args.mutants,
                               budget=args.budget))
        except kernel.ClaimError as exc:
            row["why"] = f"could not seal: {exc}"[:300]
        except Exception as exc:  # noqa: BLE001
            row["why"] = f"measurement failed: {type(exc).__name__}: {exc}"[:300]
    row["seconds"] = round(time.time() - started, 1)
    return row


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backend", default="stub", choices=["stub", "claude", "openai"])
    p.add_argument("--model", default="claude-sonnet-5")
    p.add_argument("--n", type=int, default=12, help="how many tasks")
    p.add_argument("--seed", default="reticuli", help="which tasks (deterministic)")
    p.add_argument("--tasks", default=None, metavar="ID[,ID...]",
                   help="run exactly these task ids, so a second model faces "
                        "the first one's task set rather than a fresh draw")
    p.add_argument("--mutants", type=int, default=24)
    p.add_argument("--repairs", type=int, default=2,
                   help="turns the model may take to fix what its own tests catch")
    p.add_argument("--budget", type=float, default=oracle_mod.TASK_BUDGET,
                   help="seconds of judging per task")
    p.add_argument("--out", default=os.path.join(HERE, "results"))
    p.add_argument("--keep", action="store_true", help="keep the task rooms")
    args = p.parse_args()

    named = [t.strip() for t in (args.tasks or "").split(",") if t.strip()]
    records = corpus_mod.sample(args.n, args.seed, ids=named or None)
    os.makedirs(args.out, exist_ok=True)
    stamp = f"{args.backend}-{args.model}-{len(records)}".replace("/", "_")
    work = os.path.join(args.out, f"rooms-{stamp}")
    os.makedirs(work, exist_ok=True)
    path = os.path.join(args.out, f"{stamp}.jsonl")

    print(f"{len(records)} tasks, backend {args.backend}"
          f"{'' if args.backend == 'stub' else ' (' + args.model + ')'}, "
          f"{args.mutants} mutants each -> {path}", file=sys.stderr)
    spent = 0.0
    with open(path, "w", encoding="utf-8") as out:
        for index, record in enumerate(records):
            row = one(record, work, index, args)
            spent += (row.get("spend") or {}).get("usd", 0.0)
            out.write(json.dumps(row, sort_keys=True) + "\n")
            out.flush()
            x = "-" if row.get("x") is None else f"{row['x']:.2f}"
            y = "-" if row.get("y") is None else f"{row['y']:.3f}"
            note = row.get("stub_kind") or ("" if row.get("authored") else "UNAUTHORED")
            why = " ".join((row.get("why") or "").split())
            print(f"  {row['task_id']:16} x={x:>5}  y={y:>6}  "
                  f"cases={row.get('cases') or '-'!s:>3}  "
                  f"{row['seconds']:>6.1f}s  {note} {why}"[:170],
                  file=sys.stderr)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {path}" + (f"  (${spent:.2f})" if spent else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
