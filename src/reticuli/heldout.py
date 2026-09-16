"""Held-out evaluation: do the tests generalise, or do they only enumerate?

Mutation adequacy asks how narrow a claim is around the implementation it
already has. This asks the other question: how much of the behaviour lives in
the PRODUCER rather than in the claim. Take a claim whose pinned inputs
include a case corpus, hide a fraction of the cases, re-seal on the rest -- a
different root: fewer inputs, the same gate -- and let producers regrow the
implementation blind from the kept cases alone. Then judge each rebuild on the
HIDDEN cases, one case at a time.

Per producer: the held-out pass rate p. A high p means the retained cases
carried the behaviour, so the tests are a specification. A low p means they
enumerated: the producer had no way to know what the hidden cases demand,
because the claim never named it anywhere but in the cases themselves.

Per pair of producers: the observed agreement a -- the share of held-out cases
where both pass or both fail -- against the agreement two independent coin
flips at those rates would show, e = p1*p2 + (1-p1)(1-p2). The EXCESS a - e is
the headline number. Around zero means the claim accounts for all the
agreement: the producers agree exactly where it forces them to. Above zero
means they share structure the claim never named -- a convention, a common
training corpus, a default both reached for and the tests never excluded.

Two properties this module is built around, both load-bearing:

  * THE MEASURED CLAIM IS NEVER TOUCHED. Every re-seal, rebuild and judgment
    happens on copies in a scratch workspace, and no residue is written back.
    A measurement that mutated its subject would be worth nothing, and the
    subject here is a sealed identity that must still verify afterwards.

  * THE GATE MUST TOLERATE A SUBSET of the corpus -- it has to judge whatever
    cases are present in the workspace, not a list it carries. A checker that
    globs `cases/*`, or pytest over a directory, is that shape; a gate that
    hard-codes its filenames is not, and this module refuses such a claim
    rather than reporting a rate that only measures the refusal.
"""
from __future__ import annotations

import copy
import fnmatch
import itertools
import os
import random
import shutil
import stat
import tempfile

from . import _util, kernel, render

#: What fraction of the corpus to hide when the caller does not say. Small
#: enough that the kept cases are still a plausible specification, large enough
#: that the rate has resolution: 0.3 of 59 cases is 18 independent judgments.
DEFAULT_HOLDOUT = 0.3


# ------------------------------------------------------------- the corpus

