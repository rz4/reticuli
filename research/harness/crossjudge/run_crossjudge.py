"""Cross-judging: the rebuilt tools judge, and rebuild, each other.

*Research tooling — not normative, not pinned.*

The succession runs showed descendants SATISFY the parent's criteria
(REPO_OK re-earned on regrown trees). This harness tests the stronger
property: can a descendant DO the parent's job — judge claims, including
refusing broken ones with the right verdict, and orchestrate the
production of another conforming descendant?

Three tools:
    original  src/reticuli (the shipped implementation)
    claude    lineages-r3/claude/tree (regrown, Anthropic family)
    codex     lineages-r3/codex/tree  (regrown, OpenAI family)

Phase A — the judging matrix. One claim battery, built once from shared
bytes, judged by all three tools through their own CLI (`-m reticuli`):

    good       portable toy claim, sealed warm            verify ok, audit ok
    variant    different implementation, same criteria    same root, both ok
    tamper-in  pinned input flipped after seal            verify refuses: broken
    tamper-gen generated output broken after seal         verify ok (root never
                                                          covered it), audit
                                                          re-earns: failed
    forged     gate verdict file present, gate would fail audit re-earns: failed
    recipe-edit recipe edited after seal                  verify refuses: broken

The two verdict words are the pinned vocabulary (surface_check): `broken`
is identity damage, `failed` is a failed gate. A judge that confuses them
has not learned the distinction the criteria pin. Every claim's gate uses
`python3` from PATH — the strict audit sandbox masks the home ground, so
a gate naming an absolute venv path is unjudgeable by design (found
2026-10-05 via tests/test_streams.py).

Phase A2 — three builders. Each tool packs the same toy content; the
roots must be identical (the root is criteria+recipe, so three correct
kernels must mint one name), and each builder's claim must verify under
the other two judges.

Phase B — orchestration. Each tool drives its own `rebuild` of the good
claim in a blind room with a deterministic producer (a python script
that writes a conforming implementation from the room's check alone).
The descendant must seal, and must then pass audit under BOTH other
tools. The rebuild ledger's `quarantine` field is recorded per tool —
the sandbox-signal question: do three implementations agree on what
jail they are in (and inherit an existing one rather than nest)?

    python3 run_crossjudge.py            # phase A + A2 + B, JSON report
    python3 run_crossjudge.py --skip-b   # judging matrix only

Output: crossjudge_report.json beside this file, and a findings list on
stdout. Every disagreement between tools is a finding — either a
soundness gap in a regrown tree (the criteria admitted a wrong judge) or
an unpinned seam (the contract never said). Both feed the ratchet.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SUCCESSION = REPO / "research" / "harness" / "succession"

TOOLS = {
    "original": REPO / "src",
    "claude": SUCCESSION / "lineages-r3" / "claude" / "pypath",
    "codex": SUCCESSION / "lineages-r3" / "codex" / "pypath",
    # the first tree grown under the authoring-and-sandbox bundle
    # (root 79bce6fb, 2026-10-05) — scores P1/P10/P11 of predictions_r4.md:
    # its verdict words, its authoring default, and its named jails are the
    # behaviors the bundle's pins must have steered.
    "codex-r4": SUCCESSION / "lineages-r4" / "codex" / "pypath",
    # closure trial 1 (root e2b77b87, frozen): the first tree grown under
    # the sandbox-closure bundle — scores predictions_r5.md P1/P5.
    "codex-r5": SUCCESSION / "lineages-r5" / "codex" / "pypath",
    # closure trial 1, second attempt (root 5eabb96e, frozen)
    "codex-r6": SUCCESSION / "lineages-r6" / "codex" / "pypath",
    # closure trial 1, third attempt (root c6eac133, frozen)
    "codex-r7": SUCCESSION / "lineages-r7" / "codex" / "pypath",
    # closure trial 1, fourth attempt (root 47ee199b, frozen)
    "codex-r8": SUCCESSION / "lineages-r8" / "codex" / "pypath",
    # closure trial 1, fifth attempt (root d37cd91d, frozen)
    "codex-r9": SUCCESSION / "lineages-r9" / "codex" / "pypath",
}

CHECK = """import os
with open("impl.py") as f:
    ns = {}
    exec(f.read(), ns)
assert ns["double"](4) == 8, "double must double"
assert ns["double"](0) == 0
with open("OK", "w") as f:
    f.write("ok\\n")
