"""Judge a generation-1 lineage: identity, confidence, succession.

Three verdicts on a fully regrown implementation, in rising order of
meaning:

  --full-gate   identity: audit the REPOSITORY's claim with every one of
                its 37 generated modules substituted from the lineage tree
                (the kernel's produce_from — the same move stage 2 used to
                judge parser substitutions). REPO_OK re-earned means the
                repository's root admits the regrown implementation.
  --tests       confidence, and the drift instrument: the repository's
                tests/ suite is deliberately OUTSIDE the root — it changes
                confidence, not identity — which makes it a held-out probe
                battery for exactly the surface the criteria never pin. A
                failure here is not a gate failure; it is a measured
                divergence between the regrown tool and the tool we ship.
  --bootstrap   succession: run the REGROWN tool as the tool. It must
                verify the repository, refuse a tampered claim, and drive
                a generation-2 rebuild of the core layer through its own
                kernel — the regrown judge judging, and reproducing.

    python3 judge_gen1.py --lineage claude --full-gate
    python3 judge_gen1.py --lineage claude --tests
    python3 judge_gen1.py --lineage claude --bootstrap
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
from reticuli import kernel  # noqa: E402

VENV_PY = str(REPO / ".venv" / "bin" / "python")


def _tree(name: str) -> Path:
    return HERE / "lineages" / name / "tree"


def _pypath(name: str) -> Path:
    """A directory whose `reticuli` is the lineage tree, for imports."""
    base = HERE / "lineages" / name / "pypath"
    base.mkdir(parents=True, exist_ok=True)
    link = base / "reticuli"
    if not link.exists():
        os.symlink(_tree(name), link)
    return base


def _modules() -> list:
    import tomllib
    with open(REPO / "reticuli.toml", "rb") as f:
        recipe = tomllib.load(f)
    return [s["output"] for s in recipe["step"]
            if s["kind"] == "produce" and "from" not in s]


def full_gate(name: str) -> None:
    tree = _tree(name)
    mapping = {}
    for out in _modules():
        src = tree / Path(out).relative_to("src/reticuli")
        assert src.is_file(), f"lineage tree is missing {src}"
        mapping[out] = str(src)
    print(f"[{name}] auditing the repository claim with all "
          f"{len(mapping)} generated modules substituted from the "
          f"lineage (gate_timeout applies — expect ~25 minutes)...",
          flush=True)
    started = time.time()
    result = kernel.audit(str(REPO), produce_from=mapping)
    minutes = (time.time() - started) / 60
    print(f"[{name}] full gate: ok={result['ok']} "
          f"({minutes:.1f} minutes)", flush=True)
    out = {"lineage": name, "ok": result["ok"], "minutes": round(minutes, 1)}
    with open(HERE / f"full_gate_{name}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True)


def run_tests(name: str) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_pypath(name))
    env["NO_COLOR"] = "1"
    print(f"[{name}] running the held-out tests/ battery against the "
          f"regrown tree...", flush=True)
    proc = subprocess.run(
        [VENV_PY, "-m", "pytest", "tests/", "-q", "--no-header", "-rf",
         "-p", "no:cacheprovider"],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        timeout=3600, check=False)
    tail = proc.stdout[-4000:]
    print(tail, flush=True)
    with open(HERE / f"tests_{name}.txt", "w", encoding="utf-8") as f:
        f.write(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
    print(f"[{name}] tests exit {proc.returncode}; full output in "
          f"tests_{name}.txt", flush=True)


def bootstrap(name: str) -> None:
    pypath = str(_pypath(name))
    env = dict(os.environ)
    env["PYTHONPATH"] = pypath
    env["NO_COLOR"] = "1"
    # the codex gen-1 kernel caps every gate at min(env, declared) with a
    # 60-second default — conforming (the default timeout is declared
    # implementation-defined) but far below the repository gate's needs;
    # its own env knob raises the ceiling. Witnessed 2026-09-29 when its
    # first repo audit died at a minute.
    env["RETICULI_GATE_TIMEOUT"] = "1800"
    report = {"lineage": name}

    def step(label, argv, cwd=str(REPO), expect=0, timeout=2400, e=None):
        proc = subprocess.run(argv, cwd=cwd, env=e or env,
                              capture_output=True, text=True,
                              timeout=timeout, check=False)
        ok = proc.returncode == expect
        report[label] = {"ok": ok, "rc": proc.returncode,
                         "tail": (proc.stdout + proc.stderr)[-300:].strip()}
        print(f"[{name}] {label}: {'ok' if ok else 'FAILED'} "
              f"(rc={proc.returncode}, want {expect})", flush=True)
        return ok

    # a) the regrown tool speaks
    step("version", [VENV_PY, "-P", "-m", "reticuli", "--version"])
    # b) the regrown tool verifies the repository in milliseconds
    step("verify_repo", [VENV_PY, "-P", "-m", "reticuli", "verify", "."])
    # c) the regrown judge refuses tampering: copy a sealed claim, flip a
    #    pinned byte, verify must exit nonzero
    probe = HERE / "scratch" / f"tamper_{name}"
    if probe.exists():
        shutil.rmtree(probe)
    shutil.copytree(REPO / "research/harness/ladder/claims/L", probe,
                    ignore=shutil.ignore_patterns("__pycache__"))
    step("verify_intact_claim",
         [VENV_PY, "-P", "-m", "reticuli", "verify", str(probe)])
    check = probe / "check_c0.py"
    check.write_text(check.read_text() + "\n# tampered\n", encoding="utf-8")
    step("refuse_tampered_claim",
         [VENV_PY, "-P", "-m", "reticuli", "verify", str(probe)], expect=1)
    # d) succession: the regrown kernel drives a generation-2 rebuild of
    #    the core layer, blind, through the SAME producer machinery
    # the producer is bundled tooling OUTSIDE the equivalence class — a
    # gen-1 tree rightly has none, so the producer subprocess runs against
    # the original package while gen-1's kernel does all the judging. The
    # call is positional and the model rides inside the command: spec/
    # kernel-api.md names only produce_from and input_from as rebuild's
    # keywords, and the regrown kernel implemented exactly the spec —
    # `guidance`/`producer_env` are the ORIGINAL's undocumented extras
    # (witnessed 2026-09-29: the first driver used them and gen-1
    # rightly refused).
    producer_cmd = (f"env PYTHONPATH={REPO / 'src'} "
                    f"RETICULI_MODEL={LINEAGE_MODELS[name]} "
                    f"RETICULI_VENDOR={name} {VENV_PY} -P "
                    f"-m reticuli.producers.{name}")
    driver = f"""
