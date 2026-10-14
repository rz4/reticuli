"""Drive one population member in a subprocess and record what it did.

A member is a package tree implementing the kernel surface. Members cannot be
imported into one process -- several of them are packages named `tree` -- so
each observation runs a small driver under the member's own import path.

The OUTCOME is what the member did: a value, or an in-band refusal. The
EQUIVALENCE used to class members deliberately ignores refusal message text.
The specification requires a reader to refuse "in band and with a reason";
it does not fix the sentence, so two members refusing the same input with
different wording agree for classing purposes and the wording is reported
separately as a note.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

DRIVER = r'''
import importlib, json, os, sys
request = json.loads(sys.stdin.readline())
# Put the member's own tree first. PYTHONPATH is not used: the driver runs
# isolated, which discards it, and an editable install of the authored
# package would otherwise answer for a reconstruction's probe.
sys.path.insert(0, request["path"])
try:
    module = importlib.import_module(request["package"] + ".kernel")
    # Containment, not string prefix. `lineages-r2` is a prefix of
    # `lineages-r24` and both exist, so prefix matching would let one
    # member's tree answer for another's probe.
    origin = os.path.realpath(getattr(module, "__file__", "") or "")
    tree = os.path.realpath(request["path"])
    if not origin.startswith(tree.rstrip(os.sep) + os.sep):
        print(json.dumps({"kind": "misresolved", "error_type": "WrongImport",
                          "error_message": f"{request['package']} resolved to {origin}"}))
        raise SystemExit(0)
except Exception as exc:
    print(json.dumps({"kind": "unavailable", "error_type": type(exc).__name__,
                      "error_message": str(exc)[:400]}))
    raise SystemExit(0)
try:
    function = getattr(module, request["call"])
except AttributeError as exc:
    print(json.dumps({"kind": "absent", "error_type": "AttributeError",
                      "error_message": str(exc)[:400]}))
    raise SystemExit(0)
try:
    result = function(*request["args"])
except BaseException as exc:
    print(json.dumps({"kind": "refused", "error_type": type(exc).__name__,
                      "error_message": str(exc)[:400]}))
    raise SystemExit(0)
if isinstance(result, bytes):
    shown = {"bytes": result.decode("utf-8", "backslashreplace")}
elif isinstance(result, (str, int, float, bool)) or result is None:
    shown = {"plain": result}
else:
    try:
        shown = {"json": json.loads(json.dumps(result, sort_keys=True, default=repr))}
    except Exception:
        shown = {"repr": repr(result)[:4000]}
print(json.dumps({"kind": "value", "value": shown}, sort_keys=True))
'''

TIMEOUT = 20.0


def observe(member, call, args):
    """Run one call against one member. Never raises on member misbehaviour."""
    request = {"package": member["package"], "call": call, "args": args,
               "path": str(Path(member["path"]).resolve())}
    env = {"PATH": os.defpath, "PYTHONHASHSEED": "0",
           "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1"}
    try:
        done = subprocess.run([sys.executable, "-I", "-c", DRIVER],
                              input=json.dumps(request) + "\n", text=True,
                              capture_output=True, timeout=TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return {"kind": "timeout", "error_type": "Timeout",
                "error_message": f"member exceeded {TIMEOUT:g}s"}
    line = done.stdout.strip().splitlines()
    if not line:
        return {"kind": "crashed", "error_type": "NoOutput",
                "error_message": (done.stderr or "")[-400:]}
    try:
        return json.loads(line[-1])
    except ValueError:
        return {"kind": "crashed", "error_type": "BadOutput",
                "error_message": line[-1][:400]}


def behaviour_key(outcome):
    """The equivalence a split is computed over. Refusal wording is excluded."""
    if outcome["kind"] == "value":
        payload = {"kind": "value", "value": outcome["value"]}
    else:
        # Every non-value outcome is "this member did not return a result".
        # The exception class is kept because it distinguishes an in-band
        # refusal from a crash; the message is not, because no criterion
        # pins the sentence.
        payload = {"kind": outcome["kind"], "error_type": outcome["error_type"]}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()
