"""Ground truth, by differential execution against a reference implementation.

The study needs a second opinion on whether a model's code is *actually*
correct, and that opinion has to be independent of anything the model wrote.
A stored test suite is the obvious choice and a poor one: HumanEval's own
tests are weak enough that EvalPlus found roughly a fifth of the solutions
they accept to be wrong, so using them as truth would compress the axis the
study is trying to measure.

So truth here is differential rather than declarative. For each task we hold a
reference implementation and about a thousand generated inputs, and ask a
single question of the candidate:

    for every input, does it return what the reference returns?

That is a stronger oracle than any fixed suite of assertions, and it is not
something a model can have memorised the answers to -- the expected values are
not written down anywhere, they are computed at judging time by running the
reference.

WHAT COUNTS AS DISAGREEMENT, and what does not:

  * The reference rejecting an input (EvalPlus ships each task with a
    `contract` of preconditions) means the input is not part of the task.
    Skipped, and counted as skipped.
  * The candidate raising where the reference returns is a disagreement, and
    so is returning a different value.
  * RUNNING OUT OF CLOCK IS NOT. It was, at first, and that was wrong in a way
    worth recording: the pilot's one "incorrect" implementation turned out to
    compute the right answer for every input, taking twelve seconds on the
    last one because it used trial division where the reference used
    Miller-Rabin. Counting it as wrong would have reported a false finding
    from a correct program. Slowness is reported on its own line, and the
    agreement rate is taken over the inputs that finished.
  * Floats compare with a tolerance, exactly and only where EvalPlus declares
    one; NaN equals NaN, because otherwise a correct implementation of a task
    whose answer is NaN would score zero.

The candidate is model-written code of unknown quality, so it executes in a
child process with a per-call alarm and a whole-task budget, and its stdout is
discarded. A run that exhausts the budget reports how far it got rather than
pretending to a number it did not reach.

    python3 oracle.py --judge <job.json> <result.json>     (the child)
"""
from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys

#: Seconds any single call may have before it is set aside as too slow to
#: judge. Not a correctness threshold -- see `slow` below -- so it can afford
#: to be generous, and needs to be: an implementation may be a thousand times
#: slower than the reference and still be right.
CALL_TIMEOUT = 15.0

#: Seconds a whole task may take. A candidate that is merely slow should not
#: be able to stall the study, and a partial result is reported as partial.
TASK_BUDGET = 180.0

#: Float comparison where EvalPlus declares no tolerance of its own. Present
#: because a task can return a float without being declared float-valued.
REL_TOL = 1e-6


def reference_source(record: dict) -> str:
    """The reference implementation: the prompt, its preconditions, its body.

    EvalPlus stores `canonical_solution` as the body that continues `prompt`,
    and `contract` as assertions guarding the arguments. Assembling all three
    gives a function that computes the task and refuses inputs outside it.
    """
    return record["prompt"] + record.get("contract", "") + record["canonical_solution"]


