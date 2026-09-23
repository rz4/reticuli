"""Run one generation of the contraction loop, and self-test the instrument.

With no producers wired yet, `python3 pilot.py` runs the whole pipeline over the
hand-written fixtures: gate against C_0, find disagreements, reduce one to its
minimal witness, take a (simulated) keyholder adjudication, tighten to C_1, and
re-gate to show the basin contract. Zero producer spend — this proves the
measuring tools before a single rebuild draws on the codex window.

At generation 0 of the real pilot, the fixtures are replaced by `k` blind
rebuilds and the adjudication becomes a real keyholder call; nothing else here
changes.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import base64_subject
import boundary
import differential
import quirkcalc_subject
from metrics import Generation, compute

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
TAU = 0.30  # frozen clustering threshold
SUBJECTS = {"base64": base64_subject, "quirkcalc": quirkcalc_subject}


def _use(subject):
    """Select a subject: its C_0, its probes, and the operation to compare on."""
    c0 = subject.C0()
    boundary.OP = c0.op  # the differential/reducer reach the operation through this
    return c0, subject.probes()


def load_impls(directory: Path) -> tuple[dict, dict]:
    """Load every .py in a directory as an implementation. Returns
    ({name: module}, {name: source})."""
    impls, sources = {}, {}
    for path in sorted(directory.glob("*.py")):
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"impl_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        impls[name] = mod
        sources[name] = path.read_text()
    return impls, sources


def gate_population(boundary, impls, sources):
    """Keep only implementations that satisfy the boundary."""
    survivors, surv_src, rejected = {}, {}, {}
    for name, mod in impls.items():
        ok, fails = boundary.gate(mod)
        if ok:
            survivors[name] = mod
            surv_src[name] = sources[name]
        else:
            rejected[name] = fails
    return survivors, surv_src, rejected


def report(m: dict) -> None:
    print(f"  generation {m['generation']}: "
          f"R={m['R']} ({m['R_count']}/{m['attempts']})  "
          f"S={m['S']} ({m['clusters']} clusters)  D={m['D']}  "
          f"U={m['U']}  A={m['A']}  Y={m['Y']}  Y*={m['Ystar']}  K*={m['Kstar']}")


def main(outdir: str | None = None) -> int:
    c0, probes = _use(base64_subject)
    impls, sources = load_impls(FIXTURES)
    print(f"instrument self-test: {len(impls)} fixtures, {len(probes)} probes\n")

    # --- Generation 0: the partial boundary ---
    surv0, src0, rej0 = gate_population(c0, impls, sources)
    print("C_0 (round-trip + RFC vectors only)")
    for name, fails in rej0.items():
        print(f"  rejected {name}: {fails[0]}")
    gen0 = Generation(n=0, attempts=len(impls), survivors=surv0, sources=src0,
                      costs=dict.fromkeys(surv0))
    m0 = compute(gen0, probes, TAU)
    report(m0)

    # Show the reducer and the classing: one question per class, not per input.
    raw = differential.disagreements(surv0, probes)
    print(f"\n  {len(raw)} raw disagreements collapse to {m0['U']} distinct "
          f"questions (classes):")
    for c in m0["novel_classes"]:
        print(f"    {c['witness']!r:>10}  accept={c['accept']}  reject={c['reject']}")

    # --- Simulated keyholder adjudication ---
    # The keyholder rules that malformed input must be rejected, but will not
    # accept a counterexample that collapses the population — structural
    # diversity is the thing being protected. Accept greedily while at least
    # three implementations survive. A real generation gets a human here, one
    # decision per class, with these same metrics in front of them.
    accepted: list[tuple[str, tuple]] = []
    for c in m0["novel_classes"]:
        trial = accepted + [(c["witness"], ("err",))]
        surv_trial, _, _ = gate_population(c0.tighten(trial), impls, sources)
        if len(surv_trial) >= 3:
            accepted = trial
        if len(accepted) >= 2:
            break
    print(f"\n  keyholder accepts {len(accepted)} counterexamples (must-reject, "
          f"guarding the structural floor): {[w for w, _ in accepted]}")
    gen0.adjudication = {w: "counterexample" for w, _ in accepted}
    m0 = compute(gen0, probes, TAU)
    report(m0)

    # --- Generation 1: tightened boundary ---
    c1 = c0.tighten(accepted)
    surv1, src1, rej1 = gate_population(c1, impls, sources)
    print(f"\nC_1 (C_0 + {len(accepted)} pinned decode rules)")
    for name, fails in rej1.items():
        print(f"  now rejected {name}: {fails[0]}")
    gen1 = Generation(n=1, attempts=len(impls), survivors=surv1, sources=src1,
                      costs=dict.fromkeys(surv1),
                      prior_witnesses=set(m0["all_witnesses"]))
    m1 = compute(gen1, probes, TAU)
    report(m1)

    contracted = m1["D"] < m0["D"]
    print(f"\ninstrument self-test: {'PASS' if _passes(m0, m1) else 'CHECK'} — "
          f"behavioral diversity {m0['D']} -> {m1['D']} "
          f"({'contracted' if contracted else 'did not contract'}), "
          f"structure preserved (S {m0['S']} -> {m1['S']}, "
          f"clusters {m0['clusters']} -> {m1['clusters']})")

    if outdir:
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "gen0.json").write_text(json.dumps(m0, indent=2))
        (out / "gen1.json").write_text(json.dumps(m1, indent=2))
        print(f"\nwrote gen0.json, gen1.json to {out}")
    return 0


def _passes(m0: dict, m1: dict) -> bool:
    # The instrument works if every metric computed, a minimal witness was
    # produced, an adjudication tightened the boundary, and one contraction
    # step is visible with structure preserved.
    return (m0["U"] > 0 and m0["A"] > 0 and m0["novel_witnesses"]
            and m1["D"] <= m0["D"] and m1["clusters"] >= 2)


def _load_one(path: str):
    p = Path(path)
    spec = importlib.util.spec_from_file_location(f"oracle_{p.stem}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _truth_report(survivors: dict, truth, probes: list[str]) -> dict:
    """When ground truth is available, the number that matters is distance from
    truth, not between rebuilds. A shared miss — every rebuild agreeing on a
    wrong answer — is invisible to a rebuild-vs-rebuild differential but is the
    thing contraction has to close."""
    correct = shared_miss = split = 0
    for p in probes:
        vals = {boundary.call(m, p) for m in survivors.values()}
        tv = boundary.call(truth, p)
        if len(vals) > 1:
            split += 1
        elif vals == {tv}:
            correct += 1
        else:
            shared_miss += 1
    return {"correct": correct, "shared_miss": shared_miss, "split": split}


def survey(subject_name: str, impls_dir: str, outdir: str | None = None,
           generation: int = 0, oracle: str | None = None) -> int:
    """Measure one generation of REAL rebuilds and present the disagreement
    classes — then stop. No simulated keyholder: on real data the adjudication
    is a human's, so this only surfaces the questions. With an oracle (ground
    truth), it also reports distance from truth and marks truth in each class.
    """
    subject = SUBJECTS[subject_name]
    c0, probes = _use(subject)
    c = c0
    if generation >= 1 and hasattr(subject, "C1_RULES"):
        c = c0.tighten(subject.C1_RULES)  # gate against C_1
    impls, sources = load_impls(Path(impls_dir))
    print(f"survey ({subject_name}, C_{generation}): {len(impls)} rebuilds from "
          f"{impls_dir}, {len(probes)} probes\n")

    surv, src, rej = gate_population(c, impls, sources)
    for name, fails in rej.items():
        print(f"  outside C_0 (not a valid rebuild): {name}: {fails[0]}")
    gen = Generation(n=generation, attempts=len(impls), survivors=surv,
                     sources=src, costs=dict.fromkeys(surv))
    m = compute(gen, probes, TAU)
    report(m)

    truth = _load_one(oracle) if oracle else None
    if truth is not None:
        tr = _truth_report(surv, truth, probes)
        print(f"\n  vs ground truth over {len(probes)} probes: "
              f"{tr['correct']} correct, {tr['shared_miss']} SHARED MISSES "
              f"(all rebuilds agree, all wrong), {tr['split']} split")
        # classes over rebuilds ∪ truth, so shared misses surface as questions
        pop = dict(surv, __truth__=truth)
        gen_t = Generation(n=generation, attempts=len(impls), survivors=pop,
                           sources=dict(src, __truth__=""), costs={})
        mt = compute(gen_t, probes, TAU)
        print(f"\n  {mt['U']} questions vs truth (the correct answer is truth's):")
        for c in mt["novel_classes"]:
            groups = "  ".join(
                f"{g['value']}{'*' if '__truth__' in g['members'] else ''}:"
                f"{len(g['members'])}" for g in c["groups"])
            print(f"    {c['witness']!r:>14}   {groups}    (* = truth)")
        m = mt  # persist the truth-aware view
    else:
        print(f"\n  {m['U']} distinct questions (rebuild-vs-rebuild):")
        for c in m["novel_classes"]:
            groups = "  ".join(f"{g['value']}:{len(g['members'])}" for g in c["groups"])
            print(f"    {c['witness']!r:>14}   {groups}")

    if outdir:
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"gen{generation}.json").write_text(json.dumps(m, indent=2))
        print(f"\n  wrote gen{generation}.json to {out}")
    print("\n  awaiting adjudication — no boundary moves without a keyholder.")
    return 0


if __name__ == "__main__":
    # Self-test:  python3 pilot.py [outdir]
    # Real survey: pilot.py --survey <subject> <impls> [outdir] [oracle.py] [generation]
    if len(sys.argv) > 1 and sys.argv[1] == "--survey":
        sys.exit(survey(sys.argv[2], sys.argv[3],
                        sys.argv[4] if len(sys.argv) > 4 else None,
                        generation=int(sys.argv[6]) if len(sys.argv) > 6 else 0,
                        oracle=sys.argv[5] if len(sys.argv) > 5 else None))
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
