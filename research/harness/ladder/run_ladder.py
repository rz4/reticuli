"""The generation ladder: iterated AI rewriting under a fixed gate.

The question: when an agent rewrites a working module generation after
generation, and the only floor is the claim's gate, what happens to the
behavior the gate is silent about? Generation 0 makes eight deliberate,
undocumented choices on the unpinned surface (see probes.py). Each
generation, a producer is handed the previous implementation over the
claim's guidance channel — which the root excludes, so every generation
re-earns the SAME root — and asked to rewrite it in its own style. The
gate must pass; nothing else is enforced. The measurement is which intent
bits survive, per generation, per producer family.

The controls are blind rebuilds (criteria only, no previous implementation)
by the same families: the distribution iterated rewriting would collapse to
if the chain forgets everything but the gate — the model prior, restricted
to the equivalence class.

    python3 run_ladder.py --chain codex --gens 16     # one family's chain
    python3 run_ladder.py --chain claude --gens 16
    python3 run_ladder.py --controls                  # 6 blind rebuilds
    python3 run_ladder.py --fingerprints              # measure everything
    python3 run_ladder.py --report                    # survival table

Paced and resumable: a chain continues from its highest generation on
disk, a quota signal stops cleanly, a failed attempt is retried twice and
then halts the chain with the failure ledgered.
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))
from reticuli import kernel  # noqa: E402
import probes  # noqa: E402

VENV_PY = str(REPO / ".venv" / "bin" / "python")
L = HERE / "claims" / "L"
CHAINS_DIR, CONTROLS, SCRATCH = HERE / "chains", HERE / "controls", HERE / "scratch"

REWRITE_STYLE = "faithful"
REWRITE_MIN = "minimize"

#: chain name -> (vendor for producer_rewrite.py, model, rewrite condition)
CHAINS = {
    "codex": ("codex", "gpt-6-sol", REWRITE_STYLE),
    "claude": ("claude", "sonnet", REWRITE_STYLE),
    "codex-min": ("codex", "gpt-6-sol", REWRITE_MIN),
    "claude-min": ("claude", "sonnet", REWRITE_MIN),
}

#: blind controls — the shipped blind producers, one run per stage-2 model.
CONTROL_PLAN = [
    ("codex", "reticuli.producers.codex", "gpt-6-luna"),
    ("codex", "reticuli.producers.codex", "gpt-6-sol"),
    ("codex", "reticuli.producers.codex", "gpt-6-astra"),
    ("claude", "reticuli.producers.claude", "sonnet"),
    ("claude", "reticuli.producers.claude", "opus"),
    ("claude", "reticuli.producers.claude", "haiku"),
]

QUOTA = re.compile(r"usage limit|rate limit|try again|quota|429", re.IGNORECASE)

REWRITE_REQUEST = """Below is the current parser.py from this project; it \
passes the project's check. Rewrite parser.py from scratch in your own style \
— clear, idiomatic Python, standard library only. Do not copy it line by \
line; write it the way you would write it. Write your rewrite as parser.py \
in the current directory.

--- current parser.py ---
@SOURCE@
--- end of current parser.py ---"""

MIN_REQUEST = """Below is the current parser.py from this project; it \
passes the project's check. Rewrite parser.py to be as short and simple as \
you can while the project's check still passes. Write your rewrite as \
parser.py in the current directory.