print("toy gate: pass")
"""

IMPL = "def double(x):\n    return x * 2\n"
IMPL_VARIANT = "def double(x):\n    return x + x\n"
IMPL_BROKEN = "def double(x):\n    return x * 3\n"

#: a producer that regrows impl.py from nothing but the room — it reads the
#: check to learn the name, then writes the obvious implementation. Dumb on
#: purpose: phase B tests the ORCHESTRATOR (rooms, gates, seals, sandbox),
#: not the producer's intelligence.
PRODUCER = ("import pathlib; "
            "pathlib.Path('impl.py').write_text('def double(x):\\n"
            "    return x * 2\\n')")


def run_tool(tool: str, *argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(TOOLS[tool]))
    return subprocess.run([sys.executable, "-m", "reticuli", *argv],
                          check=False, cwd=cwd or REPO, env=env,
                          capture_output=True, text=True, timeout=600)


def build_battery(work: Path) -> dict:
    """The six claims, built once (original tool) from shared bytes."""
    claims = {}

    def seal(name: str, impl: str) -> Path:
        d = work / name
        d.mkdir(parents=True)
        (d / "check.py").write_text(CHECK)
        (d / "impl.py").write_text(impl)
        r = run_tool("original", "pack", name, "-C", str(d),
                     "--generated", "impl.py", "--input", "check.py",
                     "--gate", "python3 check.py", "--output", "OK", "--json")
        assert r.returncode == 0, f"{name} must seal: {r.stderr}"
        claims[name] = {"dir": str(d), "root": json.loads(r.stdout)["root"]}
        return d

    seal("good", IMPL)
    seal("variant", IMPL_VARIANT)

    d = seal("tamper-in", IMPL)
    (d / "check.py").write_text(CHECK + "# flipped after seal\n")

    d = seal("tamper-gen", IMPL)
    (d / "impl.py").write_text(IMPL_BROKEN)

    d = seal("forged", IMPL)
    # the verdict file still says ok (left by the warm seal), but the
    # implementation no longer satisfies the gate: a judge that trusts the
    # verdict instead of re-earning it accepts a lie
    (d / "impl.py").write_text(IMPL_BROKEN)
    (d / "OK").write_text("ok\n")

    d = seal("recipe-edit", IMPL)
    recipes = [p for p in d.iterdir() if p.suffix == ".toml"]
    assert recipes, "a sealed claim carries a recipe"
    recipes[0].write_text(
        recipes[0].read_text().replace('"python3 check.py"',
                                       '"python3 -B check.py"'))
    return claims


EXPECT = {
    # claim -> (verify ok, audit ok, audit verdict word if not ok)
    "good": (True, True, None),
    "variant": (True, True, None),
    "tamper-in": (False, False, "broken"),
    "tamper-gen": (True, False, "failed"),   # root never covered impl.py
    "forged": (True, False, "failed"),
    "recipe-edit": (False, False, "broken"),
}


def phase_a(claims: dict) -> tuple[list, list]:
    rows, findings = [], []
    for name, meta in claims.items():
        want_verify, want_audit, want_word = EXPECT[name]
        for tool in TOOLS:
            row = {"phase": "A", "claim": name, "tool": tool}
            v = run_tool(tool, "verify", meta["dir"], "--json")
            row["verify_rc"] = v.returncode
            row["verify_ok"] = v.returncode == 0
            a = run_tool(tool, "audit", meta["dir"], "--json")
            row["audit_rc"] = a.returncode
            row["audit_ok"] = a.returncode == 0
            word = None
            try:
                payload = json.loads(a.stdout)
                word = payload.get("status") or payload.get("verdict")
                row["audit_keys"] = sorted(payload)[:8]
            except ValueError:
                row["audit_json"] = "unparseable"
            row["audit_word"] = word
            if row["verify_ok"] != want_verify:
                findings.append(f"{tool} verify({name}): "
                                f"got ok={row['verify_ok']}, want {want_verify}")
            if row["audit_ok"] != want_audit:
                findings.append(f"{tool} audit({name}): "
                                f"got ok={row['audit_ok']}, want {want_audit}")
            if want_word and word != want_word and not row["audit_ok"]:
                # the r3 trees predate the verdict-vocabulary pin (final
                # bundle); a word mismatch from them is era-faithful drift,
                # expected to close in r4 (predictions_r4.md, P1) — and the
                # --json report SCHEMA itself is an unpinned seam this
                # measures (three tools, three shapes).
                findings.append(f"{tool} audit({name}): verdict word "
                                f"{word!r}, pinned vocabulary says {want_word!r}"
                                f" (keys: {row.get('audit_keys')})")
            rows.append(row)
    return rows, findings


def run_api(tool: str, code: str) -> subprocess.CompletedProcess:
    """Drive a tool through its library surface — the one the layer criteria
    exercise — rather than CLI flag spellings, which are unpinned (measured
    here 2026-10-05: `-C` and `--into` exist only in the original; codex
    spells the rebuild target `-o`). The last line of stdout must be JSON."""
    env = dict(os.environ, PYTHONPATH=str(TOOLS[tool]))
    return subprocess.run([sys.executable, "-c", code], check=False, cwd=REPO,
                          env=env, capture_output=True, text=True, timeout=600)


def phase_a2(work: Path) -> tuple[list, list]:
    """Three builders, one name: each tool packs the same content."""
    rows, findings, roots = [], [], {}
    for tool in TOOLS:
        d = work / f"built-by-{tool}"
        d.mkdir()
        (d / "check.py").write_text(CHECK)
        (d / "impl.py").write_text(IMPL)
        r = run_api(tool, f"""