import sys
sys.path.insert(0, {pypath!r})
from reticuli import kernel
r = kernel.rebuild({str(HERE / 'scratch' / (name + '_00_core_claim'))!r},
                   {producer_cmd!r},
                   {str(HERE / 'scratch' / (name + '_gen2_core'))!r})
print('gen2 root', r['root'])
"""
    gen2_out = HERE / "scratch" / f"{name}_gen2_core"
    if gen2_out.exists():
        shutil.rmtree(gen2_out)
    e2 = dict(env)
    e2["RETICULI_MODEL"] = LINEAGE_MODELS[name]
    e2["RETICULI_VENDOR"] = name
    step("gen2_core_rebuild", [VENV_PY, "-P", "-c", driver],
         timeout=3900, e=e2)
    # e) the regrown auditor re-earns the repository's verdicts, cold
    step("audit_repo", [VENV_PY, "-P", "-m", "reticuli", "audit", "."],
         timeout=2400)

    with open(HERE / f"bootstrap_{name}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    verdict = all(v["ok"] for k, v in report.items() if isinstance(v, dict))
    print(f"[{name}] bootstrap: "
          f"{'SUCCESSION HOLDS' if verdict else 'gaps found'} "
          f"(bootstrap_{name}.json)", flush=True)


LINEAGE_MODELS = {"claude": "sonnet", "codex": "gpt-6-sol"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lineage", required=True, choices=["claude", "codex"])
    ap.add_argument("--full-gate", action="store_true")
    ap.add_argument("--tests", action="store_true")
    ap.add_argument("--bootstrap", action="store_true")
    args = ap.parse_args()
    if args.full_gate:
        full_gate(args.lineage)
    if args.tests:
        run_tests(args.lineage)
    if args.bootstrap:
        bootstrap(args.lineage)
