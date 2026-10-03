"""Audit: re-earning a claim's verdict cold (spec/verification.md, "Audit:
earned vs. carried").

`audit` is the only verb that re-earns a verdict: it trusts no stored
ledger entry and no manifest-recorded gate status. It confirms identity
still holds against the sealed manifest, builds a fresh room from the
claim's pinned inputs and its present (or freshly produced) generated
bytes, re-runs every gate inside it, and requires every pinned byte the
gate writes to reproduce exactly what the claim already holds. `_produce`
and `_materialize` build that room; `_step_guidance` reads a produce
step's hint for an external producer (spec/claim-format.md, "Producer
guidance versus criteria"); `_compare_pin` is the byte comparison behind
"reproduced" versus "mismatch"; `_read_usage` parses a producer's
self-reported cost; `_authorized`/`_ssh_verify` check a signed
authorization statement under `core.SIGN_NAMESPACE` before an external
producer's bytes are accepted, when the claim's store carries one.
"""
import json
import os
import shutil
import subprocess
import tempfile

from . import core
from . import recipe
from . import run
from . import seal
from .core import ClaimError


def _ssh_verify(data: bytes, signature_path: str, namespace: str, allowed_signers: str) -> bool:
    """Verify a detached `ssh-keygen -Y` signature over `data` in
    `namespace` against an `allowed_signers` file (spec/record.md: the
    signing mechanism every namespace in this tool shares). Returns
    `False` on any failure -- a missing binary, a missing signer, a bad
    signature -- rather than raising: authorization is advisory input to
    `_authorized`, never a crash.
    """
    if not shutil.which("ssh-keygen"):
        return False
    try:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", "producer",
             "-n", namespace, "-s", signature_path],
            input=data, capture_output=True, timeout=10, check=False,
        )
        return done.returncode == 0
    except OSError:
        return False


def _authorized(d: str, producer_id: str, allowed_signers=None) -> bool:
    """Whether `producer_id` (a "vendor/model" label) is authorized to
    produce for the claim at `d`: a signed statement under
    `core.SIGN_DIR`, in the `core.SIGN_NAMESPACE` ("reticuli.mint")
    signing purpose -- distinct from attestation and from a record
    (spec/record.md). With no `allowed_signers` to check against, or no
    signed statement on disk, authorization is not restricted: it is
    opt-in infrastructure, not a default gate on every producer.
    """
    sign_dir = os.path.join(d, core.SIGN_DIR)
    if allowed_signers is None or not os.path.isdir(sign_dir):
        return True
    statement_path = os.path.join(sign_dir, f"{producer_id}.sign.json")
    signature_path = statement_path + ".sig"
    if not (os.path.isfile(statement_path) and os.path.isfile(signature_path)):
        return False
    with open(statement_path, "rb") as f:
        data = f.read()
    return _ssh_verify(data, signature_path, core.SIGN_NAMESPACE, allowed_signers)


