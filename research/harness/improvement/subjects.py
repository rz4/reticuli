"""Public development fixtures. These are controlled tasks, not hidden tests."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from urllib.parse import parse_qsl


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


TARGETS = {
    "config-mixed": {"family": "config", "realizations": ["strings-last", "numbers-first"],
                     "omissions": ["numeric-coercion", "duplicate-first"]},
    "config-shared": {"family": "config", "realizations": ["strings-last", "strings-last-copy"],
                      "omissions": ["numeric-coercion", "duplicate-first"]},
    "base64-mixed": {"family": "base64", "realizations": ["strict", "permissive", "unpadded"],
                     "omissions": ["whitespace-rejection", "junk-rejection", "padding-required"]},
    "base64-shared": {"family": "base64", "realizations": ["unpadded", "unpadded-copy"],
                      "omissions": ["whitespace-rejection", "junk-rejection", "padding-required"]},
    "query-mixed": {"family": "query", "realizations": ["lossy", "complete"],
                    "omissions": ["duplicate-preservation", "blank-preservation", "plus-decoding"]},
    "query-shared": {"family": "query", "realizations": ["lossy", "lossy-copy"],
                     "omissions": ["duplicate-preservation", "blank-preservation", "plus-decoding"]},
    "config-control": {"family": "config", "realizations": ["numbers-first", "numbers-first-copy"],
                       "omissions": []},
}


def config(text, *, numbers, first):
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if numbers and value.isdecimal():
            value = int(value)
        if not first or key not in result:
            result[key] = value
    return result


def query(text, *, complete):
    if complete:
        result = {}
        for key, value in parse_qsl(text, keep_blank_values=True):
            result.setdefault(key, []).append(value)
        return result
    result = {}
    for item in text.split("&"):
        key, sep, value = item.partition("=")
        if sep and value:
            result[key] = [value]
    return result


def observe(target, realization, text):
    """Canonical JSON outcomes; only fixture exceptions are normalized."""
    family = TARGETS[target]["family"]
    try:
        if family == "config":
            value = config(text, numbers=realization.startswith("numbers"),
                           first=realization.startswith("numbers"))
        elif family == "query":
            value = query(text, complete=realization == "complete")
        else:
            data = text.encode("ascii")
            if realization.startswith("unpadded"):
                data += b"=" * (-len(data) % 4)
            value = base64.b64decode(data, validate=realization == "strict").hex()
        return {"kind": "value", "value": value}
    except (ValueError, UnicodeError, binascii.Error):
        return {"kind": "rejected"}


def public_contract(target):
    family = TARGETS[target]["family"]
    cases = (["a=red", "b=blue"] if family == "config" else
             ["a=red", "b=blue"] if family == "query" else ["", "aA==", "aGk="])
    reference = {"config": "numbers-first", "query": "complete", "base64": "strict"}[family]
    return {"schema": "reticuli.improvement.boundary.1", "family": family,
            "input_type": "string", "max_input_bytes": 256,
            "cases": [{"input": x, "expected": observe(target, reference, x)} for x in cases]}


def check_population(target):
    contract = public_contract(target)
    for realization in TARGETS[target]["realizations"]:
        for case in contract["cases"]:
            if observe(target, realization, case["input"]) != case["expected"]:
                raise ValueError(f"{target}/{realization} does not satisfy public gate")


def evaluate_probe(target, text):
    """Return observations and independently labelled consumer breaks.

    Labels belong to the controller. Candidate feedback receives observations only.
    Realization partitions are not used as semantic omission identifiers.
    """
    spec = TARGETS[target]
    observations = {r: observe(target, r, text) for r in spec["realizations"]}
    family = spec["family"]
    reference = {"config": "numbers-first", "query": "complete", "base64": "strict"}[family]
    expected = observe(target, reference, text)
    broken = [r for r, outcome in observations.items() if outcome != expected]
    labels = set()
    if broken and family == "config" and expected["kind"] == "value":
        strings = config(text, numbers=False, first=True)
        last = config(text, numbers=True, first=False)
        if strings != expected["value"]:
            labels.add("numeric-coercion")
        if last != expected["value"]:
            labels.add("duplicate-first")
    elif broken and family == "query":
        complete = query(text, complete=True)
        if any(len(v) > 1 for v in complete.values()):
            labels.add("duplicate-preservation")
        if any("" in v for v in complete.values()):
            labels.add("blank-preservation")
        if "+" in text and any(" " in key or any(" " in v for v in values)
                               for key, values in complete.items()):
            labels.add("plus-decoding")
    elif broken and family == "base64" and expected["kind"] == "rejected":
        if any(c.isspace() for c in text):
            labels.add("whitespace-rejection")
        elif any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
                 for c in text):
            labels.add("junk-rejection")
        elif len(text) % 4:
            labels.add("padding-required")
    return {"input": text, "observations": observations, "consumer_expected": expected,
            "broken_realizations": broken, "omissions": sorted(labels & set(spec["omissions"])),
            "differential": len({digest(v) for v in observations.values()}) > 1}
