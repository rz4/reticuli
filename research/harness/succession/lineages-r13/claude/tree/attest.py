"""Attestation: a keyholder's signed statement of a build, and the
signing ceremony over a chain (spec/layers.md's exchange layer).

`attest` signs only a claim whose verdicts reproduce from its own bytes
right now -- it runs a full audit first and refuses a carried verdict or
a broken claim, never notarizing either. `check` reports whether a stored
attestation still names the current build, or has drifted (regenerated,
same root, different bytes) or gone untrusted.

`sign` is the accountable-authorization ceremony: a trusted signature
over the chain's `sign_root`, coupled to a review packet that freezes the
root, build digest, and recorded-proof status the keyholder reviewed.
`sign_check` reports the ceremony's own paperwork -- whether the
signature is authorized and the stored packet still holds -- which is
one half of `kernel.phase`'s SIGNED (authorized AND proven); the kernel
owns the composite.
"""
import hashlib
import json
import os
import subprocess

from . import _util
from . import kernel
from . import registry

ATTEST = ".reticuli/attest"


# --------------------------------------------------------------- signing --

def _sign_file(key: str, namespace: str, path: str) -> str:
    """Detached ssh signature over `path`, in `namespace`. Any stale
    signature at the destination is removed first -- `ssh-keygen -Y sign`
    otherwise prompts interactively before overwriting one."""
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
                   check=True, capture_output=True)
    return sig_path


def _verify_signature(stmt_path: str, sig_path: str, signers: str, namespace: str) -> bool:
    if not (os.path.isfile(stmt_path) and os.path.isfile(sig_path) and os.path.isfile(signers)):
        return False
    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", signers, "-s", sig_path],
            capture_output=True, timeout=30, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return False
    principals = [line.split()[0] for line in found.stdout.splitlines() if line.strip()]
    if not principals:
        return False
    try:
        with open(stmt_path, "rb") as f:
            data = f.read()
    except OSError:
        return False
    for principal in principals:
        try:
            verified = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", principal,
                 "-n", namespace, "-s", sig_path],
                input=data, capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if verified.returncode == 0:
            return True
    return False


# ---------------------------------------------------------------- attest --

def attest(d: str, key: str, principal: str) -> dict:
    """Sign a build: refuses unless every gate re-earns its verdict cold,
    right now, on the bytes present -- never a carried verdict."""
    audit_result = kernel.audit(d)
    if not audit_result["ok"]:
        raise kernel.ClaimError(
            f"attest refuses: {d!r} does not audit clean: {audit_result.get('verdict')}")
    root = audit_result["root"]
    digest = kernel.build_digest(d)
    store = os.path.join(d, ATTEST)
    os.makedirs(store, exist_ok=True)
    base = f"{root[:16]}-{digest[:16]}"

    statement = {"root": root, "build_digest": digest, "principal": principal,
                 "when": _util.stamp()}
    stmt_bytes = json.dumps(statement, sort_keys=True).encode("utf-8")
    stmt_rel = os.path.join(ATTEST, base + ".statement.json")
    stmt_path = os.path.join(d, stmt_rel)
    with open(stmt_path, "wb") as f:
        f.write(stmt_bytes)

    _sign_file(key, kernel.NAMESPACE, stmt_path)
    sig_rel = stmt_rel + ".sig"
    return {"root": root, "build_digest": digest, "statement": stmt_rel, "signature": sig_rel}


def check(d: str, signers: str = None) -> dict:
    """Whether a stored attestation still names the current build:
    intact (root matches, bytes have not drifted) and, when an anchor is
    given, signed by a principal it trusts."""
    store = os.path.join(d, ATTEST)
    if not os.path.isdir(store):
        return {"ok": False, "attestations": []}
    try:
        verified = kernel.verify(d)
        current_root = verified["root"] if verified["ok"] else None
    except kernel.ClaimError:
        current_root = None
    try:
        current_digest = kernel.build_digest(d)
    except kernel.ClaimError:
        current_digest = None

    names = sorted(f for f in os.listdir(store) if f.endswith(".statement.json"))
    attestations = []
    ok_overall = bool(names)
    for name in names:
        stmt_path = os.path.join(store, name)
        sig_path = stmt_path + ".sig"
        entry = {"statement": os.path.join(ATTEST, name)}
        try:
            with open(stmt_path, "rb") as f:
                raw = f.read()
            stmt = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            entry.update(verdict="malformed", drifted=True)
            attestations.append(entry)
            ok_overall = False
            continue
        drifted = stmt.get("build_digest") != current_digest
        root_matches = current_root is not None and stmt.get("root") == current_root
        signer_ok = True
        if signers is not None:
            signer_ok = _verify_signature(stmt_path, sig_path, signers, kernel.NAMESPACE)
        this_ok = root_matches and not drifted and signer_ok
        entry.update(root=stmt.get("root"), principal=stmt.get("principal"),
                     drifted=drifted,
                     verdict="signed" if this_ok else ("drifted" if drifted else "untrusted"))
        attestations.append(entry)
        if not this_ok:
            ok_overall = False
    return {"ok": ok_overall, "attestations": attestations}


# ----------------------------------------------------------- the ceremony --

