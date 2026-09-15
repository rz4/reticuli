"""The claim over a TOML 1.0.0 parser: the whole toml-test 1.0.0 corpus must hold.

This file is a PINNED input. The claim's root hash covers exactly: `claim.toml`,
this script, the two licences, all 917 files under `cases/`, and the verdict
`TOML_OK`. The parser it judges is NOT covered: the `tomli/` package is a
`generated` step, outside identity. So the root does not name a version of
tomli; it names *any* program that, placed at `tomli/`, satisfies this script
against these bytes. tomli and CPython's stdlib `tomllib` are two members of
that class.

What is being claimed, precisely:

  A Python package importable as `tomli` from this directory, exposing
  `load(binary_file)` and `TOMLDecodeError`, such that for every case in the
  pinned corpus:
    * a `valid/NAME.toml` parses, and its result equals `valid/NAME.json`
      read as toml-test's tagged JSON -- compared SEMANTICALLY (values and
      types), never textually, and never by key order;
    * an `invalid/NAME.toml` is REFUSED -- the parser raises a declared
      decode error. Parsing it is a failure; crashing on it is also a failure.

  Tables arrive as `dict`, arrays as `list`. That is the shape tomli's API
  contracts, so it is part of the claim rather than an accident of the harness.

Stdlib only. Deterministic: same bytes in, same bytes out, no clock, no
network, no absolute paths in the output.
"""

import sys

sys.dont_write_bytecode = True  # leave no __pycache__ inside the claim

import datetime
import io
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# --- import the parser UNDER CLAIM, not whatever is installed on the host ---
# The claim is about the bytes sitting in ./tomli/. A `tomli` from
# site-packages would silently judge the wrong program, so evict any that is
# already loaded, put this directory first on the path, and then verify that
# the module we actually got came from here.
for _name in [m for m in sys.modules if m == "tomli" or m.startswith("tomli.")]:
    del sys.modules[_name]
sys.path.insert(0, HERE)
import tomli  # noqa: E402

_origin = os.path.dirname(os.path.abspath(tomli.__file__))
if _origin != os.path.join(HERE, "tomli"):
    sys.exit(f"REFUSED: imported tomli from {_origin!r}, not from the claim directory")

CASES = os.path.join(HERE, "cases")

# The TOML 1.0.0 slice of toml-test, as listed in that project's
# `tests/files-toml-1.0.0`. Pinned here as numbers so that deleting an
# inconvenient case cannot quietly pass: the counts are inside the root.
EXPECT_VALID = 208
EXPECT_INVALID = 501

# toml-test tags every scalar as {"type": T, "value": "<text>"}. Tables are
# plain JSON objects and arrays are plain JSON arrays, so these eight tags are
# the whole vocabulary of leaves.
TAGS = frozenset(
    {
        "string",
        "integer",
        "float",
        "bool",
        "datetime",
        "datetime-local",
        "date-local",
        "time-local",
    }
)

# A proper refusal, and NOTHING else:
#   * TOMLDecodeError   -- the parser's declared "these bytes are not TOML".
#   * UnicodeDecodeError -- raised by the parser's own bytes->str step on the
#     nine fixtures that are not valid UTF-8. TOML 1.0.0 mandates UTF-8, so
#     rejecting the bytes IS the correct verdict for those, and the rejection
#     still comes from the parser, not from this harness.
# Every other exception is a CRASH, not a refusal, and is counted as a
# failure -- RecursionError, SystemError, MemoryError, AttributeError and
# friends are all `Exception` subclasses, so the broad `except Exception`
# below catches them and reports them as failures. We never let a crash
# masquerade as a correct rejection.
REFUSALS = (tomli.TOMLDecodeError, UnicodeDecodeError)


# --------------------------------------------------------------------------
# reading the expectation
# --------------------------------------------------------------------------
def tagged(obj):
    """True if `obj` is a toml-test tagged scalar rather than a table.

    A table's values in the expectation are always themselves tagged objects
    or containers, never bare strings, so requiring a string `value` and a
    known `type` distinguishes the two with no ambiguity. (The corpus does
    contain a table with a literal `type` key: valid/spec-1.0.0/inline-table-2.)
    """
    return (
        isinstance(obj, dict)
        and len(obj) == 2
        and isinstance(obj.get("type"), str)
        and obj["type"] in TAGS
        and isinstance(obj.get("value"), str)
    )


