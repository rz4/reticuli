"""A bounded evolutionary investigator: learned operator order is compiled here.

The operation vocabulary and learner are human-authored. No model weights change.
Successors inherit this code and alter their probe policy through measured search.
"""

from __future__ import annotations

import json
import random
import sys

POLICY = []  # compiled-policy
OPERATORS = ["duplicate", "digits", "empty", "plus", "whitespace", "junk", "truncate"]


def mutate(family, text, operator, seed):
    rng = random.Random(seed)
    suffix = "".join(rng.choice("xyz") for _ in range(3))
    if operator == "duplicate":
        separator = "\n" if family == "config" else "&" if family == "query" else ""
        changed = text.partition("=")[0] + "=" + suffix if family != "base64" else text
        return text + separator + changed
    if operator == "digits":
        return (text.partition("=")[0] + "=" + str(rng.randint(10, 99))
                if family != "base64" else "7")
    if operator == "empty":
        return text.partition("=")[0] + "=" if family != "base64" else ""
    if operator == "plus":
        return text + "+" + suffix
    if operator == "whitespace":
        return " " + text
    if operator == "junk":
        return text + "!"
    return text.rstrip("=") if family == "base64" else text[:-1]


def proposals(history):
    """The incumbent itself proposes its extensions, using development feedback.

    Prior search results order candidates but do not set evaluation outcomes.
    The external controller independently executes and chooses among them.
    """
    gains = {}
    for item in history.get("attempts", []):
        gains[item["operator"]] = max(gains.get(item["operator"], -1), item["training_gain"])
    remaining = sorted((op for op in OPERATORS if op not in POLICY),
                       key=lambda op: (-gains.get(op, 0), op))
    return {"parent_policy": POLICY,
            "candidates": [{"operator": op, "policy": POLICY + [op]} for op in remaining]}


def probe_inputs(start, policy):
    family = start["target"]["family"]
    cases = start["target"]["public_gate"]["cases"]
    # Derive probe content from the disclosed gate; no target labels or stored
    # test-answer table are compiled into the successor.
    base = next((case["input"] for case in cases if case["input"]), "")
    for index in range(start["budget"]["probes"]):
        yield (mutate(family, base, policy[index], start["seed"])
               if index < len(policy) else cases[index % len(cases)]["input"])


def investigate(start):
    for value in probe_inputs(start, POLICY):
        print(json.dumps({"op": "probe", "input": value}), flush=True)
        if not sys.stdin.readline():
            return
    print(json.dumps({"op": "finish"}), flush=True)


def main():
    payload = json.loads(sys.stdin.readline())
    if sys.argv[1:] == ["--propose"]:
        print(json.dumps(proposals(payload)), flush=True)
    elif not sys.argv[1:]:
        investigate(payload)
    else:
        raise ValueError("expected no arguments or --propose")


if __name__ == "__main__":
    main()
