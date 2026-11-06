"""The record: the one file this project promises other programs may parse.

A record states what ONE machine established about ONE claim at ONE time —
the identity it recomputed, the implementation bytes it found, the gate
results it obtained by running them, and the production cost where one was
measured (`spec/record.md`).  The kernel owns the FORMAT; authoring a record
belongs to the exchange layer.

Three properties are the whole contract.  The canonical form is the identity
serialization verbatim, so one document has one digest under every wrapper.
The member set is CLOSED per version — extension is a version bump, not a
quiet extra field under an old number.  And validation is a precondition of
the format rather than a service of one function: every entry point refuses
what a reader refuses, canonicalizing and digesting included, because a
digest is how a record is CITED and an implementation that will digest a
non-record manufactures a well-formed citable value standing for something
this format does not admit.

Numbers are carried VERBATIM.  A reader does not normalise numeric form, so
`{"usd": 1}` and `{"usd": 1.0}` are different records with different digests
— and that is what lets a file hold its own canonical bytes.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess

from .core import (COST_KEYS, RECORD_FORMAT, RECORD_NAMESPACE, ClaimError,
                   _ENV_SIGNERS, _finite)

#: The members every version admits.  `claim` is version-2-only and is
#: handled beside this set: the member set is closed PER VERSION, so a
#: version-1 document carrying it is refused rather than tolerated.
_RECORD_MEMBERS = frozenset({"record", "name", "root", "build_digest",
                             "gates", "cost", "producer", "environment",
                             "when", "tool"})
_RECORD_REQUIRED = frozenset({"record", "name", "root", "build_digest",
                              "gates", "environment", "when"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch",
                              "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_OBLIGATIONS = frozenset({"tolerance", "envelope", "mutation_floor"})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _refuse(reason: str):
    raise ClaimError(f"not a record: {reason}")


def record_validate(doc) -> dict:
    """Refuse, in band and with a reason, anything this format does not admit."""
    if not isinstance(doc, dict):
        _refuse(f"a record is a JSON object, not {type(doc).__name__}")
    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int):
        _refuse("the `record` member must be an integer format version")
    if version < 1:
        _refuse(f"record version {version} is not a version")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this reader "
                f"understands (version {RECORD_FORMAT})")
    admitted = set(_RECORD_MEMBERS)
    if version >= 2:
        admitted.add("claim")
    unknown = set(doc) - admitted
    if unknown:
        _refuse(f"the member set is closed; this document carries "
                f"{', '.join(sorted(unknown))}")
    required = set(_RECORD_REQUIRED)
    if version >= 2:
        required.add("claim")
    absent = required - set(doc)
    if absent:
        _refuse(f"missing required member(s) {', '.join(sorted(absent))} "
                f"at version {version}")
    if version < 2 and "claim" in doc:
        _refuse("`claim` carries the declared obligations and does not exist "
                "at version 1; a version-1 record cannot make that statement")

    if not isinstance(doc.get("name"), str) or not doc["name"]:
        _refuse("`name` must be the claim's name, as a string")
    for key in ("root", "build_digest"):
        if not isinstance(doc.get(key), str) or not _RECORD_HEX.match(doc[key]):
            _refuse(f"`{key}` must be 64 lowercase hex characters")
    if not isinstance(doc.get("when"), str) or not _RECORD_WHEN.match(doc["when"]):
        _refuse("`when` must be a UTC time, YYYY-MM-DDTHH:MM:SSZ")
    if "tool" in doc and not isinstance(doc["tool"], str):
        _refuse("`tool` is a string, and diagnostic only")

    gates = doc.get("gates")
    if not isinstance(gates, list):
        _refuse("`gates` is an array, one entry per gate step")
    for entry in gates:
        if not isinstance(entry, dict):
            _refuse("every `gates` entry is an object")
        extra = set(entry) - _RECORD_GATE
        if extra:
            _refuse(f"a gate entry carries {', '.join(sorted(extra))}; "
                    f"per-gate wall-clock is deliberately outside the "
                    f"document")
        if not isinstance(entry.get("output"), str):
            _refuse("a gate entry names the output it pins")
        if entry.get("status") not in _RECORD_STATUSES:
            _refuse(f"the gate status {entry.get('status')!r} is outside the "
                    f"audit vocabulary ({', '.join(sorted(_RECORD_STATUSES))})")
        if entry.get("sandbox") not in _RECORD_SANDBOXES:
            _refuse(f"the sandbox {entry.get('sandbox')!r} is outside the "
                    f"vocabulary ({', '.join(sorted(_RECORD_SANDBOXES))})")

    environment = doc.get("environment")
    if not isinstance(environment, dict) or \
            set(environment) != _RECORD_ENVIRONMENT:
        _refuse(f"`environment` carries exactly "
                f"{', '.join(sorted(_RECORD_ENVIRONMENT))}")
    for key, value in environment.items():
        if not isinstance(value, str):
            _refuse(f"`environment.{key}` is a string")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict):
            _refuse("`cost` is an object of measured totals")
        for unit, value in cost.items():
            if unit not in COST_KEYS:
                _refuse(f"`cost` names the unknown unit {unit!r}")
            if not _finite(value) or value < 0:
                _refuse(f"`cost.{unit}` = {value!r} is not a finite, "
                        f"non-negative measurement; neither NaN nor an "
                        f"infinity reports any work done")
    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict):
            _refuse("`producer` is an object of declarations")
        extra = set(producer) - _RECORD_PRODUCER
        if extra:
            _refuse(f"`producer` carries {', '.join(sorted(extra))}")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            _refuse("`producer.blind` is a boolean")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                _refuse(f"`producer.{key}` is a string")
    if "claim" in doc:
        obligations = doc["claim"]
        if not isinstance(obligations, dict):
            _refuse("`claim` relays the recipe's declared obligations")
        extra = set(obligations) - _RECORD_OBLIGATIONS
        if extra:
            _refuse(f"`claim` names the unknown obligation(s) "
                    f"{', '.join(sorted(extra))}")
        for key in ("tolerance", "mutation_floor"):
            if key in obligations:
                value = obligations[key]
                if not _finite(value) or value < 0:
                    _refuse(f"`claim.{key}` = {value!r} is not a finite, "
                            f"non-negative number")
        if "envelope" in obligations:
            envelope = obligations["envelope"]
            if not isinstance(envelope, dict) or not envelope:
                _refuse("`claim.envelope` is a non-empty table of ceilings")
            for unit, ceiling in envelope.items():
                if unit not in COST_KEYS:
                    _refuse(f"`claim.envelope` names the unknown unit "
                            f"{unit!r}")
                if not _finite(ceiling) or ceiling <= 0:
                    _refuse(f"`claim.envelope.{unit}` = {ceiling!r} is not a "
                            f"finite positive ceiling")
    return doc


def record_canonical(doc) -> bytes:
    """The record's canonical bytes — sorted keys, default separators, UTF-8.

    Validation first: reading the canonical bytes of a document nobody has
    validated is reading the preimage of a value that stands for nothing.
    """
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """The lowercase hex sha256 of the canonical bytes — how a record is cited."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    """Read a record file, which must hold exactly its own canonical bytes.

    A reformatted document is not a record: a signature signs bytes, and a
    signature over facts-rather-than-bytes would be forgeable by
    reformatting.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ClaimError(f"{path}: {exc.strerror or exc}") from None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ClaimError(f"{path}: not readable as JSON ({exc})") from None
    record_validate(doc)
    if raw.rstrip(b"\n") != json.dumps(doc, sort_keys=True).encode("utf-8"):
        raise ClaimError(
            f"{path}: the file is its canonical bytes or it is not a record")
    return doc


def record_signer(path: str, anchor: str = None):
    """Who signed this record, as the verifier's own anchor sees it.

    A record signature says "these are the results I obtained"; it is made
    in the record's own namespace so it can never be presented as an
    authorization.  A record from a key you have not anchored is a document,
    not evidence.
    """
    signers = anchor or os.environ.get(_ENV_SIGNERS)
    if not signers or not os.path.isfile(signers):
        return None
    if not shutil.which("ssh-keygen") or not os.path.isfile(path + ".sig"):
        return None
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
        with open(signers, encoding="utf-8") as handle:
            principals = [line.split()[0] for line in handle
                          if line.strip() and not line.startswith("#")]
    except (OSError, UnicodeDecodeError, IndexError):
        return None
    for identity in principals:
        try:
            done = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", identity,
                 "-n", RECORD_NAMESPACE, "-s", path + ".sig"],
                input=payload, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode == 0:
            return identity
    return None
