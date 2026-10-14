"""Generate, measure and adopt bounded investigator successors without API calls."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import time

import campaign
import policy_template
import subjects

HERE = Path(__file__).resolve().parent
SCHEMA = "reticuli.improvement.lineage.1"
TRAIN = ["config-mixed", "base64-mixed", "query-mixed"]
VALIDATE = ["config-shared", "base64-shared", "query-shared", "config-control"]
SOURCES = ["evolve.py", "campaign.py", "subjects.py", "policy_template.py"]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def compile_policy(parent_source, policy):
    if (not isinstance(policy, list) or len(policy) != len(set(policy)) or
            any(op not in policy_template.OPERATORS for op in policy)):
        raise ValueError("invalid successor policy")
    source, count = re.subn(r"^POLICY = .*  # compiled-policy$",
                           lambda _: "POLICY = " + repr(policy) + "  # compiled-policy",
                           parent_source, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("parent has no unique policy compilation point")
    return source


def request_proposals(parent, history):
    # Reuse the deadline/line bound and process-group cleanup of the investigator
    # protocol. Only trusted, compiled local investigators are executed here.
    import selectors
    import subprocess

    with tempfile.TemporaryFile() as errors, tempfile.TemporaryDirectory() as work:
        proc = subprocess.Popen(campaign.candidate_command(parent, None) + ["--propose"],
                                cwd=work, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=errors, start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            campaign.send(proc, history)
            reply, _ = campaign.receive(proc, selector, b"", time.monotonic() + 3)
            return reply
        finally:
            selector.close()
            campaign.stop(proc)


def evaluate(path, targets, seeds, budget):
    rows = []
    for target in targets:
        for seed in seeds:
            rows.append(campaign.run_candidate(target, campaign.candidate_command(path, None),
                                               seed, budget))
    return {"targets": targets, "seeds": seeds, "runs": rows, "metrics": metrics(rows)}


def metrics(rows):
    target_means = {}
    for target in sorted({r["target"] for r in rows}):
        group = [r for r in rows if r["target"] == target]
        target_means[target] = sum(r["score"]["recall"] for r in group) / len(group)
    measured = [v for t, v in target_means.items() if subjects.TARGETS[t]["omissions"]]
    return {"recall": sum(measured) / len(measured), "per_target": target_means,
            "failed": sum(r["status"] not in ("completed", "budget_exhausted") for r in rows),
            "target_calls": sum(r["score"]["target_calls"] for r in rows)}


def decision(parent_train, child_train, parent_validation, child_validation, minimum_gain):
    train_gain = child_train["recall"] - parent_train["recall"]
    validation_gain = child_validation["recall"] - parent_validation["recall"]
    nonregression = all(child_validation["per_target"][t] >= value
                        for t, value in parent_validation["per_target"].items())
    accepted = (train_gain >= minimum_gain and validation_gain >= minimum_gain and
                nonregression and child_train["failed"] == child_validation["failed"] == 0)
    return {"accepted": accepted, "training_gain": train_gain,
            "validation_gain": validation_gain, "nonregression": nonregression,
            "scope": "local policy adoption on public controlled fixtures; not external promotion"}


def run(out, *, rounds=3, seeds=2, probes=8, seconds=2.0, minimum_gain=0.05):
    if (type(rounds) is not int or not 1 <= rounds <= 32 or type(seeds) is not int or
            not 1 <= seeds <= 100 or type(probes) is not int or not 1 <= probes <= 100 or
            not math.isfinite(seconds) or seconds <= 0 or
            not math.isfinite(minimum_gain) or not 0 < minimum_gain <= 1):
        raise ValueError("invalid bounded search configuration")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    for name in SOURCES:
        (out / name).write_bytes((HERE / name).read_bytes())
    contract = {"schema": SCHEMA, "mode": "public-development", "rounds": rounds,
                "budget": {"probes": probes, "seconds": seconds}, "minimum_gain": minimum_gain,
                "training_targets": TRAIN, "validation_targets": VALIDATE,
                "training_seeds": list(range(seeds)), "validation_seeds": list(range(1000, 1000 + seeds)),
                "sources": {name: campaign.file_digest(HERE / name) for name in SOURCES},
                "operators": policy_template.OPERATORS,
                "selection": "largest training recall, then lexicographic operator; one validation per round",
                "external_promotion": "incomplete: public sibling fixtures, fixed mutation vocabulary"}
    lineage = {"schema": SCHEMA, "contract": contract, "contract_digest": subjects.digest(contract),
               "rounds": [], "history": [], "active": "generation-0.py"}
    parent = out / lineage["active"]
    parent.write_text(compile_policy((out / "policy_template.py").read_text(), []))
    initial = evaluate(parent, TRAIN, contract["training_seeds"], contract["budget"])
    lineage["initial"] = initial
    save(out / "lineage.json", lineage)
    history = {"attempts": []}
    active_policy = []
    for index in range(rounds):
        # The active investigator, rather than the controller, emits its own
        # successor policies. It receives development history only.
        proposal = request_proposals(parent, history)
        if proposal.get("parent_policy") != active_policy:
            raise ValueError("proposal does not identify the active parent policy")
        candidates = proposal.get("candidates")
        remaining = set(policy_template.OPERATORS) - set(active_policy)
        if (not isinstance(candidates, list) or
                {p.get("operator") for p in candidates} != remaining or len(candidates) != len(remaining)):
            raise ValueError("proposal must enumerate each allowed unused operator once")
        if not candidates:
            lineage["stop_reason"] = "mutation vocabulary exhausted"
            break
        parent_train = evaluate(parent, TRAIN, contract["training_seeds"], contract["budget"])
        attempts = []
        for number, item in enumerate(candidates):
            op = item["operator"]
            policy = item["policy"]
            if policy != active_policy + [op]:
                raise ValueError("successor must inherit parent policy and add one operator")
            name = f"round-{index + 1}-candidate-{number}.py"
            path = out / name
            path.write_text(compile_policy(parent.read_text(), policy))
            result = evaluate(path, TRAIN, contract["training_seeds"], contract["budget"])
            attempts.append({"file": name, "operator": op, "policy": policy,
                             "source_digest": campaign.file_digest(path), "evaluation": result})
            history["attempts"].append({"operator": op,
                                       "training_gain": result["metrics"]["recall"] -
                                       parent_train["metrics"]["recall"]})
        winner = sorted(attempts, key=lambda a: (-a["evaluation"]["metrics"]["recall"], a["operator"]))[0]
        parent_validation = evaluate(parent, VALIDATE, contract["validation_seeds"], contract["budget"])
        child_validation = evaluate(out / winner["file"], VALIDATE,
                                    contract["validation_seeds"], contract["budget"])
        ruling = decision(parent_train["metrics"], winner["evaluation"]["metrics"],
                          parent_validation["metrics"], child_validation["metrics"], minimum_gain)
        record = {"parent": parent.name, "parent_digest": campaign.file_digest(parent),
                  "proposal": proposal, "parent_training": parent_train, "attempts": attempts,
                  "winner": winner["file"], "parent_validation": parent_validation,
                  "child_validation": child_validation, "decision": ruling}
        if ruling["accepted"]:
            name = f"generation-{index + 1}.py"
            (out / name).write_bytes((out / winner["file"]).read_bytes())
            parent, active_policy = out / name, winner["policy"]
            lineage["active"] = name
        lineage["rounds"].append(record)
        lineage["history"] = history["attempts"]
        save(out / "lineage.json", lineage)
        if not ruling["accepted"]:
            lineage["stop_reason"] = "selected successor failed local adoption conditions"
            break
    lineage.setdefault("stop_reason", "round budget exhausted")
    lineage["final_policy"] = active_policy
    lineage["active_digest"] = campaign.file_digest(parent)
    lineage["final"] = evaluate(parent, TRAIN + VALIDATE,
                                contract["validation_seeds"], contract["budget"])
    lineage["frozen"] = evaluate(out / "generation-0.py", TRAIN + VALIDATE,
                                 contract["validation_seeds"], contract["budget"])
    save(out / "lineage.json", lineage)
    write_recipe(out)
    return summary(lineage)


def summary(lineage):
    evaluations = [lineage["initial"], lineage["final"], lineage["frozen"]]
    for record in lineage["rounds"]:
        evaluations.extend([record["parent_training"], record["parent_validation"],
                            record["child_validation"]])
        evaluations.extend(a["evaluation"] for a in record["attempts"])
    return {"accepted_generations": sum(r["decision"]["accepted"] for r in lineage["rounds"]),
            "initial_training_recall": lineage["initial"]["metrics"]["recall"],
            "final_recall": lineage["final"]["metrics"]["recall"],
            "frozen_recall": lineage["frozen"]["metrics"]["recall"],
            "final_minus_frozen": lineage["final"]["metrics"]["recall"] -
                                  lineage["frozen"]["metrics"]["recall"],
            "total_evaluation_runs": sum(len(e["runs"]) for e in evaluations),
            "total_search_target_calls": sum(e["metrics"]["target_calls"] for e in evaluations),
            "policy": lineage["final_policy"], "active": lineage["active"],
            "stop_reason": lineage["stop_reason"],
            "external_promotion": lineage["contract"]["external_promotion"]}


def write_recipe(out):
    (out / "check_lineage.py").write_text(
        'from pathlib import Path\nimport evolve\n'
        'evolve.replay(Path(__file__).resolve().parent)\n'
        'Path("LINEAGE_OK").write_text("ok\\n")\n')
    inputs = sorted(p.name for p in out.iterdir() if p.is_file())
    (out / "reticuli.toml").write_text(
        '[claim]\nname = "investigator-policy-lineage"\nformat = 4\ninputs = ' +
        json.dumps(inputs) + '\n\n[[step]]\nkind = "gate"\noutput = "LINEAGE_OK"\n'
        'class = "validated"\nrun = "python3 check_lineage.py"\n')


def check_evaluation(result, targets, seeds, budget, policy):
    if result["targets"] != targets or result["seeds"] != seeds:
        raise ValueError("evaluation panel changed")
    rows = result["runs"]
    expected = {(t, s) for t in targets for s in seeds}
    actual = [(r["target"], r["seed"]) for r in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("assigned lineage runs missing or duplicated")
    for row in rows:
        target = row["target"]
        subjects.check_population(target)
        public = subjects.public_contract(target)
        context = {"schema": "reticuli.improvement.protocol.1", "event": "start",
                   "target": {"family": subjects.TARGETS[target]["family"],
                              "boundary_digest": subjects.digest(public), "public_gate": public,
                              "realizations": subjects.TARGETS[target]["realizations"]},
                   "seed": row["seed"], "budget": budget}
        if row["context"] != context or len(row["probes"]) > budget["probes"]:
            raise ValueError("lineage run budget changed")
        if row["status"] not in ("completed", "budget_exhausted", "failed", "timeout"):
            raise ValueError("unknown lineage run status")
        if row["status"] in ("completed", "budget_exhausted") and len(row["probes"]) != budget["probes"]:
            raise ValueError("compiled investigator completed without its assigned probes")
        expected_inputs = list(policy_template.probe_inputs(context, policy))
        if [p["input"] for p in row["probes"]] != expected_inputs[:len(row["probes"])]:
            raise ValueError("recorded probes do not belong to the claimed investigator")
        for evidence in row["probes"]:
            if subjects.evaluate_probe(row["target"], evidence["input"]) != evidence:
                raise ValueError("lineage witness did not re-earn")
        if campaign.score(row) != row["score"]:
            raise ValueError("lineage score did not re-earn")
    if metrics(rows) != result["metrics"]:
        raise ValueError("lineage aggregate did not re-earn")


def replay(out):
    out = Path(out)
    lineage = json.loads((out / "lineage.json").read_text())
    contract = lineage["contract"]
    if lineage["schema"] != SCHEMA or subjects.digest(contract) != lineage["contract_digest"]:
        raise ValueError("lineage contract changed")
    if (contract["sources"] != {name: campaign.file_digest(HERE / name) for name in SOURCES} or
            contract["training_targets"] != TRAIN or contract["validation_targets"] != VALIDATE or
            contract["operators"] != policy_template.OPERATORS):
        raise ValueError("lineage evaluator changed; use retained source snapshot")
    for name, value in contract["sources"].items():
        if campaign.file_digest(out / name) != value:
            raise ValueError("retained evaluator changed")
    parent = "generation-0.py"
    source = compile_policy((out / "policy_template.py").read_text(), [])
    if (out / parent).read_text() != source:
        raise ValueError("initial investigator changed")
    policy = []
    history = {"attempts": []}
    check_evaluation(lineage["initial"], TRAIN, contract["training_seeds"], contract["budget"], [])
    if len(lineage["rounds"]) > contract["rounds"]:
        raise ValueError("round budget exceeded")
    for index, record in enumerate(lineage["rounds"]):
        if record["parent"] != parent or record["parent_digest"] != campaign.file_digest(out / parent):
            raise ValueError("lineage parent changed")
        # Proposals are regenerated by the recorded parent, not trusted from JSON.
        if request_proposals(out / parent, history) != record["proposal"]:
            raise ValueError("successor proposal did not re-earn")
        check_evaluation(record["parent_training"], TRAIN, contract["training_seeds"], contract["budget"], policy)
        attempts = record["attempts"]
        proposal_items = record["proposal"]["candidates"]
        if len(attempts) != len(proposal_items):
            raise ValueError("candidate search evidence missing")
        for number, (attempt, proposal) in enumerate(zip(attempts, proposal_items)):
            name = f"round-{index + 1}-candidate-{number}.py"
            if (attempt["file"] != name or attempt["policy"] != policy + [proposal["operator"]] or
                    attempt["operator"] != proposal["operator"] or
                    (out / name).read_text() != compile_policy((out / parent).read_text(), attempt["policy"]) or
                    campaign.file_digest(out / name) != attempt["source_digest"]):
                raise ValueError("successor source or inheritance changed")
            check_evaluation(attempt["evaluation"], TRAIN, contract["training_seeds"],
                             contract["budget"], attempt["policy"])
            history["attempts"].append({"operator": attempt["operator"],
                                       "training_gain": attempt["evaluation"]["metrics"]["recall"] -
                                       record["parent_training"]["metrics"]["recall"]})
        winner = sorted(attempts, key=lambda a: (-a["evaluation"]["metrics"]["recall"], a["operator"]))[0]
        if winner["file"] != record["winner"]:
            raise ValueError("winner selection did not re-earn")
        check_evaluation(record["parent_validation"], VALIDATE, contract["validation_seeds"],
                         contract["budget"], policy)
        check_evaluation(record["child_validation"], VALIDATE, contract["validation_seeds"],
                         contract["budget"], winner["policy"])
        ruling = decision(record["parent_training"]["metrics"], winner["evaluation"]["metrics"],
                          record["parent_validation"]["metrics"], record["child_validation"]["metrics"],
                          contract["minimum_gain"])
        if ruling != record["decision"]:
            raise ValueError("adoption decision did not re-earn")
        if ruling["accepted"]:
            parent = f"generation-{index + 1}.py"
            if (out / parent).read_bytes() != (out / winner["file"]).read_bytes():
                raise ValueError("adopted successor changed")
            policy = winner["policy"]
        elif index != len(lineage["rounds"]) - 1:
            raise ValueError("continued after rejected adoption")
    if (lineage["active"] != parent or lineage["final_policy"] != policy or
            lineage["active_digest"] != campaign.file_digest(out / parent) or
            lineage["history"] != history["attempts"]):
        raise ValueError("active lineage state changed")
    check_evaluation(lineage["final"], TRAIN + VALIDATE, contract["validation_seeds"], contract["budget"], policy)
    check_evaluation(lineage["frozen"], TRAIN + VALIDATE, contract["validation_seeds"], contract["budget"], [])
    expected_stop = ("selected successor failed local adoption conditions"
                     if lineage["rounds"] and not lineage["rounds"][-1]["decision"]["accepted"] else
                     "mutation vocabulary exhausted" if len(lineage["rounds"]) < contract["rounds"] else
                     "round budget exhausted")
    if lineage["stop_reason"] != expected_stop:
        raise ValueError("lineage stop condition did not re-earn")
    return summary(lineage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)
    start = sub.add_parser("run")
    start.add_argument("--out", required=True)
    start.add_argument("--rounds", type=int, default=3)
    start.add_argument("--seeds", type=int, default=2)
    start.add_argument("--probes", type=int, default=8)
    start.add_argument("--seconds", type=float, default=2)
    start.add_argument("--minimum-gain", type=float, default=0.05)
    audit = sub.add_parser("replay")
    audit.add_argument("directory")
    args = parser.parse_args()
    try:
        result = replay(args.directory) if args.verb == "replay" else run(
            args.out, rounds=args.rounds, seeds=args.seeds, probes=args.probes,
            seconds=args.seconds, minimum_gain=args.minimum_gain)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"evolve: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