def case_corpus(recipe: dict, pattern: str | None = None) -> list[str]:
    """Which pinned inputs are the CASE CORPUS -- the part that may be hidden.

    With a pattern the caller says. Without one it is inferred, because the
    format does not declare the distinction: the corpus is the largest family
    of inputs sharing a top-level directory. Grouping by the FIRST path
    segment rather than the full dirname keeps a nested corpus
    (`cases/invalid/array/…`) one family instead of dozens of singletons, and
    a loose file at the claim's root is never a corpus on its own.

    Whatever a gate EXECUTES is excluded however it is named and however it is
    matched. The acceptance test is the thing doing the judging; hiding it
    would not measure generalisation, it would measure nothing at all.
    """
    inputs = _util.declared_inputs(recipe)
    deciders = {d.removeprefix("./")
                for step in kernel.gates(recipe)
                for d in kernel.gate_deciders(step.get("run") or "")}

    if pattern:
        chosen = [n for n in inputs if fnmatch.fnmatch(n, pattern)]
        judging = [n for n in chosen if n.removeprefix("./") in deciders]
        if judging:
            raise kernel.ClaimError(
                f"{pattern!r} matches what the gate runs ({', '.join(judging)}); "
                "the acceptance test cannot be held out from itself")
        return chosen

    families: dict[str, list[str]] = {}
    for name in inputs:
        if name.removeprefix("./") in deciders:
            continue
        head, _, tail = name.replace(os.sep, "/").partition("/")
        if not head or not tail:
            continue
        families.setdefault(head, []).append(name)
    ranked = sorted(families.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    if not ranked:
        return []
    # A tie is genuine ambiguity, and picking the alphabetically first would
    # silently measure one corpus while the reader assumed the other.
    if len(ranked) > 1 and len(ranked[1][1]) == len(ranked[0][1]):
        raise kernel.ClaimError(
            f"two input families are the same size ({ranked[0][0]}/ and "
            f"{ranked[1][0]}/, {len(ranked[0][1])} files each); name the case "
            "corpus explicitly rather than letting it be guessed")
    return list(ranked[0][1])


def split(cases: list[str], fraction: float, seed) -> tuple[list[str], list[str]]:
    """Hide `fraction` of the corpus. Returns (kept, held out), both sorted.

    The shuffle is seeded from the claim's ROOT, exactly as `mutation_score`
    draws its sample: the split is then reproducible by anyone holding the
    claim, and it cannot be shopped for by re-rolling until a flattering set of
    cases lands in the hidden half. v1 exposed a `--seed` for this; deliberately
    not carried.

    Both halves are non-empty by construction. An empty kept half leaves the
    producer nothing to build from, and an empty hidden half leaves nothing to
    judge -- either way the run would report a number that measured neither.
    """
    order = list(cases)
    random.Random(seed).shuffle(order)
    k = min(max(1, round(len(order) * fraction)), len(order) - 1) if len(order) > 1 else 0
    return sorted(order[k:]), sorted(order[:k])


def agreement(a: dict, b: dict) -> dict:
    """Two producers' held-out outcomes: observed agreement, expected, excess.

    The rates are recomputed here from the cases the two producers actually
    share rather than taken from their stored pass rates, so the three numbers
    are always arithmetically consistent with each other even if one producer
    was judged on a different set.
    """
    shared = sorted(set(a) & set(b))
    if not shared:
        return {"cases": 0, "agreement": None, "expected": None, "excess": None}
    observed = sum(1 for c in shared if bool(a[c]) == bool(b[c])) / len(shared)
    pa = sum(1 for c in shared if a[c]) / len(shared)
    pb = sum(1 for c in shared if b[c]) / len(shared)
    expected = pa * pb + (1 - pa) * (1 - pb)
    return {"cases": len(shared), "agreement": observed,
            "expected": expected, "excess": observed - expected}


# ------------------------------------------------------- the restricted claim

def _place(src: str, dst: str) -> None:
    """Copy one declared file into a workspace, carrying its permission bits.

    A generated output may legitimately BE an executable -- a compiled binary --
    and `copyfile` drops the exec bit, so a gate that runs its own output would
    fail with "Permission denied" in every workspace this module builds. The
    kernel's own materializer carries the low nine bits for that reason; only
    those nine, never setuid/setgid/sticky.
    """
    _util.copy_into(src, dst)
    os.chmod(dst, stat.S_IMODE(os.stat(src).st_mode) & 0o777)


def _restrict(claimdir: str, recipe: dict, corpus: list[str], keep: list[str],
              into: str, implementation: str | None = None) -> dict:
    """Lay the claim out at `into` with only `keep` of its case corpus present.

    The result is THE SAME CLAIM with fewer pinned inputs: same steps, same
    gate, a different root. `implementation` supplies the generated bytes when
    they are to come from somewhere other than the claim -- a producer's
    rebuild, when this workspace is a judging room.

    Gate outputs are deliberately not copied. A gate must re-earn its verdict
    from the bytes present, and a carried verdict would make every measurement
    here vacuous: the room would already contain the answer it is being asked
    to produce.
    """
    hidden = set(corpus) - set(keep)
    restricted = copy.deepcopy(recipe)
    restricted["claim"]["inputs"] = [n for n in _util.declared_inputs(recipe)
                                     if n not in hidden]

    os.makedirs(into, exist_ok=True)
    for name in restricted["claim"]["inputs"]:
        _place(_util.safe_path(claimdir, name), _util.safe_path(into, name))
    for step in kernel.produces(recipe):
        name = step.get("output")
        if not isinstance(name, str) or not name:
            continue
        source_dir = claimdir
        if implementation and step.get("class") == "generated":
            source_dir = implementation
        source = _util.safe_path(source_dir, name)
        if os.path.isfile(source):
            _place(source, _util.safe_path(into, name))

    with open(os.path.join(into, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(restricted))
    # Read back what was written and demand it be the original recipe minus the
    # hidden inputs and nothing else. The recipe writer emits the keys it knows
    # about, so a key it does not know would vanish here silently -- and the
    # measurement would then be of a DIFFERENT claim than the one on disk,
    # reported under this claim's name. Refusing is the only honest answer.
    written = kernel.load_recipe(into)
    if written != restricted:
        lost = sorted(set(restricted.get("claim") or {}) - set(written.get("claim") or {}))
        raise kernel.ClaimError(
            "the claim does not survive being restricted to a subset of its cases"
            + (f": the [claim] keys {', '.join(lost)} are dropped when the recipe "
               "is rewritten" if lost else ": the rewritten recipe differs")
            + " -- a held-out run would measure a different claim")
    return restricted


def _gate_verdict(workdir: str, recipe: dict) -> tuple[bool, str]:
    """Run every gate in `workdir`. Returns (all passed, the tail of why not).

    Gates go through the kernel's one entry point, so a judgment here is run
    scrubbed, bounded and sandboxed exactly as `audit` would run it -- a
    held-out pass earned under looser conditions than the claim's own would not
    be comparable with anything.
    """
    for step in kernel.gates(recipe):
        outcome = kernel.run_gate(step["run"], workdir, recipe)
        if outcome["status"] != "ok":
            detail = (outcome.get("stderr") or outcome.get("stdout") or "").strip()
            return False, detail[-200:]
    return True, ""


def _judge(claimdir: str, recipe: dict, corpus: list[str], case: str,
           implementation: str) -> bool:
    """Run the claim's gate with exactly ONE case present: the held-out one.

    One case per room, rather than all the hidden cases at once, because a gate
    stops at its first failure: judged as a batch, a producer that misses one
    case and a producer that misses seventeen would score identically, and the
    agreement statistic -- which needs a per-case outcome vector -- would have
    nothing to compare.
    """
    scratch = tempfile.mkdtemp(prefix="reticuli-heldout-")
    try:
        room = os.path.join(scratch, "room")
        _restrict(claimdir, recipe, corpus, [case], room, implementation=implementation)
        return _gate_verdict(room, recipe)[0]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------- the producers

def parse_producers(spec) -> list[tuple[str, str]]:
    """Normalise `NAME=COMMAND` producer specs into ordered (name, command).

    Names are the reader's handle on the rows and on the pairings, so a
    duplicate is refused rather than quietly overwriting the earlier one and
    reporting two different producers under one name.
    """
    if isinstance(spec, dict):
        spec = list(spec.items())
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in spec or []:
        if isinstance(entry, (tuple, list)) and len(entry) == 2:
            name, command = entry
        else:
            name, separator, command = str(entry).partition("=")
            if not separator:
                raise kernel.ClaimError(
                    f"a held-out producer is NAME=COMMAND, got {entry!r}")
        name, command = str(name).strip(), str(command).strip()
        if not name or not command:
            raise kernel.ClaimError(f"a held-out producer is NAME=COMMAND, got {entry!r}")
        if name in seen:
            raise kernel.ClaimError(f"two held-out producers are both named {name!r}")
        seen.add(name)
        out.append((name, command))
    return out


def _row(name: str, *, blind: bool, landed: bool, held: list[str],
         outcomes: dict | None = None, root=None, cost=None, why=None) -> dict:
    outcomes = dict(sorted((outcomes or {}).items()))
    passed = sum(1 for v in outcomes.values() if v)
    return {"name": name, "blind": blind, "landed": landed,
            "pass_rate": (passed / len(outcomes)) if outcomes else None,
            "passed": passed if outcomes else None, "of": len(held),
            "outcomes": outcomes, "root": root, "cost": cost, "why": why}


# ------------------------------------------------------------ the measurement

def measure(claimdir: str, *, fraction: float = DEFAULT_HOLDOUT, producers=None,
            cases: str | None = None, into: str | None = None) -> dict:
    """Measure generalisation: hide cases, rebuild blind, judge on the hidden.

    `producers` is a list of `NAME=COMMAND` (or (name, command) pairs); each is
    asked to regrow the implementation from the kept cases alone. `cases` names
    the corpus when it should not be inferred, `fraction` how much of it to
    hide, `into` keeps the scratch workspace instead of deleting it.

    Refuses in band, via ClaimError, whenever the claim is the wrong shape for
    this measurement -- no corpus, no gate, a gate that cannot judge a subset.
    A refusal is reported by the caller as "not applicable"; it is emphatically
    not a low score.
    """
    claimdir = os.path.abspath(claimdir)
    recipe = kernel.load_recipe(claimdir)
    manifest = kernel.read_manifest(claimdir)
    try:
        fraction = float(fraction)
    except (TypeError, ValueError):
        raise kernel.ClaimError(
            f"the held-out fraction must be a number, got {fraction!r}") from None
    if not 0.0 < fraction < 1.0:
        raise kernel.ClaimError(
            f"the held-out fraction must lie strictly between 0 and 1, got {fraction}")
    if not kernel.gates(recipe):
        raise kernel.ClaimError(
            "the claim declares no gate, so a held-out case has nothing to judge it")

    corpus = case_corpus(recipe, cases)
    if len(corpus) < 2:
        raise kernel.ClaimError(
            "no case corpus to hold out: this claim's pinned inputs are not a family "
            "of cases a gate judges one by one"
            + (f" (nothing but {len(corpus)} file(s) matched {cases!r})" if cases else ""))
    rows = parse_producers(producers)
    kept, held = split(corpus, fraction, manifest.get("root") or "")

    work = os.path.abspath(into) if into else tempfile.mkdtemp(prefix="reticuli-heldout-")
    # A kept workspace must start empty, for the reason `rebuild` refuses a
    # non-empty target: a leftover rebuild from an earlier run would be judged
    # as this run's, and the number would name the wrong producer.
    if into and os.path.exists(work) and (not os.path.isdir(work) or os.listdir(work)):
        raise kernel.ClaimError(f"the held-out workspace already holds something: {work}")
    try:
        kept_dir = os.path.join(work, "kept")
        _restrict(claimdir, recipe, corpus, kept, kept_dir)
        # Warm the gate before sealing, exactly as `pack` does: the gate writes
        # its own verdict, and that verdict's bytes are inside the kept claim's
        # root. A gate that cannot pass on the kept cases alone is a gate that
        # judges a fixed list, which is the one claim shape this method cannot
        # measure -- so say that, rather than blaming the producers for it.
        ok, why = _gate_verdict(kept_dir, recipe)
        if not ok:
            raise kernel.ClaimError(
                f"the gate does not pass with {len(kept)} of {len(corpus)} cases present, "
                "so nothing can be rebuilt from them: it judges a fixed list rather than "
                f"the cases in the workspace. {why}")
        kept_root = kernel.seal(kept_dir)["root"]

        results = []
        # The claim's own implementation is a CONTROL, not a producer. It was
        # written with every case in view, so its held-out rate is no evidence
        # about the claim -- but it is the rig's own check: anything below 1.00
        # means the judging room is built wrong, not that the tests fail to
        # generalise. For the same reason it stays out of the pairings, where
        # an implementation that passes everything makes the excess identically
        # zero and says nothing. (v1 paired it; deliberately not carried.)
        results.append(_row("sealed", blind=False, landed=True, held=held,
                            outcomes={c: _judge(claimdir, recipe, corpus, c, claimdir)
                                      for c in held},
                            root=manifest.get("root")))

        for index, (name, command) in enumerate(rows):
            # An index names the directory, never the producer's own name: the
            # name arrives from a command line, and a path separator in it would
            # put a workspace somewhere nobody asked for.
            target = os.path.join(work, f"p{index}")
            try:
                rebuilt = kernel.rebuild(kept_dir, command, target)
            except kernel.ClaimError as exc:
                # Not landing is a real outcome and is reported as one: the
                # producer could not satisfy even the KEPT cases, so there is
                # nothing to judge on the hidden ones. It is not a zero.
                results.append(_row(name, blind=True, landed=False, held=held,
                                    why=str(exc)[-200:]))
                continue
            landed = rebuilt.get("root") == kept_root
            outcomes = ({c: _judge(claimdir, recipe, corpus, c, target) for c in held}
                        if landed else {})
            results.append(_row(
                name, blind=True, landed=landed, held=held, outcomes=outcomes,
                root=rebuilt.get("root"), cost=kernel.cost(target),
                why=None if landed else
                "the rebuild passed the gate but sealed a root the kept claim does not name"))

        pairs = []
        blind_rows = [r for r in results if r["blind"] and r["landed"]]
        for a, b in itertools.combinations(blind_rows, 2):
            pairs.append({"a": a["name"], "b": b["name"],
                          **agreement(a["outcomes"], b["outcomes"])})

        return {
            "claim": manifest.get("name"), "root": manifest.get("root"),
            "kept_root": kept_root, "corpus": cases or "inferred",
            "cases": len(corpus), "kept": len(kept), "held_out": len(held),
            "fraction": fraction, "held": held,
            "producers": results, "pairs": pairs,
            "workspace": work if into else None,
        }
    finally:
        if not into:
            shutil.rmtree(work, ignore_errors=True)
