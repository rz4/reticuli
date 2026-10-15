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

#: The DOE Model Access Gateway (MAG) serves ~87 models behind one
#: OpenAI-compatible endpoint, which the agentic producer already speaks.
#: Every row here is a producer FAMILY: one more candidate lineage for the
#: closure count, at a metered price the usage ledger records in dollars.
#: name -> (model string, "input,output[,cache_read]" usd per million tokens,
#: quoted from the MAG dashboard's price table on 2026-10-15). The three
#: rates are kept apart because they differ by up to a factor of twenty and
#: this producer is input-heavy: it re-reads the whole check every turn, so
#: a run priced at one blended rate is not a measurement of what it cost.
#: Model strings carry MAG modifiers: :high = reasoning effort, @provider
#: pins the serving provider so a rerun is the same claim about the world.
MAG_URL = "https://mag.genesis.americansciencecloud.org/v1"
MAG = {
    # free (cborg-served): shake out the plumbing at zero dollars
    "gemma": ("gemma-4-thinking@cborg", "0,0,0"),
    "inkling": ("inkling-small@cborg", "0,0,0"),
    # cheap tier: is a small model enough to re-derive the spec?
    "luna": ("gpt-6-luna:high@microsoft", "0.10,0.50,0.01"),
    "nemotron": ("nemotron-super-3@amazon", "0.15,0.65"),
    "oss": ("gpt-oss-120b@amazon", "0.15,0.60"),
    "mistral": ("mistral-large-3@amazon", "0.50,1.50"),
    "haiku": ("claude-haiku-5-5:high@google", "0.10,0.50,0.01"),
    # frontier tier: the serious new families
    "gemini": ("gemini-3.8-flash:high@google", "0.75,3.75,0.07"),
    "argon": ("gemini-4-argon:high@google", "2.00,10.00,0.10"),
    "grok": ("grok-4.7:high@microsoft", "2.00,6.00,0.50"),
    # claude without the subscription clock, for the r26 retry
    "sonnet-mag": ("claude-sonnet-5-5:high@google", "2.00,10.00,0.10"),
    # the r31 slate. A specialist, a fifth family and its cheap sibling:
    "devstral": ("devstral-2@amazon", "0.40,2.00"),
    "grok-fast": ("grok-4-1-fast-reasoning@microsoft", "0.20,0.50"),
    # grok-4.7 serves NO effort modifier: `:high` is refused 400. Corrected
    # 2026-10-15 after the first probe measured the gateway instead.
    "grok": ("grok-4.7@microsoft", "2.00,6.00,0.50"),
    # the effort ladder: luna failed identity at :high — does deliberation
    # budget substitute for scale? (amazon: the one provider serving :max)
    "luna-max": ("gpt-6-luna:max@amazon", "0.11,0.55,0.01"),
    # the generation ladder inside one family, tier held at pro. Neither
    # old generation serves an effort modifier, so they run at default —
    # a confound the predictions file carries rather than hides.
    "gemini25": ("gemini-2.5-pro@google", "1.25,10.00,0.12"),
    "gemini31": ("gemini-3.1-pro-preview@google", "2.00,12.00,0.20"),
}
for _n, (_m, _p) in MAG.items():
    LINEAGES[_n] = ("mag", "reticuli.producers.openai", _m)

QUOTA = re.compile(r"usage limit|rate limit|try again|quota|429", re.IGNORECASE)

#: A CONFIGURATION refusal: the gateway rejected the request itself, so the
#: producer never saw the task. Retrying cannot help, and recording a halt
#: would file a configuration error as a capability measurement -- the one
#: confusion that silently corrupts a floor table. Witnessed 2026-10-15:
#: grok-4.7 serves no effort modifier, `:high` was refused 400 three times,
#: and the ledger wrote "halted" beside genuine identity failures.
CONFIG = re.compile(r"amsc_invalid_model_modifier|model_modifier_invalid|"
                    r"model_not_found|invalid_model|unsupported_modifier",
                    re.IGNORECASE)

#: An INFRASTRUCTURE failure: the serving path broke. Transient, so it is
#: worth retrying -- but a lineage whose every attempt died this way measured
#: the gateway, not the producer, and must not be reported as a floor result.
#: Witnessed the same day: gemini-4-argon's recipe attempts died on repeated
#: InternalServerError and a killed producer, and grok-4-1-fast took a 403
#: from an Azure gateway. Both were nearly read as capability.
INFRA = re.compile(r"InternalServerError|BadGateway|ServiceUnavailable|"
                   r"50[0234]|403 Forbidden|Forbidden|rc=-9|"
                   r"Connection error|Can't reach the API", re.IGNORECASE)
RETRIES = 3


def _classify(text):
    """What KIND of failure this was. Capability is the residual, never the
    assumption: a floor table is only as honest as its refusal to count a
    broken request as an answer."""
    if CONFIG.search(text):
        return "config"
    if QUOTA.search(text):
        return "quota"
    if INFRA.search(text):
        return "infra"
    return "capability"


#: which run's trees to write/read — set SUCCESSION_RUN to keep a rerun's
#: trees beside the committed baseline (e.g. "r2" after clicks A/J).
RUN = os.environ.get("SUCCESSION_RUN", "")
RUN_DIR = "lineages" + ("-" + RUN if RUN else "")
TAG = ("_" + RUN) if RUN else ""       # infix so a rerun's scratch is its own


