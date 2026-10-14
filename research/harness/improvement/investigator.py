"""Two fixed probe strategies for instrument calibration, not learned successors."""

from __future__ import annotations

import argparse
import base64
import json
import random
import sys


def probes(family, strategy, seed):
    rng = random.Random(seed)
    if strategy == "structured":
        if family == "config":
            yield "a=12"
            yield "a=red\na=blue"
            yield "a=7\na=9"
            yield "# note\na=red"
        elif family == "query":
            yield "a=red&a=blue"
            yield "a="
            yield "a=red+blue"
            yield "a=&a=red+blue"
        else:
            yield " aA=="
            yield "aA==!"
            yield "aA"
            yield "aA==\n"
    while True:
        word = "".join(rng.choice("abcdef") for _ in range(5))
        yield base64.b64encode(word.encode()).decode() if family == "base64" else "a=" + word


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["uniform", "structured"], required=True)
    args = parser.parse_args()
    start = json.loads(sys.stdin.readline())
    stream = probes(start["target"]["family"], args.strategy, start["seed"])
    for _ in range(start["budget"]["probes"]):
        print(json.dumps({"op": "probe", "input": next(stream)}), flush=True)
        if not sys.stdin.readline():
            return
    print(json.dumps({"op": "finish"}), flush=True)


if __name__ == "__main__":
    main()