def review_packet(d: str, ws: str = None) -> dict:
    """What a keyholder reviews before signing: the root, the chain's
    signature node, the audit verdict, and whether a proof is recorded --
    the reviewer sees the whole ladder, not just the top rung."""
    verified = kernel.verify(d)
    audit_result = kernel.audit(d)
    manifest = kernel.read_manifest(d)
    the_sign_root = registry.sign_root(d, ws)
    return {
        "root": verified["root"],
        "build_digest": kernel.build_digest(d),
        "sign_root": the_sign_root,
        "audit": {"ok": audit_result["ok"], "verdict": audit_result.get("verdict")},
        "proof": manifest.get("proof"),
    }


def _find_packet(sign_dir: str, digest):
    if not digest:
        return None
    for name in sorted(os.listdir(sign_dir)):
        if not name.endswith(".packet.json"):
            continue
        path = os.path.join(sign_dir, name)
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            continue
        if hashlib.sha256(raw).hexdigest() != digest:
            continue
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
    return None


def sign(d: str, key: str, principal: str, *, ws: str = None) -> dict:
    """The signing ceremony: refuse a claim whose verdicts do not
    reproduce, freeze a review packet (root, build digest, recorded-proof
    status), and sign the chain root bound to that packet's digest."""
    audit_result = kernel.audit(d)
    if not audit_result["ok"]:
        raise kernel.ClaimError(
            f"sign refuses: {d!r} does not audit clean: {audit_result.get('verdict')}")
    verified = kernel.verify(d)
    root = verified["root"]
    digest = kernel.build_digest(d)
    manifest = kernel.read_manifest(d)
    the_sign_root = registry.sign_root(d, ws)

    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(sign_dir, exist_ok=True)
    base = f"{root[:16]}-{digest[:16]}"

    packet = {"root": root, "build_digest": digest, "sign_root": the_sign_root,
              "audit": {"ok": audit_result["ok"], "verdict": audit_result.get("verdict")},
              "proof": manifest.get("proof")}
    packet_bytes = json.dumps(packet, sort_keys=True).encode("utf-8")
    packet_rel = os.path.join(kernel.SIGN_DIR, base + ".packet.json")
    packet_path = os.path.join(d, packet_rel)
    with open(packet_path, "wb") as f:
        f.write(packet_bytes)
    packet_digest = hashlib.sha256(packet_bytes).hexdigest()

    statement = {"ceremony": "RETICULI_CLAIM_BASIN_V1", "root": root, "build_digest": digest,
                 "sign_root": the_sign_root, "packet_digest": packet_digest,
                 "principal": principal, "when": _util.stamp()}
    stmt_bytes = json.dumps(statement, sort_keys=True).encode("utf-8")
    stmt_rel = os.path.join(kernel.SIGN_DIR, base + ".sign.json")
    stmt_path = os.path.join(d, stmt_rel)
    with open(stmt_path, "wb") as f:
        f.write(stmt_bytes)

    _sign_file(key, kernel.SIGN_NAMESPACE, stmt_path)
    sig_rel = stmt_rel + ".sig"

    return {"ceremony": "RETICULI_CLAIM_BASIN_V1", "root": root, "sign_root": the_sign_root,
            "statement": stmt_rel, "signature": sig_rel, "packet": packet_rel}


def sign_check(d: str, *, ws: str = None, signers: str = None) -> dict:
    """The ceremony's own paperwork: is the signature authorized, and does
    the stored packet it binds to still hold against the current bytes."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return {"ok": False, "authorizations": []}
    try:
        verified = kernel.verify(d)
        current_root = verified["root"] if verified["ok"] else None
    except kernel.ClaimError:
        current_root = None
    try:
        current_digest = kernel.build_digest(d)
    except kernel.ClaimError:
        current_digest = None

    names = sorted(f for f in os.listdir(sign_dir) if f.endswith(".sign.json"))
    rows = []
    ok_overall = False
    for name in names:
        stmt_path = os.path.join(sign_dir, name)
        sig_path = stmt_path + ".sig"
        row = {"statement": os.path.join(kernel.SIGN_DIR, name)}
        try:
            with open(stmt_path, "rb") as f:
                raw = f.read()
            stmt = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            row.update(verdict="malformed", packet_holds=False, proof_recorded=False, ok=False)
            rows.append(row)
            continue
        signer_ok = True
        if signers is not None:
            signer_ok = _verify_signature(stmt_path, sig_path, signers, kernel.SIGN_NAMESPACE)
        root_matches = current_root is not None and stmt.get("root") == current_root
        packet = _find_packet(sign_dir, stmt.get("packet_digest"))
        packet_holds = bool(packet is not None and packet.get("root") == current_root
                             and packet.get("build_digest") == current_digest)
        proof_recorded = bool(packet.get("proof")) if packet else False
        authorized = signer_ok and root_matches
        this_ok = authorized and packet_holds
        row.update(verdict="authorized" if authorized else "untrusted",
                   packet_holds=packet_holds, proof_recorded=proof_recorded, ok=this_ok)
        rows.append(row)
        if this_ok:
            ok_overall = True
    return {"ok": ok_overall, "authorizations": rows}