def _lineage_dirs(name: str) -> tuple:
    base = HERE / RUN_DIR / name
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


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock(base: Path):
    """One runner per lineage, enforced.

    Two runners on one lineage share both the tree and the scratch room
    names, and each wipes the other's room mid-flight -- `_flat_claim`
    rmtrees the scaffold and every attempt rmtrees the rebuild directory --
    so attempts die for reasons belonging to neither producer, and the
    failures are indistinguishable from capability in the ledger.

    Witnessed 2026-10-15: a process check returned a false negative, three
    lineages were relaunched over live runners, and the duplicate runners
    were only found by reading `ps` for elapsed times. Asking the operating
    system politely is not a check; holding a lock is.
    """
    base.mkdir(parents=True, exist_ok=True)
    lock = base / "RUNNER.lock"
    if lock.is_file():
        try:
            pid = int(lock.read_text().split()[0])
        except (ValueError, IndexError):
            pid = None
        if pid and _alive(pid):
            raise SystemExit(
                f"lineage {base.name} is already being run by pid {pid}; "
                f"refusing to race it. Stop that runner, or remove "
                f"{lock} if you are certain it is dead.")
        print(f"[{base.name}] clearing a stale lock from pid {pid}", flush=True)
    lock.write_text(f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    return lock


def run_lineage(name: str, stop_after: int | None = None) -> None:
    """Grow one lineage, holding its lock for the whole run."""
    _tree, base = _lineage_dirs(name)
    lock = _lock(base)
    try:
        _run_lineage(name, stop_after)
    finally:
        try:
            if lock.is_file() and lock.read_text().split()[0] == str(os.getpid()):
                lock.unlink()
        except OSError:
            pass


def _run_lineage(name: str, stop_after: int | None = None) -> None:
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
        # the core layer's room name has no idx suffix, so the bootstrap's
        # gen-2 driver can find it as "{name}{TAG}_00_core_claim"
        room = scratch / (f"{name}{TAG}_00_core_claim" if layer == "core"
                          else f"{name}{TAG}_{idx:02d}_{layer}_claim")
        print(f"[{name} {idx:02d} {layer}] sealing scaffold (all-original, "
              f"warm)...", flush=True)
        _flat_claim(name, idx, room)
        prefix = "src/reticuli" if layer == "reference" else "reticuli"
        threaded = {f"{prefix}/{m}": str(tree / m) for m in _lowers(idx)}
        out = scratch / f"{name}{TAG}_{idx:02d}_{layer}_rebuild"
        grown = False
        kinds = []
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
            if vendor == "mag":
                # the kernel scrubs the room's environment, so the gateway
                # credential must be handed over deliberately here
                key = os.environ.get("AMSC_API_KEY") or os.environ.get("AMSC_TOKEN")
                if not key:
                    print(f"[{name}] AMSC_API_KEY is not set; a MAG lineage "
                          f"cannot run without the gateway credential.",
                          flush=True)
                    return
                penv.update(OPENAI_BASE_URL=MAG_URL, OPENAI_API_KEY=key,
                            RETICULI_PRICE=MAG[name][1])
            try:
                r = kernel.rebuild(str(room), producer, str(out),
                                   input_from=threaded, guidance=False,
                                   producer_env=penv)
            except kernel.ClaimError as exc:
                text = str(exc)
                kind = _classify(text)
                kinds.append(kind)
                if kind == "config":
                    # No retry: the request was refused, not the task. Three
                    # identical 400s only make a configuration error look
                    # like a measurement.
                    print(f"[{name} {idx:02d} {layer}] MISCONFIGURED — the "
                          f"gateway refused the request; this lineage "
                          f"measured nothing.", flush=True)
                    _ledger(base, {"layer": layer, "event": "misconfigured",
                                   "attempt": attempt, "voids_result": True,
                                   "error": text[-300:]})
                    return
                if kind == "quota":
                    # Also a void, and marked as one: a lineage that was
                    # throttled measured availability, not capability. Note
                    # that a 429 is not evidence the allocation is spent --
                    # 2026-10-15, grok-4.7 returned 429 while its own
                    # headers reported 9999 of 10000 requests and 25 billion
                    # allocation tokens remaining, so the refusal was
                    # upstream capacity. Read the headers before the bill.
                    print(f"[{name}] QUOTA/THROTTLED — stopping; re-run to "
                          f"resume. No capability result.", flush=True)
                    _ledger(base, {"layer": layer, "event": "quota",
                                   "attempt": attempt, "voids_result": True,
                                   "error": text[-300:]})
                    return
                _ledger(base, {"layer": layer, "event": "attempt-failed",
                               "attempt": attempt, "failure": kind,
                               "error": text[-300:]})
                continue
            grown = True
            break
        if not grown:
            # A lineage whose every attempt died in the serving path measured
            # the gateway, not the producer. Saying "halted" there would put
            # an outage in the floor table beside a real refusal.
            if kinds and all(k == "infra" for k in kinds):
                print(f"[{name} {idx:02d} {layer}] VOID — every attempt died "
                      f"in the serving path; no capability result.", flush=True)
                _ledger(base, {"layer": layer, "event": "void-infrastructure",
                               "attempts": kinds, "voids_result": True})
                return
            print(f"[{name} {idx:02d} {layer}] did not converge; "
                  f"lineage halted here.", flush=True)
            _ledger(base, {"layer": layer, "event": "halted",
                           "attempts": kinds})
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