--- current parser.py ---
@SOURCE@
--- end of current parser.py ---"""


def _request(condition: str, source: str) -> str:
    template = MIN_REQUEST if condition == REWRITE_MIN else REWRITE_REQUEST
    # not str.format: the source itself is full of braces
    return template.replace("@SOURCE@", source)


def _root() -> str:
    return kernel.verify(str(L))["root"]


def _ledger(chain_dir: Path, entry: dict) -> None:
    entry["when"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(chain_dir / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _set_guidance(subject: Path, request: str) -> None:
    """Write the rewrite context onto the claim's guidance channel. Format 3
    excludes guidance from the root, so this never moves the name — asserted
    below, every single time."""
    recipe = subject / "reticuli.toml"
    text = recipe.read_text(encoding="utf-8")
    line = "guidance = " + json.dumps(request)
    new = re.sub(r"(?m)^guidance = .*$", lambda _m: line, text, count=1)
    assert new != text or line in text, "no guidance line found to replace"
    recipe.write_text(new, encoding="utf-8")
    assert kernel.verify(str(subject))["root"] == _root(), \
        "guidance moved the root — format-3 promise broken, stop everything"


def _ensure_chain(name: str) -> Path:
    chain_dir = CHAINS_DIR / name
    gens = chain_dir / "gens"
    gens.mkdir(parents=True, exist_ok=True)
    subject = chain_dir / "subject"
    if not subject.exists():
        shutil.copytree(L, subject, ignore=shutil.ignore_patterns("__pycache__"))
    gen0 = gens / "gen000.py"
    if not gen0.exists():
        shutil.copy(L / "parser.py", gen0)
    return chain_dir


def _highest_gen(gens: Path) -> int:
    found = sorted(gens.glob("gen*.py"))
    return int(found[-1].stem.removeprefix("gen")) if found else -1


def run_chain(name: str, target: int) -> None:
    import os
    vendor, model, condition = CHAINS[name]
    os.environ["RETICULI_MODEL"] = model     # for the kernel's producer ledger
    os.environ["RETICULI_VENDOR"] = vendor
    chain_dir = _ensure_chain(name)
    gens, subject = chain_dir / "gens", chain_dir / "subject"
    SCRATCH.mkdir(exist_ok=True)
    producer = f"{VENV_PY} -P {HERE / 'producer_rewrite.py'}"

    while (n := _highest_gen(gens)) < target:
        source = (gens / f"gen{n:03d}.py").read_text(encoding="utf-8")
        _set_guidance(subject, _request(condition, source))
        out = SCRATCH / f"{name}_gen{n + 1:03d}"
        converged = False
        for attempt in (1, 2, 3):
            if out.exists():
                shutil.rmtree(out)  # a failed attempt left bytes; the kernel refuses them
            print(f"[{name} gen {n + 1:03d}] rewriting (attempt {attempt})...",
                  flush=True)
            try:
                r = kernel.rebuild(str(subject), producer, str(out),
                                   producer_env={"RETICULI_MODEL": model,
                                                 "RETICULI_VENDOR": vendor})
            except kernel.ClaimError as exc:
                text = str(exc)
                if QUOTA.search(text):
                    print(f"[{name}] QUOTA — stopping; re-run to resume.",
                          flush=True)
                    _ledger(chain_dir, {"gen": n + 1, "event": "quota"})
                    return
                _ledger(chain_dir, {"gen": n + 1, "event": "attempt-failed",
                                    "attempt": attempt, "error": text[-300:]})
                continue
            converged = True
            break
        if not converged:
            print(f"[{name} gen {n + 1:03d}] did not converge; chain halted.",
                  flush=True)
            _ledger(chain_dir, {"gen": n + 1, "event": "halted"})
            return
        assert r["root"] == _root(), \
            "a rewrite that lands is the claim: one root"  # kernel enforced this
        shutil.copy(out / "parser.py", gens / f"gen{n + 1:03d}.py")
        _ledger(chain_dir, {"gen": n + 1, "event": "converged",
                            "vendor": vendor, "model": model,
                            "condition": condition, "attempt": attempt})
        print(f"[{name} gen {n + 1:03d}] converged, root held.", flush=True)


def run_controls() -> None:
    """Blind rebuilds: the prior, sampled with no previous implementation."""
    CONTROLS.mkdir(exist_ok=True)
    SCRATCH.mkdir(exist_ok=True)
    import os
    for idx, (family, module, model) in enumerate(CONTROL_PLAN):
        tag = f"{idx:02d}_{family}_{model.replace('-', '_')}"
        dest = CONTROLS / f"impl_{tag}.py"
        if dest.exists():
            print(f"[control {tag}] already ingested", flush=True)
            continue
        out = SCRATCH / f"control_{tag}"
        if out.exists():
            shutil.rmtree(out)
        print(f"[control {tag}] rebuilding blind...", flush=True)
        os.environ["RETICULI_MODEL"] = model
        os.environ["RETICULI_VENDOR"] = family
        producer = f"{VENV_PY} -P -m {module}"
        try:
            r = kernel.rebuild(str(L), producer, str(out), guidance=False,
                               producer_env={"RETICULI_MODEL": model})
        except kernel.ClaimError as exc:
            text = str(exc)
            if QUOTA.search(text):
                print(f"[control {tag}] QUOTA — stopping; re-run to resume.",
                      flush=True)
                break
            print(f"[control {tag}] did not converge: {text[-300:]}", flush=True)
            continue
        assert r["root"] == _root()
        shutil.copy(out / "parser.py", dest)
        print(f"[control {tag}] converged -> {dest.name}", flush=True)


def measure() -> dict:
    """Fingerprint every generation and control; write fingerprints.json."""
    result = {"root": _root(), "chains": {}, "controls": {}}
    for name in sorted(CHAINS):
        gens = CHAINS_DIR / name / "gens"
        if not gens.is_dir():
            continue
        rows = {}
        for path in sorted(gens.glob("gen*.py")):
            fp = probes.fingerprint(str(path))
            rows[path.stem] = {"outcomes": fp, "survived": probes.survived(fp)}
        result["chains"][name] = rows
    if CONTROLS.is_dir():
        for path in sorted(CONTROLS.glob("impl_*.py")):
            fp = probes.fingerprint(str(path))
            result["controls"][path.stem] = {"outcomes": fp,
                                             "survived": probes.survived(fp)}
    with open(HERE / "fingerprints.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    return result


def report(result: dict | None = None) -> None:
    if result is None:
        with open(HERE / "fingerprints.json", encoding="utf-8") as f:
            result = json.load(f)
    bits = probes.BITS
    print(f"\ngeneration ladder — subject root {result['root'][:12]}, "
          f"{len(bits)} unpinned intent bits\n")
    for name, rows in sorted(result["chains"].items()):
        print(f"  chain {name} ({CHAINS[name][1]}, {CHAINS[name][2]}):")
        print(f"    {'gen':>6}  " + "  ".join(f"{b[:6]:>6}" for b in bits)
              + "  alive")
        for gen, row in sorted(rows.items()):
            marks = "  ".join(
                f"{'✓' if row['survived'][b] else '·':>6}" for b in bits)
            alive = sum(row["survived"][b] for b in bits)
            print(f"    {gen:>6}  {marks}  {alive}/{len(bits)}")
        print()
    if result["controls"]:
        print("  blind controls (the prior, no previous implementation):")
        for tag, row in sorted(result["controls"].items()):
            marks = "  ".join(
                f"{'✓' if row['survived'][b] else '·':>6}" for b in bits)
            alive = sum(row["survived"][b] for b in bits)
            print(f"    {tag:>28}  {marks}  {alive}/{len(bits)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", choices=sorted(CHAINS))
    ap.add_argument("--gens", type=int, default=16)
    ap.add_argument("--controls", action="store_true")
    ap.add_argument("--fingerprints", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.chain:
        run_chain(args.chain, args.gens)
    if args.controls:
        run_controls()
    if args.fingerprints:
        report(measure())
    elif args.report:
        report()
