import json
import hashlib
import re
from typing import Any, Dict

from reticuli._kernel.core import ClaimError

_RECORD_ENVIRONMENT = frozenset({'platform', 'runtime', 'machine'})
_RECORD_GATE = frozenset({'status', 'sandbox', 'output'})
_RECORD_MEMBERS = frozenset({'when', 'cost', 'gates', 'producer', 'environment', 'name', 'root', 'record', 'build_digest', 'tool'})
_RECORD_PRODUCER = frozenset({'blind', 'model', 'cutoff', 'vendor'})
_RECORD_REQUIRED = frozenset({'build_digest', 'when', 'environment', 'record', 'name', 'root', 'gates'})
_RECORD_SANDBOXES = frozenset({'none', 'seatbelt', 'inherited', 'bubblewrap'})
_RECORD_STATUSES = frozenset({'timeout', 'ok', 'environment', 'failed', 'mismatch'})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_RECORD_CUTOFF = re.compile(r"^\d{4}-\d{2}$")

def record_validate(doc: Any) -> None:
    if not isinstance(doc, dict):
        raise ClaimError("record must be a dict")
    
    version = doc.get("record")
    if version not in (1, 2):
        raise ClaimError(f"unsupported record version {version}")

    if version == 1:
        allowed = _RECORD_MEMBERS
        required = _RECORD_REQUIRED
    else:
        allowed = _RECORD_MEMBERS | {"claim"}
        required = _RECORD_REQUIRED | {"claim"}

    for k in required:
        if k not in doc:
            raise ClaimError(f"missing required member {k}")
            
    for k in doc:
        if k not in allowed:
            raise ClaimError(f"unknown member {k}")

    if not isinstance(doc["root"], str) or not _RECORD_HEX.match(doc["root"]):
        raise ClaimError("invalid root")
    if not isinstance(doc["build_digest"], str) or not _RECORD_HEX.match(doc["build_digest"]):
        raise ClaimError("invalid build_digest")
        
    if not isinstance(doc["when"], str) or not _RECORD_WHEN.match(doc["when"]):
        raise ClaimError("invalid when")
        
    env = doc["environment"]
    if not isinstance(env, dict) or set(env.keys()) != _RECORD_ENVIRONMENT:
        raise ClaimError("invalid environment")
    for v in env.values():
        if not isinstance(v, str):
            raise ClaimError("invalid environment value")
            
    gates = doc["gates"]
    if not isinstance(gates, list):
        raise ClaimError("invalid gates")
    for g in gates:
        if not isinstance(g, dict) or set(g.keys()) != _RECORD_GATE:
            raise ClaimError("invalid gate")
        if not isinstance(g["output"], str):
            raise ClaimError("invalid gate output")
        if g["status"] not in _RECORD_STATUSES:
            raise ClaimError("invalid gate status")
        if g["sandbox"] not in _RECORD_SANDBOXES:
            raise ClaimError("invalid gate sandbox")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict):
            raise ClaimError("invalid cost")
        for k, v in cost.items():
            if k not in {"usd", "tokens", "calls", "seconds"}:
                raise ClaimError("invalid cost key")
            if isinstance(v, bool):
                raise ClaimError("cost cannot be boolean")
            if not isinstance(v, (int, float)):
                raise ClaimError("cost must be number")
            if v < 0:
                raise ClaimError("cost cannot be negative")
            import math
            if math.isinf(v) or math.isnan(v):
                raise ClaimError("cost must be finite")

    if "producer" in doc:
        prod = doc["producer"]
        if not isinstance(prod, dict):
            raise ClaimError("invalid producer")
        for k in prod:
            if k not in _RECORD_PRODUCER:
                raise ClaimError("invalid producer key")
        if "blind" in prod and not isinstance(prod["blind"], bool):
            raise ClaimError("producer blind must be boolean")
        for k in ("vendor", "model", "cutoff"):
            if k in prod and not isinstance(prod[k], str):
                raise ClaimError(f"producer {k} must be string")
        if "cutoff" in prod and not _RECORD_CUTOFF.match(prod["cutoff"]):
             raise ClaimError("producer cutoff invalid format")

    if version == 2:
        claim = doc["claim"]
        if not isinstance(claim, dict):
            raise ClaimError("invalid claim block")
        for k, v in claim.items():
            if k not in {"tolerance", "envelope", "mutation_floor"}:
                raise ClaimError(f"invalid claim key {k}")
            if k in {"tolerance", "mutation_floor"}:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                    raise ClaimError(f"invalid claim {k}")
            if k == "envelope":
                if not isinstance(v, dict) or not v:
                    raise ClaimError("invalid envelope")
                for ek, ev in v.items():
                    if ek not in {"usd", "tokens", "calls", "seconds"}:
                        raise ClaimError("invalid envelope key")
                    if isinstance(ev, bool) or not isinstance(ev, (int, float)) or ev <= 0:
                        raise ClaimError("invalid envelope value")

def record_canonical(doc: Any) -> bytes:
    record_validate(doc)
    return json.dumps(doc, sort_keys=True, separators=(", ", ": "), ensure_ascii=True).encode("utf-8")

def record_digest(doc: Any) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()

def record_signer(doc: Any) -> str:
    pass

def record_read(path: str) -> Any:
    pass
