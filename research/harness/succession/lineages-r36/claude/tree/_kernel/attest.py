"""The record: the one file this project promises other programs may parse.

A record states what one machine established about one claim at one time.
Its canonical form is the identity serialization verbatim -- sorted keys,
default separators, non-ASCII escaped, UTF-8 -- so a record travels between
implementations, and its digest is the sha256 of exactly those bytes.

Two rules are easy to get wrong and both are load-bearing. A reader does NOT
normalise numeric form: `{"usd": 1}` and `{"usd": 1.0}` are different
records with different digests, because a digest names bytes and a file must
hold its own canonical bytes. And validation is a PRECONDITION of the
format, not a service of one function: every entry point that consumes a
document refuses what a reader refuses, canonicalizing and digesting
included -- a digest is how a record is cited, so an implementation that
will digest a non-record manufactures a citable value standing for something
this format does not admit.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess

from .core import (COST_KEYS, ClaimError, NAMESPACE, SIGN_NAMESPACE, _finite,
                   _now)

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 2

#: the members every version carries. `claim` is version 2's addition and
#: is held separately, because the member set is closed PER VERSION: it is
#: refused at version 1 and required at version 2.
_RECORD_MEMBERS = frozenset({"record", "name", "root", "build_digest",
                             "gates", "cost", "producer", "environment",
                             "when", "tool"})
_RECORD_REQUIRED = frozenset({"record", "name", "root", "build_digest",
                              "gates", "environment", "when"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch",
                              "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap",
                               "inherited"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_OBLIGATIONS = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _hex(value, what: str) -> None:
    if not isinstance(value, str) or not _RECORD_HEX.match(value):
        raise ClaimError(f"a record's {what} must be 64 lowercase hex "
                         f"characters, not {value!r}")


def _cost_table(table, what: str) -> None:
    if not isinstance(table, dict):
        raise ClaimError(f"a record's {what} must be an object")
    for unit, value in table.items():
        if unit not in COST_KEYS:
            raise ClaimError(f"a record's {what} names an unknown unit: "
                             f"{unit!r}")
        if not _finite(value) or value < 0:
            raise ClaimError(
                f"a record's {what} {unit} must be a finite, non-negative "
                f"number -- a cost is a measurement of work done, and "
                f"neither NaN nor an infinity reports any: {value!r}")


def record_validate(doc) -> dict:
    """Refuse, in band and with a reason, anything that is not a record."""
    if not isinstance(doc, dict):
        raise ClaimError("a record is a JSON object")
    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ClaimError("a record's `record` member is an integer version")
    if version > RECORD_FORMAT:
        raise ClaimError(
            f"record version {version} is newer than this reader understands "
            f"(version {RECORD_FORMAT}); upgrade reticuli to read it")
    if version < 1:
        raise ClaimError(f"record version {version} is not a version")
    allowed = _RECORD_MEMBERS | ({"claim"} if version >= 2 else set())
    unknown = set(doc) - allowed
    if unknown:
        raise ClaimError(
            f"a record's member set is closed: {sorted(unknown)} is not part "
            f"of this format (extension is a version bump)")
    missing = _RECORD_REQUIRED - set(doc)
    if missing:
        raise ClaimError(f"a record is missing {sorted(missing)}")
    if version >= 2 and "claim" not in doc:
        raise ClaimError(
            "a version-2 record carries the claim's declared obligations; "
            "`{}` states positively that the recipe declares none")
    if version < 2 and "claim" in doc:
        raise ClaimError(
            "a version-1 record never carried `claim`: the member set is "
            "closed per version")

    if not isinstance(doc["name"], str) or not doc["name"]:
        raise ClaimError("a record's name must be a string")
    _hex(doc["root"], "root")
    _hex(doc["build_digest"], "build_digest")
    if not isinstance(doc["when"], str) or not _RECORD_WHEN.match(doc["when"]):
        raise ClaimError(f"a record's when must be YYYY-MM-DDTHH:MM:SSZ, "
                         f"not {doc['when']!r}")
    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("a record's tool must be a string")

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise ClaimError("a record's gates must be an array")
    for entry in gates:
        if not isinstance(entry, dict):
            raise ClaimError("every gate entry is an object")
        extra = set(entry) - _RECORD_GATE
        if extra:
            raise ClaimError(
                f"a gate entry carries only {sorted(_RECORD_GATE)}; "
                f"{sorted(extra)} is outside the document -- per-gate "
                f"wall-clock is deliberately not a member")
        if set(entry) != _RECORD_GATE:
            raise ClaimError(f"a gate entry needs "
                             f"{sorted(_RECORD_GATE - set(entry))}")
        if not isinstance(entry["output"], str):
            raise ClaimError("a gate's output is a string")
        if entry["status"] not in _RECORD_STATUSES:
            raise ClaimError(f"unknown gate status {entry['status']!r} "
                             f"(the vocabulary is closed)")
        if entry["sandbox"] not in _RECORD_SANDBOXES:
            raise ClaimError(f"unknown sandbox {entry['sandbox']!r} "
                             f"(the vocabulary is closed)")

    environment = doc["environment"]
    if not isinstance(environment, dict) or \
            set(environment) != _RECORD_ENVIRONMENT or \
            any(not isinstance(v, str) for v in environment.values()):
        raise ClaimError(f"a record's environment carries exactly "
                         f"{sorted(_RECORD_ENVIRONMENT)} as strings")

    if "cost" in doc:
        _cost_table(doc["cost"], "cost")
    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict):
            raise ClaimError("a record's producer must be an object")
        extra = set(producer) - _RECORD_PRODUCER
        if extra:
            raise ClaimError(f"a record's producer names "
                             f"{sorted(extra)}, which this format does not")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise ClaimError(f"producer.{key} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise ClaimError("producer.blind must be a boolean")
    if "claim" in doc:
        obligations = doc["claim"]
        if not isinstance(obligations, dict):
            raise ClaimError("a record's claim must be an object")
        extra = set(obligations) - _RECORD_OBLIGATIONS
        if extra:
            raise ClaimError(
                f"a record's claim carries only the three obligations "
                f"{sorted(_RECORD_OBLIGATIONS)}; not {sorted(extra)}")
        for key in ("tolerance", "mutation_floor"):
            if key in obligations:
                value = obligations[key]
                if not _finite(value) or value < 0:
                    raise ClaimError(f"a record's claim {key} must be a "
                                     f"finite, non-negative number, not "
                                     f"{value!r}")
        if "envelope" in obligations:
            envelope = obligations["envelope"]
            if not isinstance(envelope, dict) or not envelope:
                raise ClaimError("a record's declared envelope must be a "
                                 "non-empty object of ceilings")
            for unit, ceiling in envelope.items():
                if unit not in COST_KEYS:
                    raise ClaimError(f"a declared envelope names an unknown "
                                     f"unit: {unit!r}")
                if not _finite(ceiling) or ceiling <= 0:
                    raise ClaimError(
                        f"a declared envelope ceiling must be a finite "
                        f"positive number: {unit} = {ceiling!r}")
    return doc


def record_canonical(doc) -> bytes:
    """The bytes a signature covers. Validation first, always."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """How a record is CITED: the sha256 of its canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    """Read a record file, and hold it to being its own canonical bytes."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ClaimError(f"no record at {path}: {exc}") from None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaimError(f"{path} is not a JSON record: {exc}") from None
    record_validate(doc)
    if raw != json.dumps(doc, sort_keys=True).encode("utf-8"):
        raise ClaimError(
            f"{path} does not hold its own canonical bytes: a record file is "
            f"its canonical serialization or it is not a record")
    return doc


def _signers_principals(anchor: str) -> list:
    names = []
    try:
        with open(anchor, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                names.append(line.split()[0])
    except OSError:
        return []
    return names


def record_signer(path: str, anchor: str | None = None):
    """Who signed this record, as named by the VERIFIER's own anchor.

    A record's signature means something only against a key in the
    verifier's `allowed_signers`. Trust is verifier-relative, everywhere.
    """
    if not anchor or not os.path.isfile(anchor) or \
            not shutil.which("ssh-keygen"):
        return None
    signature = path + ".sig"
    if not os.path.isfile(signature):
        return None
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    for principal in _signers_principals(anchor):
        try:
            done = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", principal,
                 "-n", RECORD_NAMESPACE, "-s", signature],
                input=data, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0:
            return principal
    return None