_DATETIME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[Tt ]"
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d+))?"
    r"(?P<offset>[Zz]|[+-]\d{2}:\d{2})?$"
)
_TIME = re.compile(r"^(?P<time>\d{2}:\d{2}:\d{2})(?:\.(?P<frac>\d+))?$")


def _micros(frac):
    """TOML: precision beyond what the implementation supports is TRUNCATED,
    not rounded (spec, Offset Date-Time). Python carries microseconds, so the
    expectation is truncated to six digits before it is compared."""
    return "" if frac is None else "." + frac.ljust(6, "0")[:6]


def want_datetime(text):
    """The expected date-time, as a value. `Z` and `+00:00` become the same
    tzinfo, and two aware datetimes then compare as instants, so an offset
    rewritten by the parser is not a difference."""
    m = _DATETIME.match(text)
    if not m:
        raise ValueError(f"unparsable expectation {text!r}")
    iso = m["date"] + "T" + m["time"] + _micros(m["frac"])
    off = m["offset"]
    if off:
        iso += "+00:00" if off in "Zz" else off
    return datetime.datetime.fromisoformat(iso)


def want_time(text):
    m = _TIME.match(text)
    if not m:
        raise ValueError(f"unparsable expectation {text!r}")
    return datetime.time.fromisoformat(m["time"] + _micros(m["frac"]))


# --------------------------------------------------------------------------
# semantic comparison
# --------------------------------------------------------------------------
def brief(value):
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def diff_scalar(tag, text, got, at):
    """Compare one tagged scalar against a parsed value. Returns a complaint
    or None. The Python type must match the tag exactly -- `type(x) is int`
    rather than isinstance, so a bool cannot pass as an integer and a datetime
    cannot pass as a date."""
    if tag == "string":
        if type(got) is not str:
            return f"{at}: want string, got {type(got).__name__} {brief(got)}"
        return None if got == text else f"{at}: want {text!r}, got {got!r}"

    if tag == "integer":
        if type(got) is not int:
            return f"{at}: want integer, got {type(got).__name__} {brief(got)}"
        want = int(text)
        return None if got == want else f"{at}: want {want}, got {got}"

    if tag == "float":
        if type(got) is not float:
            return f"{at}: want float, got {type(got).__name__} {brief(got)}"
        want = float(text)  # handles inf, -inf, +inf, nan
        if math.isnan(want):
            # toml-test erases the sign of NaN, so any NaN answers any NaN.
            return None if math.isnan(got) else f"{at}: want nan, got {got!r}"
        if math.isnan(got):
            return f"{at}: want {want!r}, got nan"
        # `==` on floats: -0.0 equals 0.0, which is exactly how toml-test
        # itself normalizes signed zero.
        return None if got == want else f"{at}: want {want!r}, got {got!r}"

    if tag == "bool":
        if type(got) is not bool:
            return f"{at}: want bool, got {type(got).__name__} {brief(got)}"
        want = {"true": True, "false": False}[text]
        return None if got is want else f"{at}: want {want}, got {got}"

    if tag in ("datetime", "datetime-local"):
        if type(got) is not datetime.datetime:
            return f"{at}: want {tag}, got {type(got).__name__} {brief(got)}"
        aware = tag == "datetime"
        if aware and got.tzinfo is None:
            return f"{at}: want an offset date-time, got a local one: {got!r}"
        if not aware and got.tzinfo is not None:
            return f"{at}: want a local date-time, got an offset one: {got!r}"
        want = want_datetime(text)
        # aware == aware compares instants, so Z and +00:00 agree.
        return None if got == want else f"{at}: want {want!r}, got {got!r}"

    if tag == "date-local":
        if type(got) is not datetime.date:
            return f"{at}: want date-local, got {type(got).__name__} {brief(got)}"
        want = datetime.date.fromisoformat(text)
        return None if got == want else f"{at}: want {want!r}, got {got!r}"

    if tag == "time-local":
        if type(got) is not datetime.time:
            return f"{at}: want time-local, got {type(got).__name__} {brief(got)}"
        if got.tzinfo is not None:
            return f"{at}: want a local time, got an offset one: {got!r}"
        want = want_time(text)
        return None if got == want else f"{at}: want {want!r}, got {got!r}"

    raise ValueError(f"unknown toml-test tag {tag!r} at {at}")


