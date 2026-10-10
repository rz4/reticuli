"""Turn a checked session trace into a cold-certified claim."""
import json
import os
import re
import shutil
import tempfile

from . import kernel, pack
from ._util import safe_path

TRACE = ".reticuli/draft.jsonl"


def _events(directory):
    try:
        with open(os.path.join(directory, TRACE), encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read session trace: {exc}") from exc


def _exact_file(directory, name):
    try:
        safe_path(directory, name)
    except kernel.ClaimError:
        return False
    current = directory
    for part in name.split("/"):
        if not os.path.isdir(current) or part not in os.listdir(current):
            return False
        current = os.path.join(current, part)
    return os.path.isfile(current)


def _declared(directory, events, outputs, claim, generated):
    written = [e["path"] for e in events if e.get("event") == "write" and isinstance(e.get("path"), str)]
    reads = [e["path"] for e in events if e.get("event") == "read" and isinstance(e.get("path"), str)]
    commands = " ".join(e.get("cmd", "") for e in events if e.get("event") == "bash")
    tokens = re.findall(r"[A-Za-z0-9_./-]+", commands)
    names = list(dict.fromkeys(written + reads + tokens + list(claim or []) + list(generated or [])))
    for name in written + reads + list(claim or []) + list(generated or []):
        safe_path(directory, name)
    pins = list(dict.fromkeys(claim or []))
    made = list(dict.fromkeys(written + list(generated or [])))
    made = [x for x in made if x not in pins and x not in outputs and _exact_file(directory, x)]
    pins += [x for x in reads + tokens if x not in pins and x not in made
             and x not in outputs and _exact_file(directory, x)]
    pins = [x for x in pins if _exact_file(directory, x)]
    return pins, made


def propose(directory, outputs, name=None, *, claim=None, generated=None):
    events = _events(directory)
    gates = [e["cmd"] for e in events if e.get("event") == "bash" and e.get("cmd")]
    if not gates:
        raise kernel.ClaimError("no checked command in session")
    pins, made = _declared(directory, events, outputs, claim, generated)
    return {"claim": {"name": name or os.path.basename(os.path.abspath(directory)),
                      "format": 3, "inputs": pins},
            "generated": made, "gate": gates[-1], "outputs": list(outputs),
            "events": events}


def build_claim(directory, outputs, into, *, name=None, claim=None, generated=None):
    draft = propose(directory, outputs, name, claim=claim, generated=generated)
    if len(outputs) != 1:
        raise kernel.ClaimError("one verdict output required")
    gate_output = outputs[0]
    safe_path(directory, gate_output)
    expected = kernel._hash_file(os.path.join(directory, gate_output))
    with tempfile.TemporaryDirectory(prefix="reticuli-cold-") as room:
        for item in draft["claim"]["inputs"] + draft["generated"]:
            source = os.path.join(directory, item)
            target = os.path.join(room, item)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
        # The cold room contains exactly the declared files; a session's
        # existing verdict and undeclared residue have no authority.
        cold = kernel.run_gate(draft["gate"], room)
        if cold["status"] != "ok" or kernel._hash_file(os.path.join(room, gate_output)) != expected:
            raise kernel.ClaimError("cold gate did not re-earn the verdict")
    if os.path.exists(into):
        shutil.rmtree(into)
    os.makedirs(into)
    for item in draft["claim"]["inputs"] + draft["generated"]:
        target = os.path.join(into, item)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(directory, item), target)
    result = pack.pack(into, draft["claim"]["name"], draft["generated"],
                       draft["claim"]["inputs"], draft["gate"], gate_output)
    prompts = [e for e in draft["events"] if e.get("event") == "prompt"]
    timestamps = [e["ts"] for e in draft["events"] if type(e.get("ts")) in (int, float)]
    span = max(timestamps) - min(timestamps) if timestamps else 0
    kernel.ledger(into, {"event": "oracle", "calls": len(prompts), "seconds": span})
    return result
