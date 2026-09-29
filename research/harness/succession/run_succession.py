"""The succession run: reticuli's implementation, regrown on regrown ancestry.

The repository's root deliberately excludes `src/` — the implementation is
the equivalence class, not the identity. This harness takes that promise to
its end: grow a complete generation-1 implementation in rooms that never
see the original, layer by layer, where each layer's PINNED context is the
generation-1 bytes of the layers beneath it — never the original's. The
finished tree shares no ancestry with the shipped implementation; every
module was written by a producer whose only view of the code below was
itself producer-written.

Scaffolding, honestly labeled: each layer gets a throwaway "flat" claim
(the same construction as research/harness/build_flat_layers.py, on the
current nineteen-layer chain from scripts/selfclaim.py), sealed entirely
from the original source so the warm seal always earns. The succession
twist is `input_from`: at rebuild time the generation-1 lower modules are
threaded into the room in place of the originals — the kernel ledgers the
threading and keeps it inside the tamper snapshot — so the producer works
blind from the check and the regrown context alone, and the layer's gate
judges the regrown layer on regrown ancestry. Threaded inputs move the
destination root by design (a different input is a different claim);
these per-lineage roots are construction jigs, not the repository's
identity. The identity test comes afterward, when the assembled tree must
re-earn REPO_OK under the repository's own gate.

Found before this design settled (first attempt sealed mixed rooms —
original layer on gen-1 lowers — and both lineages refused within two
layers): the sub-layer seams run on UNPINNED PRIVATE names. The original
identity.py calls recipe's private `_inputs(recipe, claimdir)`; a
conforming regrown recipe implemented `_inputs(recipe)` and the original
above it crashed. The layer criteria pin each layer's outward behavior,
never the private interface the next layer's original code consumes — so
original modules are NOT substitutable onto regrown ancestry, while
regrown modules (written against the ancestry actually in the room) can
be. The ladder's lesson, one level down: what the checks are silent
about, only the visible context carries.

    python3 run_succession.py --lineage claude          # 19 layers, resumable
    python3 run_succession.py --lineage codex
    python3 run_succession.py --status

Resumable: a completed layer's modules live in the lineage tree; the runner
skips them. A quota signal stops cleanly; a failed attempt is retried, each
attempt ledgered.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
from reticuli import kernel, pack  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "selfclaim", REPO / "scripts" / "selfclaim.py")
_selfclaim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_selfclaim)
#: the nineteen layers of scripts/selfclaim.py, plus one the decomposition
#: omits: reference.py, the second independent identity implementation,
#: judged by vectors_check (kernel and reference must agree on every
#: conformance vector). vectors_check expects the repository layout, so
#: this layer's rooms use a src/reticuli prefix and a wrapper gate.
REFERENCE = ("reference", ["reference.py"], "criteria/vectors_check.py",
             "VECTORS_OK")
LAYERS = _selfclaim.LAYERS + [REFERENCE]

VENV_PY = str(REPO / ".venv" / "bin" / "python")

#: lineage -> (vendor, producer module, model)
LINEAGES = {
    "claude": ("claude", "reticuli.producers.claude", "sonnet"),
    "codex": ("codex", "reticuli.producers.codex", "gpt-6-sol"),
}

QUOTA = re.compile(r"usage limit|rate limit|try again|quota|429", re.IGNORECASE)
RETRIES = 3


def _lineage_dirs(name: str) -> tuple:
    base = HERE / "lineages" / name
    return base / "tree", base


def _ledger(base: Path, entry: dict) -> None:
    entry["when"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    base.mkdir(parents=True, exist_ok=True)
    with open(base / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _lowers(idx: int) -> list:
    mods: list = []
    for _name, adds, _check, _verdict in LAYERS[:idx]:
        mods += adds
    return mods


def _done(tree: Path, idx: int) -> bool:
    return all((tree / m).is_file() for m in LAYERS[idx][1])


def _flat_claim(name: str, idx: int, room: Path) -> str:
    """Build and seal the scaffold claim for one layer, entirely from the
    ORIGINAL source — lower modules as pinned inputs, the layer's own
    modules as generated — so the warm seal always earns. The succession
    twist happens at rebuild time: `input_from` threads the GENERATION-1
    lower modules into the room in place of the originals (ledgered by the
    kernel as threaded inputs, inside the tamper snapshot), and the layer's
    gate then judges the regrown layer on regrown ancestry. The destination
    seals to its own root — a different input is a different claim — and
    those per-lineage roots are construction jigs, not the repository's
    identity. Returns the gate's verdict filename."""
    layer, adds, check, verdict = LAYERS[idx]
    prefix = "src/reticuli" if layer == "reference" else "reticuli"
    gate = f"python3 checks/{Path(check).name}"
    if layer == "reference":
        gate = f"{gate} && printf ok > {verdict}"
    if room.exists():
        shutil.rmtree(room)
    (room / "checks").mkdir(parents=True)
    for module in _lowers(idx) + adds:
        dst = room / prefix / module
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / "src" / "reticuli" / module, dst)
    shutil.copyfile(REPO / check, room / "checks" / Path(check).name)
    # The specification travels with every room, exactly as the repository
    # claim pins it for a stranger's room: the checks judge, the spec
    # explains what they judge. Witnessed 2026-09-29: a producer stalled on
    # the identity layer asking for spec/identity.md — the flat rooms had
    # been under-furnished relative to the standing invitation.
    spec_files = []
    for path in sorted((REPO / "spec").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            rel = path.relative_to(REPO)
            dst = room / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dst)
            spec_files.append(str(rel))

    inputs = ["checks/*.py"] + spec_files \
        + [f"{prefix}/{m}" for m in _lowers(idx)]
    generated = [f"{prefix}/{m}" for m in adds]
    pack.pack(str(room), f"{name}-{layer}", generated=generated,
              inputs=inputs, gate=gate,
              gate_output=verdict, claim_format=3)
    return verdict