def same(a, b, atol: float) -> bool:
    """Equality as the task means it, not as Python means it."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False                       # True == 1 is not agreement here
    if isinstance(a, float) or isinstance(b, float):
        if not isinstance(a, int | float) or not isinstance(b, int | float):
            return False
        if math.isnan(a) and math.isnan(b):
            return True                    # a task may legitimately return NaN
        if math.isinf(a) or math.isinf(b):
            return a == b
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=atol or REL_TOL)
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return (type(a) is type(b) and len(a) == len(b)
                and all(same(x, y, atol) for x, y in zip(a, b, strict=True)))
    if isinstance(a, dict) and isinstance(b, dict):
        return (set(a) == set(b)
                and all(same(a[k], b[k], atol) for k in a))
    try:
        return bool(a == b)
    except Exception:  # noqa: BLE001 - a candidate may return literally anything
        return False


# --------------------------------------------------------------- the child


def _judge(job: dict) -> dict:
    """Run both implementations over every input and count the agreements.

    Lives in a child process: the candidate is model-written code that may
    loop forever, exhaust memory, or print a gigabyte, and none of that should
    reach the study.
    """
    import signal
    import time

    class Timeout(Exception):
        pass

    def alarm(_sig, _frame):
        raise Timeout()

    signal.signal(signal.SIGALRM, alarm)
    devnull = open(os.devnull, "w")  # noqa: SIM115 - held open for the whole judging pass

    def call(fn, args, seconds):
        """The candidate's every escape route, closed: time, and stdout."""
        held, sys.stdout = sys.stdout, devnull
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            return fn(*copy.deepcopy(args)), None
        except Timeout:
            return None, "timeout"
        except BaseException as exc:  # noqa: BLE001 - SystemExit included: not an answer
            return None, type(exc).__name__
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            sys.stdout = held

    def resolve(namespace, entry):
        """The function under test, which may be a method on a class.

        LeetCode-style tasks hand the model `class Solution:` with one method,
        so `Solution.twoSum` has to mean what it looks like. A fresh instance
        per call, deliberately: a candidate that caches state between calls
        would otherwise have test cases leak into each other, and each case is
        supposed to be independent.
        """
        if "." not in entry:
            found = namespace.get(entry)
            return found if callable(found) else None
        name, method = entry.split(".", 1)
        cls = namespace.get(name)
        if not isinstance(cls, type):
            return None

        def bound(*args, **kwargs):
            return getattr(cls(), method)(*args, **kwargs)

        return bound if callable(getattr(cls, method, None)) else None

    entry = job["entry_point"]
    result = {"n": 0, "agree": 0, "skipped": 0, "disagree": 0, "slow": 0,
              "candidate_error": None, "truncated": False, "total": len(job["inputs"])}

    # Expected values come either from running a reference implementation
    # (EvalPlus, where truth is differential) or shipped with the task
    # (LiveCodeBench, where truth is the contest judge's own data).
    reference: dict = {}
    if job.get("reference"):
        exec(compile(job["reference"], "<reference>", "exec"), reference)  # noqa: S102

    candidate: dict = {}
    with open(job["candidate"], encoding="utf-8", errors="replace") as f:
        source = f.read()
    try:
        signal.setitimer(signal.ITIMER_REAL, job["call_timeout"])
        held, sys.stdout = sys.stdout, devnull
        try:
            exec(compile(source, "<candidate>", "exec"), candidate)  # noqa: S102
        finally:
            sys.stdout = held
            signal.setitimer(signal.ITIMER_REAL, 0)
    except BaseException as exc:  # noqa: BLE001 - it is model-written code
        # The implementation does not even load. Every input disagrees, and the
        # reason is worth keeping: "SyntaxError" and "wrong answers" are very
        # different findings about a model.
        result["candidate_error"] = f"import: {type(exc).__name__}: {exc}"[:200]
        return result
    subject = resolve(candidate, entry)
    if subject is None:
        result["candidate_error"] = f"nothing callable named {entry!r} was defined"
        return result
    oracle_fn = resolve(reference, entry) if job.get("reference") else None
    answers = job.get("expected")

    deadline = time.monotonic() + job["budget"]
    for index, args in enumerate(job["inputs"]):
        if time.monotonic() > deadline:
            result["truncated"] = True
            break
        if oracle_fn is not None:
            expected, ref_error = call(oracle_fn, args, job["call_timeout"])
            if ref_error:
                result["skipped"] += 1     # outside the task's contract
                continue
        else:
            expected = answers[index]
        actual, cand_error = call(subject, args, job["call_timeout"])
        if cand_error == "timeout":
            # Too slow to judge, which is not the same as wrong. Set aside and
            # counted, so a reader can see how much of the task went unjudged.
            result["slow"] += 1
            continue
        result["n"] += 1
        if cand_error is None and same(expected, actual, job["atol"]):
            result["agree"] += 1
        else:
            result["disagree"] += 1
    if result["slow"] and not result["n"]:
        result["candidate_error"] = (
            f"never finished: all {result['slow']} inputs exceeded "
            f"{job['call_timeout']:.0f}s")
    return result


def run_job(job: dict, budget: float) -> dict:
    """Hand one judging job to a child process and read back the tally."""
    here = os.path.abspath(__file__)
    proc = subprocess.run([sys.executable, here, "--judge", "-"], check=False,
                          input=json.dumps(job), capture_output=True, text=True,
                          timeout=budget + 60)
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"n": 0, "agree": 0, "rate": None, "skipped": 0, "disagree": 0,
                "slow": 0, "candidate_error": f"judge crashed: {proc.stderr[-300:]}",
                "truncated": False, "total": len(job["inputs"])}
    result["rate"] = (result["agree"] / result["n"]) if result["n"] else None
    return result


def judge(candidate_path: str, record: dict, *, budget: float = TASK_BUDGET,
          call_timeout: float = CALL_TIMEOUT, inputs: int | None = None) -> dict:
    """EvalPlus: agreement with a reference implementation, computed as we go."""
    every = list(record.get("base_input") or []) + list(record.get("plus_input") or [])
    return run_job({
        "reference": reference_source(record),
        "candidate": os.path.abspath(candidate_path),
        "entry_point": record["entry_point"],
        "inputs": every[:inputs] if inputs else every,
        "atol": float(record.get("atol") or 0.0),
        "budget": budget, "call_timeout": call_timeout,
    }, budget)


def judge_cases(candidate_path: str, entry: str, cases: list, *,
                budget: float = TASK_BUDGET, call_timeout: float = CALL_TIMEOUT,
                atol: float = 0.0) -> dict:
    """Stored truth: agreement with expected values shipped alongside the task.

    The EvalPlus path computes truth because HumanEval's own stored tests are
    too weak to be truth. That objection does not carry over to a contest
    judge's test data: these are the cases a submission had to pass to be
    accepted, forty-odd per problem against HumanEval's seven, and they were
    written to break wrong solutions rather than to illustrate right ones.
    """
    return run_job({
        "reference": None,
        "candidate": os.path.abspath(candidate_path),
        "entry_point": entry,
        "inputs": [args for args, _ in cases],
        "expected": [expected for _, expected in cases],
        "atol": atol, "budget": budget, "call_timeout": call_timeout,
    }, budget)


def main() -> int:
    if sys.argv[2] == "-":
        source = sys.stdin.read()
    else:
        with open(sys.argv[2], encoding="utf-8") as f:
            source = f.read()
    # The result goes out as the LAST line of stdout: the reference and the
    # candidate are both free to have printed whatever they liked before it.
    print(json.dumps(_judge(json.loads(source))))
    return 0


if __name__ == "__main__":
    sys.exit(main() if len(sys.argv) > 2 and sys.argv[1] == "--judge" else 2)
