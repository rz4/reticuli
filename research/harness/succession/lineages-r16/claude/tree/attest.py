"""Attestation and the signing ceremony.

Two distinct, independently keyed mechanisms:

`attest`/`check` are a keyholder's plain NOTARIZATION of one build: "I
re-earned this root's verdicts, on exactly these bytes, just now." It
refuses to notarize anything less than a fresh, cold re-earn
(`registry.audit_deep`) -- never a carried verdict, never a broken claim
-- and the statement freezes the root and build digest it attests to, so
`check` can later detect DRIFT (the claim regenerated after attestation,
same root, different bytes) independently of whether the signature is
anchored to a trusted identity.

`review_packet`/`sign`/`sign_check` are the accountable AUTHORIZATION
ceremony: the packet a keyholder reviews before signing is the deep audit
and the signature chain over the claim's whole lineage (`registry.
sign_root`), plus whatever proof is currently recorded. Signing binds a
detached signature to that exact packet; `sign_check` reports whether a
signature is anchored (authorized), whether the packet it names still
matches what is stored (`packet_holds`), and whether the packet carries a
recorded proof (`proof_recorded`) -- authorization and proof are reported
as two separate facts, never conflated. Re-signing the same identity
replaces its prior statement/signature/packet rather than accumulating a
new one beside it.
"""
import hashlib
import json
import os
import subprocess

from reticuli import kernel
from reticuli import registry
from reticuli import _util

ATTEST = ".reticuli/attest"
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("utf-8")


# ------------------------------------------------------------- attestation
def attest(d: str, key: str, identity: str) -> dict:
    """Notarize the build currently at `d`: refuses unless every verdict in
    its whole lineage re-earns, cold, right now."""
    aud = registry.audit_deep(d)
    if not aud["ok"]:
        raise kernel.ClaimError(
            "attest refuses a claim whose verdicts do not reproduce")

    statement = {
        "identity": identity,
        "root": kernel.verify(d)["root"],
        "build_digest": kernel.build_digest(d),
    }
    raw = _canon(statement)

    attest_dir = os.path.join(d, ATTEST)
    os.makedirs(attest_dir, exist_ok=True)
    base = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    stmt_path = os.path.join(attest_dir, base + ".statement.json")
    sig_path = stmt_path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    with open(stmt_path, "wb") as f:
        f.write(raw)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.NAMESPACE, stmt_path],
        check=True, capture_output=True,
    )
    return {"statement": os.path.relpath(stmt_path, d),
             "signature": os.path.relpath(sig_path, d)}


def check(d: str, signers: str = None) -> dict:
    """Read back every attestation under `d`: intact (signature
    well-formed), anchored (verifies against `signers`, if given), and
    whether the claim has drifted since the attested build."""
    try:
        live_root = kernel.verify(d)["root"]
    except kernel.ClaimError:
        live_root = None
    try:
        live_digest = kernel.build_digest(d)
    except kernel.ClaimError:
        live_digest = None

    attest_dir = os.path.join(d, ATTEST)
    attestations = []
    if os.path.isdir(attest_dir):
        for fname in sorted(os.listdir(attest_dir)):
            if not fname.endswith(".statement.json"):
                continue
            stmt_path = os.path.join(attest_dir, fname)
            sig_path = stmt_path + ".sig"
            try:
                with open(stmt_path, "rb") as f:
                    raw = f.read()
                stmt = json.loads(raw)
            except (OSError, json.JSONDecodeError):
                continue
            identity_name = stmt.get("identity")
            stated_root = stmt.get("root")
            stated_digest = stmt.get("build_digest")
            drifted = (stated_root != live_root) or (stated_digest != live_digest)

            intact = False
            if os.path.isfile(sig_path):
                try:
                    with open(sig_path, "rb") as f:
                        sig = f.read()
                except OSError:
                    sig = None
                if sig is not None:
                    if signers and os.path.isfile(signers) and identity_name:
                        intact = _util.ssh_verify(signers, identity_name,
                                                   kernel.NAMESPACE, raw, sig)
                    else:
                        intact = _util.ssh_check_novalidate(kernel.NAMESPACE, raw, sig)

            if not intact:
                verdict = "tampered"
            elif drifted:
                verdict = "drifted"
            elif signers:
                verdict = "signed"
            else:
                verdict = "unanchored"

            attestations.append({"identity": identity_name, "verdict": verdict,
                                   "drifted": drifted, "root": stated_root})

    ok = bool(attestations) and all(
        a["verdict"] in ("signed", "unanchored") for a in attestations)
    return {"ok": ok, "attestations": attestations}


