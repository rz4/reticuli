"""The reference corpus: assess measurements, accumulated so one claim can be
read against a population instead of in a vacuum.

A mutation rate of 0.60 means something the day it is computed; "blind
re-derivation succeeded" means little until there are twenty such results to
sit it against. assess's intrinsic rungs (circularity, mutation) are born
useful; its population rungs (blind/guided re-derivation, independence,
generalization) gain resolution only as a body of runs accumulates. This module
is that body: an append-only file of flattened assess results, and the
summary/placement that turns it into a distribution.

It is residue by construction and can never move a root. Evidence calibrates how
a claim is *read*, never what it *is*: the corpus advises, and the one doorway
by which research legitimately touches identity — choosing to pin a mutation
floor or a cost envelope informed by the population — stays a keyholder's
deliberate authoring act, never something this module does. The corpus append is
lock-serialized (`_util`), so a swarm assessing many claims at once cannot tear
it.
"""
from __future__ import annotations

import json
import statistics
import time

from . import _util


def flatten(report: dict) -> dict:
    """An assess report reduced to a portable corpus record: provenance plus the
    measured numbers, nothing that ties it to one machine's presentation."""
    m = report.get("measured", {})
    rec: dict = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claim": report.get("claim"),
        "root": report.get("root"),
        "gate": report.get("gate"),
    }
    circ = m.get("circularity")
    if circ:
        rec["circularity_ok"] = bool(circ.get("ok"))
    mut = m.get("mutation")
    if mut and mut.get("mutants"):
        rec["mutation"] = {"rate": mut["rate"], "killed": mut["killed"],
                           "mutants": mut["mutants"],
                           "candidates": mut.get("candidates")}
    red = m.get("re_derivation")
    if red:
        rec["re_derivation_blind"] = bool(red.get("ok"))
    redg = m.get("re_derivation_guided")
    if redg:
        rec["re_derivation_guided"] = bool(redg.get("ok"))
    ind = m.get("independence")
    if ind and ind.get("degree"):
        rec["independence"] = ind["degree"]
    return rec


def load(path: str) -> list[dict]:
    """Every corpus record; a malformed line is skipped, never fatal."""
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        pass
    return out


def append(path: str, record: dict) -> None:
    """Add one record, lock-serialized against concurrent assessors."""
    _util.locked_append(path, json.dumps(record, sort_keys=True) + "\n")


def _rate(records: list[dict], key: str) -> dict | None:
    """The success rate of a boolean measure across the population."""
    seen = [bool(r[key]) for r in records if key in r]
    if not seen:
        return None
    return {"n": len(seen), "passed": sum(seen),
            "rate": round(sum(seen) / len(seen), 3)}


def distribution(records: list[dict]) -> dict:
    """The population, summarized: what a single result should be read against."""
    rates = sorted(r["mutation"]["rate"] for r in records
                   if isinstance(r.get("mutation"), dict)
                   and isinstance(r["mutation"].get("rate"), (int, float)))
    dist: dict = {"n": len(records)}
    if rates:
        dist["mutation"] = {"n": len(rates), "rates": rates,
                            "median": round(statistics.median(rates), 3),
                            "min": rates[0], "max": rates[-1]}
    for key in ("re_derivation_blind", "re_derivation_guided", "circularity_ok"):
        got = _rate(records, key)
        if got:
            dist[key] = got
    degrees: dict[str, int] = {}
    for r in records:
        deg = r.get("independence")
        if deg:
            degrees[deg] = degrees.get(deg, 0) + 1
    if degrees:
        dist["independence"] = degrees
    return dist


def place(record: dict, dist: dict) -> dict:
    """Where one record sits in a population's distribution — a reading aid,
    never a grade. Empty when the population is too thin to say anything."""
    out: dict = {"population": dist.get("n", 0)}
    mut = record.get("mutation")
    mdist = dist.get("mutation")
    if isinstance(mut, dict) and mdist and mdist["rates"]:
        rate = mut["rate"]
        below = sum(1 for x in mdist["rates"] if x <= rate)
        out["mutation"] = {"rate": rate, "median": mdist["median"],
                           "percentile": round(100 * below / len(mdist["rates"])),
                           "of": mdist["n"]}
    for key in ("re_derivation_blind", "re_derivation_guided"):
        if key in record and key in dist:
            out[key] = {"this": bool(record[key]),
                        "population_rate": dist[key]["rate"],
                        "of": dist[key]["n"]}
    return out


def record_and_place(path: str, report: dict) -> dict:
    """Read the prior population, place this report against it, then add it. The
    placement is against the population BEFORE this run, so a claim is never
    compared against itself."""
    prior = load(path)
    rec = flatten(report)
    placement = place(rec, distribution(prior))
    append(path, rec)
    return placement
