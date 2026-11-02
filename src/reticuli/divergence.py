"""Declared-shape divergence: verify that two runs differ exactly as stated.

A claim that digests a measured series pins every byte of it, which is right
until a *declared* change touches the surface: the APEIRON campaign's A66 fix
added two warmup-evaluation rows — values identical everywhere — and the
subject's global step counter relabeled every later row, so a two-row,
correct, declared change read as near-total divergence. Most series digests
moved while the underlying measurements did not, and telling "declared fix"
from "drift" required a schema-aware comparator built outside the tool
(`research/proposals/compare_v2.py`, kept verbatim as it ran).

This module is that comparator made declarative. A transition states the
SHAPE of the divergence it expects — which series, which class, and the join
under which everything else must still match exactly — and `verify` holds
the revised data to it: rows outside the declaration refuse, naming the
first offending row, instead of reporting a flat digest mismatch the
receiver must re-derive by hand.

The data model is deliberately small: a run is a mapping of series name to a
list of rows, where a row is a scalar or a flat table (dict). `from_csv`
reads the (step, metric, value) layout the campaign's run claims log.

The declaration:

    {
      "ignore": ["*_time", "*_flops"],    # surfaces excluded from the verdict
      "expect": [
        {"class":  "prefix-added",        # or rows-inserted, value-change
         "series": "eval/*",              # glob or list of globs this clause covers
         "where":  {"stage": "eval"},     # every INSERTED row must carry these fields
         "join":   ["stage", "event_id"], # the fields that identify a row
         "free":   ["step"],              # fields excused on aligned rows (a
                                          #   relabeled global counter)
         "keys":   ["value"]},            # value-change only: the fields allowed
                                          #   to differ on aligned rows
      ],
    }

The classes, from the campaign's own taxonomy:

    prefix-added     revised = [new leading rows] + original  (A66's signature)
    rows-inserted    original is an ordered subsequence of revised, aligned by
                     `join` (A31's signature: the join is the row's own
                     content, never the global counter)
    value-change     same rows, and only the named `keys` differ

A series the declaration does not cover must be identical. A series present
on one side only refuses (a missing series is A67's failure mode, not a
shape). `ignore` is the one escape, and it is visible in the verdict.

Verdicts are RETURNED, not raised — a divergence is an answer. A malformed
declaration is refused with a reason (ClaimError): a shape nobody can read
must not reach a verdict, the same rule the recipe parser holds envelope and
tolerance to.
"""
from __future__ import annotations

import csv
import json
import sys
from fnmatch import fnmatchcase

from .kernel import ClaimError

CLASSES = ("prefix-added", "rows-inserted", "value-change")