# ------------------------------------------------------------ the ceremony
def review_packet(d: str, *, ws=None) -> dict:
    """The packet a keyholder reviews before signing: identity, the
    signature-chain root over the whole lineage, the deep audit, and
    whatever proof is currently recorded."""
    manifest = kernel.read_manifest(d)
    v = kernel.verify(d)
    aud = registry.audit_deep(d)
    return {
        "root": v["root"],
        "build_digest": kernel.build_digest(d),
        "sign_root": registry.sign_root(d, ws) if ws is not None else None,
        "audit": {"ok": aud["ok"], "layers": aud["layers"]},
        "proof": manifest.get("proof"),
    }


def sign(d: str, key: str, identity: str, *, ws=None) -> dict:
    """Authorize `d`: refuses unless its deep audit holds, then signs the
    review packet, detached, in the mint namespace. Re-signing the same
    identity replaces its prior statement/signature/packet."""
    pkt = review_packet(d, ws=ws)
    if not pkt["audit"]["ok"]:
        raise kernel.ClaimError(
            "sign must refuse a claim whose verdicts do not reproduce")

    packet_bytes = _canon(pkt)
    packet_digest = hashlib.sha256(packet_bytes).hexdigest()
    statement = {"identity": identity, "packet_digest": packet_digest,
                 "ceremony": CEREMONY}
    statement_bytes = _canon(statement)

    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(sign_dir, exist_ok=True)
    base = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    packet_path = os.path.join(sign_dir, base + ".packet.json")
    statement_path = os.path.join(sign_dir, base + ".sign.json")
    sig_path = statement_path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)

    with open(packet_path, "wb") as f:
        f.write(packet_bytes)
    with open(statement_path, "wb") as f:
        f.write(statement_bytes)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.SIGN_NAMESPACE, statement_path],
        check=True, capture_output=True,
    )
    return {
        "ceremony": CEREMONY,
        "packet": os.path.relpath(packet_path, d),
        "statement": os.path.relpath(statement_path, d),
        "signature": os.path.relpath(sig_path, d),
    }


def sign_check(d: str, *, ws=None, signers: str = None) -> dict:
    """Report each authorization statement under `d`: anchored identity,
    whether the packet it names still matches what is stored, and whether
    that packet carries a recorded proof."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    authorizations = []
    if os.path.isdir(sign_dir):
        for fname in sorted(os.listdir(sign_dir)):
            if not fname.endswith(".sign.json"):
                continue
            stmt_path = os.path.join(sign_dir, fname)
            sig_path = stmt_path + ".sig"
            try:
                with open(stmt_path, "rb") as f:
                    raw = f.read()
                stmt = json.loads(raw)
            except (OSError, json.JSONDecodeError):
                continue
            identity_name = stmt.get("identity")
            packet_digest = stmt.get("packet_digest")

            base = fname[: -len(".sign.json")]
            packet_path = os.path.join(sign_dir, base + ".packet.json")
            packet_holds, packet = False, None
            if os.path.isfile(packet_path):
                with open(packet_path, "rb") as f:
                    packet_bytes = f.read()
                if hashlib.sha256(packet_bytes).hexdigest() == packet_digest:
                    packet_holds = True
                    try:
                        packet = json.loads(packet_bytes)
                    except json.JSONDecodeError:
                        packet = None

            verdict = "unsigned"
            if os.path.isfile(sig_path) and isinstance(identity_name, str):
                with open(sig_path, "rb") as f:
                    sig = f.read()
                if signers and os.path.isfile(signers) and _util.ssh_verify(
                        signers, identity_name, kernel.SIGN_NAMESPACE, raw, sig):
                    verdict = "authorized"
                else:
                    verdict = "unanchored"

            authorizations.append({
                "identity": identity_name, "verdict": verdict,
                "packet_holds": packet_holds,
                "proof_recorded": bool(packet and packet.get("proof")),
            })

    ok = any(a["verdict"] == "authorized" and a["packet_holds"]
             for a in authorizations)
    return {"ok": ok, "authorizations": authorizations}
