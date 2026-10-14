"""Collapse many probes onto the phenomena they witness, and keep the simplest.

A sweep asks every clause of every surface, so one behavioural difference is
witnessed over and over: nineteen documents that all distinguish the same two
members on the same call are nineteen witnesses of one phenomenon, not
nineteen findings. Counting them separately is the error the improvement
harness avoided by crediting an omission once per run, and the error the first
version of this sweep made by minting fifty-seven entries for three facts.

A PHENOMENON is identified by what it does to the population: the surface
probed, and the partition of members into behaviour classes. Two probes that
induce the same partition on the same surface are the same finding.

The WITNESS kept is the simplest probe that induces it, because a person has
to read it before signing. Each source supplies its own simplicity order --
for a spec-derived family that is the clause order, which runs from a
well-formed document outward. The discarded witnesses are not thrown away:
their identifiers travel in the entry, so the breadth of a phenomenon stays
visible and nothing claims to have been checked that was not.
"""

from __future__ import annotations


def signature(result):
    """What makes two results the same finding.

    The partition alone is too coarse: every member accepting and every member
    refusing are both one class holding everyone, and they are not the same
    phenomenon. The behaviour key is too fine in the other direction, because a
    canonicalizer returns different bytes for every document, which would make
    each input its own finding.

    What sits between them is the partition labelled by outcome KIND -- value,
    refused, crashed -- which separates "all four accept" from "all four refuse"
    while still collapsing twenty-four refusals of twenty-four documents.
    """
    shape = tuple(sorted((tuple(members), result["observations"][members[0]]["kind"])
                         for members in result["classes"].values()))
    return (result["pressure"]["call"], result["disposition"], shape)


def collapse(results):
    """Group results by phenomenon; return one reduced result per group."""
    groups = {}
    for result in results:
        groups.setdefault(signature(result), []).append(result)
    reduced = []
    for key in sorted(groups, key=lambda k: (k[0], k[1])):
        members = groups[key]
        # Discriminating power first, then simplicity. A rank borrowed from a
        # witness the entry does not retain could not be re-earned from the
        # entry's own bytes, so the witness kept is the one the rank belongs
        # to -- and among equally discriminating witnesses, the simplest.
        members.sort(key=lambda r: (-r["rank"], r["pressure"].get("simplicity", 0),
                                    r["pressure"]["id"]))
        witness = dict(members[0])
        witness["witnessed_by"] = sorted(r["pressure"]["id"] for r in members)
        witness["witness_count"] = len(members)
        reduced.append(witness)
    return reduced
