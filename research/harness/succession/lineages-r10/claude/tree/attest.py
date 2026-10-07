"""attest.py: signed statements about a build, for other parties.

Two distinct ceremonies live here, under two distinct namespaces
(`reticuli.record` is a third, owned by `record.py`):

- a plain ATTESTATION (`attest`/`check`) signs a snapshot of a build --
  its root and build digest -- under the base identity namespace. It
  signs only a claim whose verdicts reproduce from its OWN bytes, never
  a carried verdict, and refuses a tampered statement.
- the AUTHORIZATION ceremony (`sign`/`sign_check`) signs a review
  packet -- the audit, the signature-chain fold, and the claim's
  recorded proof -- under the mint namespace `kernel.phase` itself
  reads back. SIGNED (per `kernel.phase`) means authorized AND proven;
  this module reports authorization alone, the coupling is the
  kernel's.
"""
import hashlib
import json
import os
import subprocess

from . import kernel
from . import registry
from . import _util

ATTEST = ".reticuli/attest"

CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _allowed_identities(anchor: str) -> list:
    with open(anchor, "r", encoding="utf-8") as f:
        lines = f.readlines()
    identities = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        identity = line.split()[0]
        if identity not in identities:
            identities.append(identity)
    return identities


def _ssh_verify(allowed_signers: str, identity: str, namespace: str,
                 data: bytes, signature_path: str) -> bool:
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", identity,
             "-n", namespace, "-s", signature_path],
            input=data, capture_output=True,
        )
    except OSError:
        return False
    return proc.returncode == 0


# =====================================================================
# plain attestation: a signed snapshot of one build
# =====================================================================

def attest(d: str, key: str, identity: str) -> dict:
    """Sign a statement of this build's root and build digest -- only
    once its own verdicts reproduce from its own bytes."""
    aud = kernel.audit(d)
    if not aud["ok"]:
        raise kernel.ClaimError(
            f"attest refuses a claim whose verdicts do not reproduce: {d!r}")
    manifest = kernel.read_manifest(d)
    root = manifest["root"]
    digest = kernel.build_digest(d)

    store_dir = os.path.join(d, ATTEST)
    os.makedirs(store_dir, exist_ok=True)
    base = f"{root[:16]}-{digest[:16]}"
    stmt_rel = f"{ATTEST}/{base}.json"
    stmt_path = os.path.join(d, stmt_rel)
    statement = {"root": root, "build_digest": digest, "identity": identity,
                 "when": _util.stamp()}
    _util.write_json(stmt_path, statement)

    sig_path = stmt_path + ".sig"
    if os.path.exists(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.NAMESPACE, stmt_path],
        check=True, capture_output=True,
    )
    return {"signature": stmt_rel + ".sig", "statement": stmt_rel}


def check(d: str, signers: str = None) -> dict:
    """Every attestation found in `d`, judged against the bytes
    present: `drifted` when the build no longer matches what was
    signed, `signed` when a trusted key's signature still verifies over
    the exact statement bytes on disk."""
    store_dir = os.path.join(d, ATTEST)
    attestations = []
    if os.path.isdir(store_dir):
        for fname in sorted(os.listdir(store_dir)):
            if not fname.endswith(".json"):
                continue
            stmt_path = os.path.join(store_dir, fname)
            sig_path = stmt_path + ".sig"
            try:
                with open(stmt_path, "rb") as f:
                    stmt_bytes = f.read()
                stmt = json.loads(stmt_bytes)
            except (OSError, json.JSONDecodeError):
                continue
            entry = {"root": stmt.get("root"), "identity": stmt.get("identity")}
            try:
                vr = kernel.verify(d)
                current_digest = kernel.build_digest(d)
            except kernel.ClaimError:
                entry.update(verdict="broken", drifted=True)
                attestations.append(entry)
                continue
            if stmt.get("root") != vr["root"]:
                entry.update(verdict="broken", drifted=True)
            elif stmt.get("build_digest") != current_digest:
                entry.update(verdict="drifted", drifted=True)
            else:
                verdict = "unsigned"
                if signers and os.path.isfile(signers) and os.path.isfile(sig_path):
                    for ident in _allowed_identities(signers):
                        if _ssh_verify(signers, ident, kernel.NAMESPACE, stmt_bytes, sig_path):
                            verdict = "signed"
                            entry["identity"] = ident
                            break
                entry.update(verdict=verdict, drifted=False)
            attestations.append(entry)

    ok = bool(attestations)
    for a in attestations:
        if a["drifted"]:
            ok = False
        elif signers and a["verdict"] != "signed":
            ok = False
    return {"ok": ok, "attestations": attestations}