import json
from reticuli import pack
out = pack.pack({str(d)!r}, "crosstoy", generated=["impl.py"],
                inputs=["check.py"], gate="python3 check.py",
                gate_output="OK")
print(json.dumps({{"root": out["root"]}}))
""")
        row = {"phase": "A2", "builder": tool, "pack_rc": r.returncode}
        if r.returncode == 0:
            row["root"] = json.loads(r.stdout.strip().splitlines()[-1])["root"]
            roots[tool] = row["root"]
            for judge in TOOLS:
                if judge == tool:
                    continue
                v = run_tool(judge, "verify", str(d), "--json")
                row[f"verified_by_{judge}"] = v.returncode == 0
                if v.returncode != 0:
                    findings.append(f"{judge} refuses the claim {tool} built: "
                                    f"{v.stderr.strip()[:200]}")
        else:
            findings.append(f"{tool} cannot pack: {r.stderr.strip()[:200]}")
        rows.append(row)
    if len(set(roots.values())) > 1:
        findings.append(f"the three kernels mint different roots for one "
                        f"claim: { {k: v[:12] for k, v in roots.items()} }")
    return rows, findings


def phase_b(claims: dict, work: Path) -> tuple[list, list]:
    """Each tool orchestrates a blind rebuild; the others audit the child."""
    rows, findings = [], []
    src = claims["good"]["dir"]
    producer = f"{sys.executable} -c \"{PRODUCER}\""
    for tool in TOOLS:
        child = work / f"child-of-{tool}"
        r = run_api(tool, f"""
import json
from reticuli import kernel
out = kernel.rebuild({src!r}, {producer!r}, {str(child)!r})
print(json.dumps({{"root": out["root"],
                   "quarantine": out.get("quarantine")}}))
""")
        row = {"phase": "B", "orchestrator": tool, "rebuild_rc": r.returncode}
        if r.returncode != 0:
            findings.append(f"{tool} cannot orchestrate a rebuild: "
                            f"{(r.stderr or r.stdout).strip()[:300]}")
            rows.append(row)
            continue
        data = json.loads(r.stdout.strip().splitlines()[-1])
        row["child_root"] = data.get("root")
        row["quarantine"] = data.get("quarantine")
        if row["child_root"] != claims["good"]["root"]:
            findings.append(f"{tool}'s child sealed to a different root: "
                            f"{row['child_root']} != {claims['good']['root']}")
        for judge in TOOLS:
            if judge == tool:
                continue
            a = run_tool(judge, "audit", str(child), "--json")
            row[f"audited_by_{judge}"] = a.returncode == 0
            if a.returncode != 0:
                findings.append(f"{judge} refuses the child {tool} built: "
                                f"{(a.stderr or a.stdout).strip()[:200]}")
        rows.append(row)
    quarantines = {r["orchestrator"]: r.get("quarantine")
                   for r in rows if r.get("rebuild_rc") == 0}
    if len(set(quarantines.values())) > 1:
        findings.append(f"sandbox signal disagrees across orchestrators: "
                        f"{quarantines}")
    return rows, findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="cross-judging matrix")
    ap.add_argument("--skip-b", action="store_true")
    ap.add_argument("--work", default=str(HERE / "scratch"))
    a = ap.parse_args(argv)

    work = Path(a.work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    claims = build_battery(work / "battery")
    rows, findings = phase_a(claims)
    r2, f2 = phase_a2(work)
    rows += r2
    findings += f2
    if not a.skip_b:
        r3, f3 = phase_b(claims, work)
        rows += r3
        findings += f3

    report = {"tools": {k: str(v) for k, v in TOOLS.items()},
              "claims": claims, "rows": rows, "findings": findings}
    out = HERE / "crossjudge_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n{len(rows)} judgments, {len(findings)} findings "
          f"-> {out.relative_to(REPO)}")
    for f in findings:
        print(f"  ! {f}")
    if not findings:
        print("  all three tools agree on every judgment, every root, "
              "and every refusal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