def diff(exp, got, at="$"):
    """First difference between the expectation and the parsed document, or
    None. Key ORDER is never a difference: tables are compared as sets of
    keys and then key by key in sorted order."""
    if tagged(exp):
        return diff_scalar(exp["type"], exp["value"], got, at)

    if isinstance(exp, dict):
        if type(got) is not dict:
            return f"{at}: want a table, got {type(got).__name__} {brief(got)}"
        missing = sorted(set(exp) - set(got))
        extra = sorted(set(got) - set(exp))
        if missing:
            return f"{at}: missing key(s) {missing}"
        if extra:
            return f"{at}: unexpected key(s) {extra}"
        for key in sorted(exp):
            complaint = diff(exp[key], got[key], f"{at}.{key}")
            if complaint:
                return complaint
        return None

    if isinstance(exp, list):
        if type(got) is not list:
            return f"{at}: want an array, got {type(got).__name__} {brief(got)}"
        if len(got) != len(exp):
            return f"{at}: want {len(exp)} element(s), got {len(got)}"
        for i, (e, g) in enumerate(zip(exp, got)):
            complaint = diff(e, g, f"{at}[{i}]")
            if complaint:
                return complaint
        return None

    raise ValueError(f"malformed expectation at {at}: {brief(exp)}")


# --------------------------------------------------------------------------
# the corpus
# --------------------------------------------------------------------------
def collect(kind):
    found = []
    base = os.path.join(CASES, kind)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".toml"):
                found.append(os.path.relpath(os.path.join(dirpath, name), CASES))
    return sorted(found)


def group_of(rel):
    return os.path.dirname(rel).replace(os.sep, "/")


def run():
    valid = collect("valid")
    invalid = collect("invalid")
    if len(valid) != EXPECT_VALID or len(invalid) != EXPECT_INVALID:
        sys.exit(
            f"REFUSED: corpus is not the pinned TOML 1.0.0 set -- found "
            f"{len(valid)} valid / {len(invalid)} invalid, "
            f"expected {EXPECT_VALID} / {EXPECT_INVALID}"
        )

    print(f"parser under claim: tomli/ (version {getattr(tomli, '__version__', 'unknown')})")
    print(f"corpus: {len(valid)} valid + {len(invalid)} invalid = {len(valid) + len(invalid)} cases")
    print()

    failures = []
    tally = {}

    for rel in valid:
        group = group_of(rel)
        tally.setdefault(group, [0, 0])
        tally[group][1] += 1
        toml_path = os.path.join(CASES, rel)
        json_path = toml_path[: -len(".toml")] + ".json"
        try:
            with open(json_path, "rb") as f:
                expectation = json.loads(f.read().decode("utf-8"))
        except OSError as e:
            failures.append(f"{rel}: expectation unreadable ({e})")
            continue
        with open(toml_path, "rb") as f:
            raw = f.read()
        try:
            document = tomli.load(io.BytesIO(raw))
        except Exception as e:
            failures.append(f"{rel}: valid document rejected -- {type(e).__name__}: {e}")
            continue
        try:
            complaint = diff(expectation, document)
        except ValueError as e:
            failures.append(f"{rel}: {e}")
            continue
        if complaint:
            failures.append(f"{rel}: {complaint}")
        else:
            tally[group][0] += 1

    for rel in invalid:
        group = group_of(rel)
        tally.setdefault(group, [0, 0])
        tally[group][1] += 1
        with open(os.path.join(CASES, rel), "rb") as f:
            raw = f.read()
        try:
            document = tomli.load(io.BytesIO(raw))
        except REFUSALS:
            tally[group][0] += 1  # a declared refusal: correct
        except Exception as e:
            # A crash is not a refusal. RecursionError, SystemError,
            # MemoryError and anything else land here and FAIL.
            failures.append(f"{rel}: crashed instead of refusing -- {type(e).__name__}: {e}")
        else:
            failures.append(f"{rel}: accepted an invalid document -- parsed to {brief(document)}")

    width = max(len(g) for g in tally)
    for group in sorted(tally):
        passed, total = tally[group]
        mark = "ok  " if passed == total else "FAIL"
        print(f"  {mark} {group:<{width}}  {passed:>3}/{total}")
    print()

    total = len(valid) + len(invalid)
    if failures:
        print(f"{len(failures)} of {total} cases failed; first {min(10, len(failures))}:")
        for line in failures[:10]:
            print(f"  - {line}")
        print(f"\ntoml-FAIL {total - len(failures)}/{total} TOML 1.0.0 cases")
        return 1

    print(f"toml-ok {total}/{total} TOML 1.0.0 cases ({len(valid)} valid, {len(invalid)} invalid)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
