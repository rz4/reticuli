"""Budgeted subprocess probe campaigns and deterministic evidence replay.

Candidates are trusted local development programs. Process separation is not a
sandbox; this harness makes no confidentiality or confirmation claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time

import subjects

HERE = Path(__file__).resolve().parent
SCHEMA = "reticuli.improvement.campaign.1"
MAX_LINE = 65536


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluation_contract(budget):
    return {"schema": SCHEMA, "mode": "public-development",
            "isolation": "process-only", "budget": budget,
            "sources": {name: file_digest(HERE / name) for name in ("campaign.py", "subjects.py")},
            "targets": subjects.TARGETS, "scoring": "unique-omission-recovery; equal-target-weight",
            "promotion": "disabled: public fixtures and hand-written strategies"}


def send(proc, payload):
    proc.stdin.write((json.dumps(payload) + "\n").encode())
    proc.stdin.flush()


def receive(proc, selector, pending, deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("candidate exceeded wall-time budget")
    while b"\n" not in pending:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not selector.select(remaining):
            raise TimeoutError("candidate exceeded wall-time budget")
        chunk = os.read(proc.stdout.fileno(), 4096)
        if not chunk:
            raise ValueError("candidate exited without finish")
        pending += chunk
        if len(pending) > MAX_LINE:
            raise ValueError("candidate response exceeds protocol byte limit")
    line, pending = pending.split(b"\n", 1)
    return json.loads(line), pending


def stop(proc):
    # Group cleanup includes child processes started by the local candidate.
    # A candidate that exits on its own leaves a process group whose only
    # member is its unreaped leader. Signalling that group reports ESRCH on
    # Linux and EPERM on macOS; both mean nothing is left to signal, and the
    # waiting and closing below is the cleanup that still has to happen.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    finally:
        proc.wait()
        proc.stdin.close()
        proc.stdout.close()


def run_candidate(target, command, seed, budget):
    subjects.check_population(target)
    contract = subjects.public_contract(target)
    context = {"schema": "reticuli.improvement.protocol.1", "event": "start",
               "target": {"family": subjects.TARGETS[target]["family"],
                          "boundary_digest": subjects.digest(contract),
                          "public_gate": contract,
                          "realizations": subjects.TARGETS[target]["realizations"]},
               "seed": seed, "budget": budget}
    started = time.monotonic()
    record = {"target": target, "seed": seed, "context": context,
              "status": "failed", "error": None, "probes": []}
    with tempfile.TemporaryFile() as errors, tempfile.TemporaryDirectory() as work:
        try:
            proc = subprocess.Popen(command, cwd=work, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=errors, start_new_session=True,
                                    env={"PATH": os.defpath, "PYTHONHASHSEED": "0"})
        except OSError as exc:
            record.update(error=str(exc), elapsed_seconds=time.monotonic() - started,
                          stderr_excerpt="", score=score(record))
            return record
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        pending = b""
        try:
            send(proc, context)
            deadline = started + budget["seconds"]
            while True:
                request, pending = receive(proc, selector, pending, deadline)
                if not isinstance(request, dict):
                    raise ValueError("request must be an object")
                if request == {"op": "finish"}:
                    record["status"] = "completed"
                    break
                if set(request) != {"op", "input"} or request["op"] != "probe":
                    raise ValueError("expected probe(input) or finish")
                value = request["input"]
                if not isinstance(value, str) or len(value.encode()) > contract["max_input_bytes"]:
                    raise ValueError("probe input must be a string within the byte limit")
                if len(record["probes"]) >= budget["probes"]:
                    record["status"] = "budget_exhausted"
                    break
                evidence = subjects.evaluate_probe(target, value)
                record["probes"].append(evidence)
                send(proc, {"event": "observation", "observations": evidence["observations"]})
        except TimeoutError as exc:
            record["status"], record["error"] = "timeout", str(exc)
        except (ValueError, UnicodeError, OSError) as exc:
            record["error"] = str(exc)
        finally:
            selector.close()
            stop(proc)
        errors.seek(0)
        record["stderr_excerpt"] = errors.read(4096).decode(errors="replace")
    record["elapsed_seconds"] = time.monotonic() - started
    record["score"] = score(record)
    return record


def score(record):
    known = subjects.TARGETS[record["target"]]["omissions"]
    found = sorted({label for p in record["probes"] for label in p["omissions"]})
    valid = record["status"] in ("completed", "budget_exhausted")
    return {"found": found, "credited": found if valid else [], "known": known,
            "recall": len(found) / len(known) if valid and known else 0.0,
            "control": not known,
            "shared_failure_witnesses": sum(bool(p["omissions"]) and not p["differential"]
                                            for p in record["probes"]),
            "probes_used": len(record["probes"]),
            "target_calls": len(record["probes"]) * len(subjects.TARGETS[record["target"]]["realizations"])}


def summarize(runs):
    by_arm = {}
    targets = sorted({r["target"] for r in runs})
    for arm in sorted({r["arm"] for r in runs}):
        rows = [r for r in runs if r["arm"] == arm]
        per_target = {t: sum(r["score"]["recall"] for r in rows if r["target"] == t) /
                     sum(r["target"] == t for r in rows) for t in targets}
        measured = [v for t, v in per_target.items() if subjects.TARGETS[t]["omissions"]]
        by_arm[arm] = {"per_target_recall": per_target,
                       "mean_target_recall": sum(measured) / len(measured),
                       "assigned_runs": len(rows),
                       "failed_runs": sum(r["status"] not in ("completed", "budget_exhausted") for r in rows),
                       "target_calls": sum(r["score"]["target_calls"] for r in rows)}
    difference = by_arm["candidate"]["mean_target_recall"] - by_arm["baseline"]["mean_target_recall"]
    return {"arms": by_arm, "candidate_minus_baseline": difference,
            "analysis": "descriptive paired target means; no significance or promotion claim",
            "promotion": "incomplete: development fixtures are public; candidate is hand-written"}


def candidate_command(path, strategy):
    command = [sys.executable, "-I", str(Path(path).resolve())]
    if strategy:
        command += ["--strategy", strategy]
    return command


def run_campaign(out, *, seeds, probes, seconds, candidate=None):
    if seeds < 1 or probes < 1 or seconds <= 0 or not math.isfinite(seconds):
        raise ValueError("seeds, probes, and seconds must be positive")
    out = Path(out)
    # Refuse overwriting evidence, even an empty pre-existing directory.
    out.mkdir(parents=True, exist_ok=False)
    budget = {"probes": probes, "seconds": seconds}
    contract = evaluation_contract(budget)
    worker = HERE / "investigator.py"
    challenger = Path(candidate).resolve() if candidate else worker
    arms = {"baseline": {"path": worker, "strategy": "uniform"},
            "candidate": {"path": challenger, "strategy": None if candidate else "structured"}}
    manifest = {"schema": SCHEMA, "evaluation": contract,
                "evaluation_digest": subjects.digest(contract), "seeds": list(range(seeds)),
                "arms": {}, "run_files": []}
    for arm, config in arms.items():
        source = config["path"].read_bytes()
        (out / f"{arm}.py").write_bytes(source)
        manifest["arms"][arm] = {"source_digest": hashlib.sha256(source).hexdigest(),
                                  "strategy": config["strategy"]}
    for name in contract["sources"]:
        (out / name).write_bytes((HERE / name).read_bytes())
    runs = []
    for target in sorted(subjects.TARGETS):
        for seed in manifest["seeds"]:
            # Alternate arm order; align target, pool, seed and resource limits.
            order = ("baseline", "candidate") if seed % 2 == 0 else ("candidate", "baseline")
            for arm in order:
                config = arms[arm]
                command = candidate_command(out / f"{arm}.py", config["strategy"])
                record = run_candidate(target, command, seed, budget)
                record["arm"] = arm
                filename = f"{target}-{seed}-{arm}.json"
                data = json.dumps(record, indent=2, sort_keys=True) + "\n"
                (out / filename).write_text(data)
                manifest["run_files"].append({"file": filename,
                                               "digest": hashlib.sha256(data.encode()).hexdigest()})
                runs.append(record)
    summary = summarize(runs)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_claim_recipe(out, manifest)
    return summary


def write_claim_recipe(out, manifest):
    """A replayable evidence claim, not a claim that discovery improved."""
    check = ('from pathlib import Path\nimport campaign\n'
             'campaign.replay(Path(__file__).resolve().parent)\n'
             'Path("EVIDENCE_OK").write_text("ok\\n")\n')
    (out / "check_replay.py").write_text(check)
    inputs = ["check_replay.py", "campaign.py", "subjects.py", "baseline.py", "candidate.py",
              "manifest.json", "summary.json"] + [item["file"] for item in manifest["run_files"]]
    recipe = ('[claim]\nname = "improvement-evidence"\nformat = 4\ninputs = ' +
              json.dumps(inputs) + '\n\n[[step]]\nkind = "gate"\n'
              'output = "EVIDENCE_OK"\nclass = "validated"\n'
              'run = "python3 check_replay.py"\n')
    (out / "reticuli.toml").write_text(recipe)


def replay(out):
    out = Path(out)
    manifest = json.loads((out / "manifest.json").read_text())
    if manifest["schema"] != SCHEMA:
        raise ValueError("unsupported campaign schema")
    if set(manifest["arms"]) != {"baseline", "candidate"}:
        raise ValueError("campaign must contain exactly baseline and candidate")
    seeds = manifest["seeds"]
    if (not isinstance(seeds, list) or not seeds or
            any(type(seed) is not int or seed < 0 for seed in seeds) or
            len(seeds) != len(set(seeds))):
        raise ValueError("campaign seeds must be distinct nonnegative integers")
    contract = manifest["evaluation"]
    if subjects.digest(contract) != manifest["evaluation_digest"]:
        raise ValueError("evaluation contract digest mismatch")
    if evaluation_contract(contract["budget"]) != contract:
        raise ValueError("evaluator source or contract changed; replay with retained source snapshot")
    for name, expected in contract["sources"].items():
        if file_digest(out / name) != expected:
            raise ValueError(f"retained evaluator changed: {name}")
    for arm, config in manifest["arms"].items():
        if file_digest(out / f"{arm}.py") != config["source_digest"]:
            raise ValueError(f"candidate source changed: {arm}")
    runs = []
    seen = set()
    for item in manifest["run_files"]:
        name = item["file"]
        if Path(name).name != name or name in seen:
            raise ValueError("invalid or duplicate run filename")
        seen.add(name)
        if file_digest(out / name) != item["digest"]:
            raise ValueError(f"run evidence digest mismatch: {name}")
        record = json.loads((out / name).read_text())
        target, seed = record["target"], record["seed"]
        subjects.check_population(target)
        public = subjects.public_contract(target)
        context = {"schema": "reticuli.improvement.protocol.1", "event": "start",
                   "target": {"family": subjects.TARGETS[target]["family"],
                              "boundary_digest": subjects.digest(public), "public_gate": public,
                              "realizations": subjects.TARGETS[target]["realizations"]},
                   "seed": seed, "budget": contract["budget"]}
        if record["context"] != context:
            raise ValueError("run context does not match assigned conditions")
        if record["status"] not in ("completed", "budget_exhausted", "failed", "timeout"):
            raise ValueError("unknown run status")
        if len(record["probes"]) > contract["budget"]["probes"]:
            raise ValueError("record exceeds probe budget")
        for evidence in record["probes"]:
            value = evidence["input"]
            if not isinstance(value, str) or len(value.encode()) > public["max_input_bytes"]:
                raise ValueError("invalid retained input")
            if subjects.evaluate_probe(record["target"], evidence["input"]) != evidence:
                raise ValueError(f"witness failed replay: {name}")
        if score(record) != record["score"]:
            raise ValueError(f"score failed replay: {name}")
        runs.append(record)
    expected = {(t, seed, arm) for t in subjects.TARGETS for seed in manifest["seeds"]
                for arm in ("baseline", "candidate")}
    actual = [(r["target"], r["seed"], r["arm"]) for r in runs]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("assigned runs are missing or duplicated")
    summary = summarize(runs)
    if json.loads((out / "summary.json").read_text()) != summary:
        raise ValueError("summary failed independent recomputation")
    return {"replayed_runs": len(runs), "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)
    run = sub.add_parser("run")
    run.add_argument("--out", required=True)
    run.add_argument("--seeds", type=int, default=5)
    run.add_argument("--probes", type=int, default=12)
    run.add_argument("--seconds", type=float, default=3.0)
    run.add_argument("--candidate", help="standalone Python protocol program; trusted local code")
    audit = sub.add_parser("replay")
    audit.add_argument("directory")
    args = parser.parse_args()
    try:
        result = (replay(args.directory) if args.verb == "replay" else
                  run_campaign(args.out, seeds=args.seeds, probes=args.probes,
                               seconds=args.seconds, candidate=args.candidate))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"improvement: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
