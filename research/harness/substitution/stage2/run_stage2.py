"""Stage 2 of the substitution demonstrator: blind cross-family rebuilds.

Rebuilds the dependency claim `claims/D` from its boundary C_0 alone — no
reference implementation, no guidance — through two producer families
(codex/OpenAI and Claude Code/Anthropic, both un-metered), then judges every
reconstruction three ways:

  C_0   the dependency's own gate (a successful rebuild passed it by
        construction; re-earned here anyway),
  P     the consumer's contract, judged by auditing claim `claims/P` with the
        reconstruction substituted for its generated parser (gates compose:
        P's root commits to the contract, never to parser bytes),
  C_1   the tightened boundary `claims/D1`, judged the same way.

Identity discipline along the way: every accepted rebuild re-earns D's root
(the kernel now refuses a producer that touches pinned bytes), P's root never
moves while its dependency is swapped, and the build digests record which
realizations are distinct bytes.

Paced and resumable like the contraction runner: each rebuild has its own
directory, an existing reconstruction is ingested rather than re-spent, and a
quota signal stops the run cleanly.

    python3 research/harness/substitution/stage2/run_stage2.py [--judge-only]
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "src"))
from reticuli import kernel  # noqa: E402

VENV_PY = str(REPO / ".venv" / "bin" / "python")
D, D1, P = HERE / "claims/D", HERE / "claims/D1", HERE / "claims/P"
SCRATCH, IMPLS = HERE / "scratch", HERE / "impls"

#: (family, producer module, model) — three reconstructions per family.
PLAN = [
    ("codex", "reticuli.producers.codex", "gpt-6-luna"),
    ("codex", "reticuli.producers.codex", "gpt-6-sol"),
    ("codex", "reticuli.producers.codex", "gpt-6-astra"),
    ("claude", "reticuli.producers.claude", "sonnet"),
    ("claude", "reticuli.producers.claude", "opus"),
    ("claude", "reticuli.producers.claude", "haiku"),
]

QUOTA = re.compile(r"usage limit|rate limit|try again|quota|429", re.IGNORECASE)


def rebuild_all(claim=None, impls=None, prefix="rebuild") -> None:
    claim, impls = claim or D, impls or IMPLS
    impls.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for idx, (family, module, model) in enumerate(PLAN):
        tag = f"{idx:02d}_{family}_{model.replace('-', '_')}"
        out = SCRATCH / f"{prefix}_{tag}"
        dest = impls / f"impl_{tag}.py"
        if dest.exists():
            print(f"[{tag}] already ingested", flush=True)
            continue
        if out.exists():
            shutil.rmtree(out)  # a failed attempt left bytes; the kernel refuses them
        print(f"[{tag}] rebuilding blind...", flush=True)
        os.environ["RETICULI_MODEL"] = model
        os.environ["RETICULI_VENDOR"] = family
        producer = f"{VENV_PY} -P -m {module}"
        try:
            r = kernel.rebuild(str(claim), producer, str(out), guidance=False,
                               producer_env={"RETICULI_MODEL": model})
        except kernel.ClaimError as exc:
            text = str(exc)
            if QUOTA.search(text):
                print(f"[{tag}] QUOTA — stopping; re-run to resume.", flush=True)
                break
            print(f"[{tag}] did not converge: {text[-300:]}", flush=True)
            continue
        assert r["root"] == kernel.verify(str(claim))["root"], \
            "a rebuild that lands is the claim: one root"  # the kernel enforced this
        shutil.copy(out / "parser.py", dest)
        print(f"[{tag}] converged -> {dest.name}", flush=True)


def judge_all() -> dict:
    d_root = kernel.verify(str(D))["root"]
    d_digest = kernel.build_digest(str(D))
    p_root_before = kernel.verify(str(P))["root"]

    rows, digests = [], {}
    for impl in sorted(IMPLS.glob("impl_*.py")):
        tag = impl.stem.removeprefix("impl_")
        rebuilt = SCRATCH / f"rebuild_{tag}"
        row = {"impl": impl.name}
        if rebuilt.is_dir():
            row["d_root_held"] = kernel.verify(str(rebuilt))["root"] == d_root
            row["build_digest"] = kernel.build_digest(str(rebuilt))
        else:
            row["d_root_held"] = None      # scratch gone; identity was asserted at rebuild
            row["build_digest"] = None
        digests[impl.name] = row["build_digest"]
        row["c0"] = kernel.audit(str(D), produce_from={"parser.py": str(impl)})["ok"]
        row["consumer"] = kernel.audit(str(P), produce_from={"parser.py": str(impl)})["ok"]
        row["c1"] = kernel.audit(str(D1), produce_from={"parser.py": str(impl)})["ok"]
        rows.append(row)

    p_root_after = kernel.verify(str(P))["root"]
    result = {
        "d_root": d_root,
        "d_reference_digest": d_digest,
        "p_root_stable": p_root_before == p_root_after,
        "distinct_realizations": len({d for d in digests.values() if d}),
        "rows": rows,
    }
    with open(HERE / "results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    return result


def report(result: dict) -> None:
    print(f"\nstage 2 — blind cross-family rebuilds of kvparse "
          f"(D root {result['d_root'][:12]})\n")
    print(f"  {'reconstruction':34} {'D root':>7} {'C_0':>5} {'consumer P':>11} {'C_1':>5}")
    for row in result["rows"]:
        held = {True: "held", False: "MOVED", None: "-"}[row["d_root_held"]]
        print(f"  {row['impl']:34} {held:>7} "
              f"{('yes' if row['c0'] else 'no'):>5} "
              f"{('ok' if row['consumer'] else 'BREAKS'):>11} "
              f"{('yes' if row['c1'] else 'no'):>5}")
    n = len(result["rows"])
    c0 = sum(r["c0"] for r in result["rows"])
    ok = sum(r["consumer"] for r in result["rows"])
    c1 = sum(r["c1"] for r in result["rows"])
    c1_safe = all(r["consumer"] for r in result["rows"] if r["c1"])
    print(f"\n  {c0}/{n} pass C_0; {ok}/{n} keep the consumer working; "
          f"{c1}/{n} pass the tightened C_1.")
    print(f"  every C_1-passer keeps the consumer working: {c1_safe}")
    print(f"  P's root never moved while its dependency was swapped: "
          f"{result['p_root_stable']}")
    print(f"  distinct realizations by build digest: "
          f"{result['distinct_realizations']}/{n}")


IMPLS_C1 = HERE / "impls_c1"


def round2() -> None:
    """The ratchet's payoff: rebuild blind from the TIGHTENED boundary C_1
    and show the reconstructions now keep the consumer working."""
    rebuild_all(claim=D1, impls=IMPLS_C1, prefix="c1_rebuild")
    rows = []
    for impl in sorted(IMPLS_C1.glob("impl_*.py")):
        rows.append({
            "impl": impl.name,
            "c1": kernel.audit(str(D1), produce_from={"parser.py": str(impl)})["ok"],
            "consumer": kernel.audit(str(P), produce_from={"parser.py": str(impl)})["ok"],
        })
    with open(HERE / "results_round2.json", "w", encoding="utf-8") as f:
        json.dump({"rows": rows}, f, indent=2, sort_keys=True)
    print(f"\nround 2 — blind rebuilds from the tightened C_1 "
          f"(root {kernel.verify(str(D1))['root'][:12]})\n")
    print(f"  {'reconstruction':34} {'C_1':>5} {'consumer P':>11}")
    for row in rows:
        print(f"  {row['impl']:34} {('yes' if row['c1'] else 'no'):>5} "
              f"{('ok' if row['consumer'] else 'BREAKS'):>11}")
    n, ok = len(rows), sum(r["consumer"] for r in rows)
    print(f"\n  {ok}/{n} reconstructions from C_1 keep the consumer working.")


if __name__ == "__main__":
    if "--round2" in sys.argv:
        round2()
    else:
        if "--judge-only" not in sys.argv:
            rebuild_all()
        report(judge_all())