def from_csv(path: str) -> dict:
    """Series from the campaign's run-metrics layout: a header naming at
    least (step, metric, value), one series per metric, rows as
    {step, value} tables so a declaration can excuse the counter by name."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return {}
    head = rows[0]
    try:
        si, mi, vi = head.index("step"), head.index("metric"), head.index("value")
    except ValueError:
        raise ClaimError(f"{path}: the header must name step, metric, value "
                         f"(got {head!r})") from None
    out: dict = {}
    for r in rows[1:]:
        if len(r) == len(head):
            out.setdefault(r[mi], []).append({"step": r[si], "value": r[vi]})
    return out


def _validate(declaration) -> tuple:
    """A declared shape must be readable as one, or it is refused here."""
    if not isinstance(declaration, dict):
        raise ClaimError("a declaration must be a table")
    unknown = set(declaration) - {"ignore", "expect"}
    if unknown:
        raise ClaimError(f"unknown declaration key(s): {sorted(unknown)} "
                         "(the vocabulary is ignore, expect)")
    ignore = declaration.get("ignore") or []
    if not isinstance(ignore, list) or any(not isinstance(p, str) for p in ignore):
        raise ClaimError("ignore must be a list of series patterns")
    clauses = declaration.get("expect") or []
    if not isinstance(clauses, list):
        raise ClaimError("expect must be a list of clauses")
    for i, clause in enumerate(clauses):
        if not isinstance(clause, dict):
            raise ClaimError(f"expect[{i}] must be a table")
        cls = clause.get("class")
        if cls not in CLASSES:
            raise ClaimError(f"expect[{i}] class must be one of {CLASSES}, "
                             f"got {cls!r}")
        series = clause.get("series")
        if isinstance(series, str):
            series = [series]
        if not isinstance(series, list) or not series \
                or any(not isinstance(p, str) for p in series):
            raise ClaimError(f"expect[{i}] series must name at least one pattern")
        for key, need in (("where", dict), ("join", list),
                          ("free", list), ("keys", list)):
            value = clause.get(key)
            if value is not None and not isinstance(value, need):
                raise ClaimError(f"expect[{i}] {key} must be a "
                                 f"{need.__name__}, got {value!r}")
        if cls == "value-change" and not clause.get("keys"):
            raise ClaimError(f"expect[{i}]: value-change must name the keys "
                             "allowed to differ")
    return ignore, clauses


def _matches(name: str, patterns) -> bool:
    return any(fnmatchcase(name, p) for p in patterns)


def _aligned(a, b, free) -> bool:
    """Two aligned rows agree — on every field, bar the excused ones."""
    if isinstance(a, dict) and isinstance(b, dict):
        keys = (set(a) | set(b)) - set(free or ())
        return all(a.get(k) == b.get(k) for k in keys)
    return a == b


def _joins(a, b, join) -> bool:
    """Do two rows name the same measurement? With no declared join, a row's
    identity is its full content (bar the excused fields, which the caller
    checks via _aligned)."""
    if join and isinstance(a, dict) and isinstance(b, dict):
        return all(a.get(k) == b.get(k) for k in join)
    return None  # no join declared: identity and equality are the same test


def _carries(row, where) -> bool:
    if not where:
        return True
    return isinstance(row, dict) and all(row.get(k) == v for k, v in where.items())


def _check_inserted(original, revised, clause, prefix_only: bool):
    """original must survive, in order, inside revised; every extra row must
    sit inside the declared surface. Returns (ok, inserted, offender)."""
    join, free, where = clause.get("join"), clause.get("free"), clause.get("where")
    i, inserted, matched_any = 0, 0, False
    for j, row in enumerate(revised):
        if i < len(original):
            same_identity = _joins(original[i], row, join)
            if same_identity is None:
                same_identity = _aligned(original[i], row, free)
            if same_identity:
                if not _aligned(original[i], row, free):
                    # the declared join says this IS original[i], and the
                    # content disagrees: that is drift, not an insertion
                    return False, inserted, (j, row,
                        "matches the original row's identity under the "
                        "declared join but not its content")
                i += 1
                matched_any = True
                continue
        # an insertion — inside the declared surface, and (for prefix-added)
        # before the original has begun
        if prefix_only and matched_any:
            return False, inserted, (j, row, "inserted after the original's "
                                     "first row; the declaration says "
                                     "prefix-added")
        if not _carries(row, where):
            return False, inserted, (j, row,
                "an inserted row outside the declared surface "
                f"(where {where!r})")
        inserted += 1
    if i < len(original):
        return False, inserted, (len(revised), original[i],
            "an original row the revision no longer carries")
    return True, inserted, None


def _check_value_change(original, revised, clause):
    keys, join, free = clause.get("keys") or [], clause.get("join"), clause.get("free")
    if len(original) != len(revised):
        return False, 0, (min(len(original), len(revised)), None,
                          f"value-change cannot add or drop rows "
                          f"({len(original)} became {len(revised)})")
    changed = 0
    excused = set(keys) | set(free or ())
    for j, (a, b) in enumerate(zip(original, revised)):
        identity = _joins(a, b, join)
        if identity is False:
            return False, changed, (j, b, "the row's identity moved under "
                                    "the declared join")
        if isinstance(a, dict) and isinstance(b, dict):
            strayed = sorted(k for k in (set(a) | set(b)) - excused
                             if a.get(k) != b.get(k))
            if strayed:
                return False, changed, (j, b,
                    f"field(s) outside the declared keys differ: {strayed}")
            if any(a.get(k) != b.get(k) for k in keys):
                changed += 1
        elif a != b:
            return False, changed, (j, b, "scalar rows cannot carry a "
                                    "value-change declaration; name the "
                                    "fields with dict rows")
    return True, changed, None


def verify(original: dict, revised: dict, declaration: dict) -> dict:
    """Hold a revised run to the divergence its transition declared.

    `ok` is true iff every series is identical, ignored, or matches a clause
    exactly. Everything else lands in `refusals`, each naming the series and
    the FIRST row outside the declared shape — the answer a receiver acts on,
    where a flat digest mismatch left them re-deriving it by hand."""
    ignore, clauses = _validate(declaration)
    series: dict = {}
    refusals: list = []

    def refuse(name, index, row, reason):
        series[name] = {"class": "refused", "detail": reason}
        refusals.append({"series": name, "index": index, "row": row,
                         "reason": reason})

    for name in sorted(set(original) | set(revised)):
        if _matches(name, ignore):
            series[name] = {"class": "ignored"}
            continue
        a, b = original.get(name), revised.get(name)
        if a is None:
            refuse(name, 0, None, "a series only the revision carries")
            continue
        if b is None:
            refuse(name, 0, None, "a series the revision no longer carries")
            continue
        if a == b:
            series[name] = {"class": "identical"}
            continue
        covering = [(i, c) for i, c in enumerate(clauses)
                    if _matches(name, [c["series"]]
                                if isinstance(c["series"], str) else c["series"])]
        if not covering:
            first = next((j for j, (x, y) in enumerate(zip(a, b)) if x != y),
                         min(len(a), len(b)))
            refuse(name, first, b[first] if first < len(b) else None,
                   "diverges with no declaration covering it")
            continue
        verdict = None
        for i, clause in covering:
            cls = clause["class"]
            if cls == "value-change":
                ok, n, offender = _check_value_change(a, b, clause)
                detail = f"{n} row(s) changed in the declared keys"
            else:
                ok, n, offender = _check_inserted(
                    a, b, clause, prefix_only=(cls == "prefix-added"))
                detail = f"+{n} inserted"
            if ok:
                series[name] = {"class": cls, "clause": i, "detail": detail}
                verdict = True
                break
            verdict = offender
        if verdict is not True:
            j, row, reason = verdict
            refuse(name, j, row, reason)

    counts: dict = {}
    for entry in series.values():
        counts[entry["class"]] = counts.get(entry["class"], 0) + 1
    return {"ok": not refusals, "series": series, "classes": counts,
            "refusals": refusals}


def main(argv=None) -> int:
    """python3 -m reticuli.divergence ORIGINAL REVISED DECLARATION

    Each argument is a file: .csv in the run-metrics layout, or .json as
    {series: [rows]}; the declaration is .json. Exit 0 when the divergence
    is exactly the declared shape; 1 with the refusals otherwise."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3:
        print(main.__doc__, file=sys.stderr)
        return 2

    def load(path):
        if path.endswith(".csv"):
            return from_csv(path)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    try:
        result = verify(load(argv[0]), load(argv[1]), load(argv[2]))
    except (OSError, ValueError, ClaimError) as exc:
        print(f"divergence: {exc}", file=sys.stderr)
        return 2
    for cls in sorted(result["classes"]):
        print(f"{cls:<14} {result['classes'][cls]}")
    for r in result["refusals"]:
        print(f"refused  {r['series']}  row {r['index']}: {r['reason']}"
              + (f"  {r['row']!r}" if r["row"] is not None else ""),
              file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