def _read_usage(payload) -> dict:
    """Parse a producer's self-reported usage: `usd`/`tokens`/`calls` only
    -- `seconds` is the kernel's own measurement and is never accepted
    from a usage payload (spec/kernel-api.md). Accepts a dict or a JSON
    string; anything else, or a non-numeric or negative value, is dropped
    rather than raised, since usage is self-reported testimony, not a
    trusted input.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return {}
    if not isinstance(payload, dict):
        return {}
    usage = {}
    for key in ("usd", "tokens", "calls"):
        value = payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            usage[key] = value
    return usage


def _step_guidance(step: dict):
    """A produce step's guidance string, reading both spellings
    (`guidance`, current; `request`, legacy --
    spec/claim-format.md, "Producer guidance versus criteria"). `None`
    when the step carries neither. Guidance is a hint for a producer,
    never a condition the gate enforces.
    """
    for key in core.GUIDANCE_KEYS:
        value = step.get(key)
        if value is not None:
            return value
    return None


def _produce(room: str, d: str, step: dict, producer=None) -> None:
    """Realize one produce step's output into `room`. With a `producer`
    callback, call it with the room, the output name, and this step's
    guidance, and let it write the file directly into `room` (guidance
    reaches a producer this way, never through the room's recipe --
    spec/identity.md, "Format 3"). With no producer, fall back to the
    bytes already present at that name in the original claim directory
    `d` -- the concrete realization audit is re-earning a verdict for. An
    output that exists nowhere is simply not realized; the gate that
    needs it will fail honestly.
    """
    output = step["output"]
    if producer is not None:
        producer(room, output, _step_guidance(step))
        return
    src = core._safe(d, output)
    if os.path.isfile(src):
        core._copy_into(d, room, [output])


def _materialize(d: str, parsed: dict, into: str, producer=None) -> None:
    """Build a fresh judging room at `into`: every pinned input copied in,
    then every produce step's output realized (spec/verification.md,
    "Audit: earned vs. carried" -- a cold room, nothing carried in but
    the claim's own declared and present bytes).
    """
    core._copy_into(d, into, recipe._inputs(parsed))
    for step in recipe.produces(parsed):
        _produce(into, d, step, producer)


def _compare_pin(room: str, d: str, output: str) -> bool:
    """Whether `output`'s bytes in the fresh room match its bytes in the
    original claim directory `d` -- the "every pinned byte reproduces"
    half of audit (spec/verification.md). Missing on either side is not a
    match: a pinned byte nobody can find has not reproduced.
    """
    room_path = core._safe(room, output)
    orig_path = core._safe(d, output)
    if not (os.path.isfile(room_path) and os.path.isfile(orig_path)):
        return False
    return core._hash_file(room_path) == core._hash_file(orig_path)


def audit(d: str, producer=None) -> dict:
    """Re-earn a claim's verdict cold (spec/verification.md, "Audit:
    earned vs. carried"). Identity must hold against the sealed manifest
    first -- a tampered pinned input fails here, before any gate runs.
    The environment contract (`[claim] requires`) must be met. Every gate
    then runs fresh in a sandboxed room built from the claim's pinned
    inputs and its present (or freshly produced) generated bytes, and the
    bytes it pins must reproduce exactly what the claim already holds.
    Nothing here trusts a stored ledger verdict.

    Returns `{"ok": bool, "gates": [...]}`, one entry per gate step in
    recipe order (`output`, `status` -- `reproduced`/`mismatch`/`failed`/
    `timeout` (spec/verification.md, "Failure classes") -- and `sandbox`,
    the confinement that actually applied). A refusal before any gate
    runs (identity mismatch, a missing `requires`) reports `ok: False`
    with an empty `gates` list and a `verdict` naming why.
    """
    try:
        vr = seal.verify(d)
    except ClaimError as exc:
        return {"ok": False, "verdict": str(exc), "gates": []}
    if not vr["ok"]:
        return {"ok": False, "verdict": "mismatch", "gates": []}

    parsed = recipe.load_recipe(d)

    missing = run.preflight(parsed)
    if missing:
        return {"ok": False, "verdict": "environment", "gates": [], "missing": missing}

    room = tempfile.mkdtemp(prefix="audit-")
    try:
        _materialize(d, parsed, room, producer)

        timeout = run.gate_timeout(parsed)
        gate_results = []
        ok = True
        for step in recipe.gates(parsed):
            outcome = run.run_gate(step["run"], room, timeout)
            output = step["output"]
            if outcome["status"] == "ok":
                status = "reproduced" if _compare_pin(room, d, output) else "mismatch"
            else:
                status = outcome["status"]
            if status != "reproduced":
                ok = False
            gate_results.append(
                {"output": output, "status": status, "sandbox": outcome["quarantine"]}
            )
        return {"ok": ok, "gates": gate_results}
    finally:
        shutil.rmtree(room, ignore_errors=True)