def run_lineage(name: str, stop_after: int | None = None) -> None:
    vendor, module, model = LINEAGES[name]
    os.environ["RETICULI_MODEL"] = model
    os.environ["RETICULI_VENDOR"] = vendor
    tree, base = _lineage_dirs(name)
    tree.mkdir(parents=True, exist_ok=True)
    scratch = HERE / "scratch"
    scratch.mkdir(exist_ok=True)
    producer = f"{VENV_PY} -P -m {module}"

    for idx, (layer, adds, _check, _verdict) in enumerate(LAYERS):
        if stop_after is not None and idx >= stop_after:
            return
        if _done(tree, idx):
            print(f"[{name} {idx:02d} {layer}] already grown", flush=True)
            continue
        room = scratch / f"{name}_{idx:02d}_{layer}_claim"
        print(f"[{name} {idx:02d} {layer}] sealing scaffold (all-original, "
              f"warm)...", flush=True)
        _flat_claim(name, idx, room)
        prefix = "src/reticuli" if layer == "reference" else "reticuli"
        threaded = {f"{prefix}/{m}": str(tree / m) for m in _lowers(idx)}
        out = scratch / f"{name}_{idx:02d}_{layer}_rebuild"
        grown = False
        for attempt in range(1, RETRIES + 1):
            if out.exists():
                shutil.rmtree(out)
            print(f"[{name} {idx:02d} {layer}] regrowing blind "
                  f"(attempt {attempt})...", flush=True)
            penv = {"RETICULI_MODEL": model}
            if vendor == "claude":
                # witnessed 2026-09-29: the crosscheck layer's session hit
                # the claude CLI's 64k output-token ceiling mid-module
                penv["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "128000"
            try:
                r = kernel.rebuild(str(room), producer, str(out),
                                   input_from=threaded, guidance=False,
                                   producer_env=penv)
            except kernel.ClaimError as exc:
                text = str(exc)
                if QUOTA.search(text):
                    print(f"[{name}] QUOTA — stopping; re-run to resume.",
                          flush=True)
                    _ledger(base, {"layer": layer, "event": "quota"})
                    return
                _ledger(base, {"layer": layer, "event": "attempt-failed",
                               "attempt": attempt, "error": text[-300:]})
                continue
            grown = True
            break
        if not grown:
            print(f"[{name} {idx:02d} {layer}] did not converge; "
                  f"lineage halted here.", flush=True)
            _ledger(base, {"layer": layer, "event": "halted"})
            return
        assert kernel.verify(str(out))["root"] == r["root"], \
            "the regrown layer claim must verify as sealed"
        # NOT asserted equal to the scaffold root: threaded gen-1 inputs make
        # this a different claim by design ("a different input is a
        # different claim") — the identity test is the repository gate later.
        for m in adds:
            dst = tree / m
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / prefix / m, dst)
        _ledger(base, {"layer": layer, "event": "grown", "vendor": vendor,
                       "model": model, "attempt": attempt,
                       "scaffold_root": r["root"]})
        print(f"[{name} {idx:02d} {layer}] grown into the lineage tree.",
              flush=True)
    print(f"[{name}] all {len(LAYERS)} layers grown.", flush=True)


def status() -> None:
    for name in sorted(LINEAGES):
        tree, _base = _lineage_dirs(name)
        done = sum(_done(tree, i) for i in range(len(LAYERS))) \
            if tree.exists() else 0
        print(f"{name}: {done}/{len(LAYERS)} layers grown")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lineage", choices=sorted(LINEAGES))
    ap.add_argument("--stop-after", type=int, default=None,
                    help="grow only the first N layers (pilot runs)")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.status:
        status()
    elif args.lineage:
        run_lineage(args.lineage, args.stop_after)
    else:
        ap.print_help()