# =====================================================================
# the signing ceremony: authorization over a reviewed packet
# =====================================================================

def review_packet(d: str, ws: str = None) -> dict:
    """Assemble the packet a keyholder reviews: the audit re-earned
    fresh, the signature-chain fold over the DAG, and the claim's
    currently recorded proof (if any) -- never a carried verdict."""
    aud = kernel.audit(d)
    if not aud["ok"]:
        raise kernel.ClaimError(
            f"review packet refuses a claim whose verdicts do not reproduce: {d!r}")
    manifest = kernel.read_manifest(d)
    root = manifest["root"]
    digest = kernel.build_digest(d)
    sroot = registry.sign_root(d, ws)
    return {
        "root": root,
        "build_digest": digest,
        "sign_root": sroot,
        "audit": aud,
        "proof": manifest.get("proof"),
    }


def sign(d: str, key: str, identity: str, ws: str = None) -> dict:
    """The ceremony: sign the review packet's digest, under the mint
    namespace `kernel.phase` reads back."""
    packet = review_packet(d, ws=ws)
    packet_digest = hashlib.sha256(
        json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()

    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(sign_dir, exist_ok=True)
    base = "attest"
    packet_rel = f"{kernel.SIGN_DIR}/{base}.packet.json"
    stmt_rel = f"{kernel.SIGN_DIR}/{base}.sign.json"
    packet_path = os.path.join(d, packet_rel)
    stmt_path = os.path.join(d, stmt_rel)

    statement = {"ceremony": CEREMONY, "root": packet["root"], "identity": identity,
                 "packet_digest": packet_digest, "when": _util.stamp()}
    _util.write_json(packet_path, packet)
    _util.write_json(stmt_path, statement)

    sig_path = stmt_path + ".sig"
    if os.path.exists(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.SIGN_NAMESPACE, stmt_path],
        check=True, capture_output=True,
    )

    return {"ceremony": CEREMONY, "signature": stmt_rel + ".sig",
            "statement": stmt_rel, "packet": packet_rel}


def sign_check(d: str, ws: str = None, signers: str = None) -> dict:
    """Every authorization found in `d`: whether its packet still
    matches the claim's current state exactly, and whether a trusted
    key's signature still verifies over the exact statement bytes.
    `proof_recorded` says whether the reviewed packet carried a proof --
    authorization is never mistaken for proof."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    authorizations = []
    if os.path.isdir(sign_dir):
        for fname in sorted(os.listdir(sign_dir)):
            if not fname.endswith(".sign.json"):
                continue
            base = fname[: -len(".sign.json")]
            stmt_path = os.path.join(sign_dir, fname)
            sig_path = stmt_path + ".sig"
            packet_path = os.path.join(sign_dir, base + ".packet.json")
            entry = {"identity": None, "verdict": "unauthorized",
                     "packet_holds": False, "proof_recorded": False}
            try:
                with open(stmt_path, "rb") as f:
                    stmt_bytes = f.read()
                stmt = json.loads(stmt_bytes)
            except (OSError, json.JSONDecodeError):
                authorizations.append(entry)
                continue
            entry["identity"] = stmt.get("identity")
            try:
                manifest = kernel.read_manifest(d)
                current_root = manifest["root"]
                current_digest = kernel.build_digest(d)
            except kernel.ClaimError:
                authorizations.append(entry)
                continue
            if stmt.get("root") != current_root:
                authorizations.append(entry)
                continue
            try:
                with open(packet_path, encoding="utf-8") as f:
                    packet = json.load(f)
            except (OSError, json.JSONDecodeError):
                authorizations.append(entry)
                continue
            actual_digest = hashlib.sha256(
                json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()
            packet_holds = (actual_digest == stmt.get("packet_digest")
                            and packet.get("root") == current_root
                            and packet.get("build_digest") == current_digest)
            entry["packet_holds"] = packet_holds
            entry["proof_recorded"] = bool(packet.get("proof")) if packet_holds else False

            verified = False
            if signers and os.path.isfile(signers) and os.path.isfile(sig_path):
                for ident in _allowed_identities(signers):
                    if _ssh_verify(signers, ident, kernel.SIGN_NAMESPACE, stmt_bytes, sig_path):
                        verified = True
                        entry["identity"] = ident
                        break
            entry["verdict"] = "authorized" if (packet_holds and verified) else "unauthorized"
            authorizations.append(entry)

    ok = bool(authorizations) and all(a["verdict"] == "authorized" for a in authorizations)
    return {"ok": ok, "authorizations": authorizations}
