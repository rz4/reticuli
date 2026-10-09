"""Attestation: a keyholder's signed statement of a build (`spec/layers.md`).

`attest(d, key, identity)` signs only claims whose verdicts reproduce from
their own bytes -- it re-earns the verdict (`kernel.audit`) before ever
touching a key, so it never notarizes a carried verdict and never signs a
claim whose own pin is broken. `check(d, signers=None)` reads an
attestation back: drift (the claim's current root/build_digest no longer
matches what was signed) refuses regardless of an anchor; a tampered
statement refuses once an anchor is given to verify against.

`review_packet`/`sign`/`sign_check` are the signing CEREMONY: accountable
authorization over a claim's whole chain. SIGNED means AUTHORIZED (by a
trusted signer) AND PROVEN (a recorded proof) -- the two facts are coupled
but distinct, and a reviewer must see which is which. The on-disk statement
and packet this ceremony writes are exactly what `kernel.phase` (pinned,
given) already knows how to read back: a `<root>.sign.json` statement
naming a `<root>.packet.json` by its digest, detached-signed in the
kernel's own `SIGN_NAMESPACE`.

Stdlib only.
"""
import hashlib
import json
import os
import subprocess
import tempfile

from reticuli import _util, kernel, registry

ATTEST = ".reticuli/attest"
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _ssh_verify(namespace: str, allowed_signers: str, signer_id: str,
                signature: bytes, data: bytes) -> bool:
    if not allowed_signers or not os.path.isfile(allowed_signers) or not signer_id:
        return False
    fd, sig_path = tempfile.mkstemp(suffix=".sig")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(signature)
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", signer_id, "-n", namespace, "-s", sig_path],
            input=data, capture_output=True, timeout=10)
    except OSError:
        return False
    finally:
        try:
            os.remove(sig_path)
        except OSError:
            pass
    return result.returncode == 0


# =============================================================================
# attest / check: a plain signed statement of one build
# =============================================================================

def attest(d: str, key_path: str, identity: str) -> dict:
    audit_result = kernel.audit(d)
    if not audit_result["ok"]:
        raise kernel.ClaimError(
            f"cannot attest {d!r}: verdict does not reproduce from these "
            f"bytes ({audit_result['verdict']})")

    manifest = kernel.read_manifest(d)
    root_value = manifest["root"]
    statement = {
        "root": root_value,
        "build_digest": kernel.build_digest(d),
        "signer": identity,
        "when": _util.stamp(),
    }
    base = os.path.join(d, ATTEST)
    os.makedirs(base, exist_ok=True)
    rel_statement = f"{ATTEST}/{root_value}.statement.json"
    statement_path = os.path.join(d, rel_statement)
    _util.write_json(statement_path, statement)

    rel_sig = rel_statement + ".sig"
    sig_path = os.path.join(d, rel_sig)
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key_path, "-n", kernel.NAMESPACE,
         statement_path], check=True, capture_output=True)
    return {"statement": rel_statement, "signature": rel_sig}


def check(d: str, signers: str = None) -> dict:
    base = os.path.join(d, ATTEST)
    attestations = []
    ok = True
    if os.path.isdir(base):
        for fn in sorted(os.listdir(base)):
            if not fn.endswith(".statement.json"):
                continue
            statement_path = os.path.join(base, fn)
            sig_path = statement_path + ".sig"
            try:
                stmt = _util.read_json(statement_path)
            except kernel.ClaimError:
                attestations.append({"verdict": "malformed", "drifted": False})
                ok = False
                continue

            try:
                current_root = kernel.verify(d)["root"]
            except kernel.ClaimError:
                current_root = None
            try:
                current_digest = kernel.build_digest(d)
            except kernel.ClaimError:
                current_digest = None
            drifted = (current_root != stmt.get("root")
                       or current_digest != stmt.get("build_digest"))

            entry = {"root": stmt.get("root"), "signer": stmt.get("signer"),
                      "drifted": drifted}
            if drifted:
                entry["verdict"] = "drifted"
                ok = False
            elif signers:
                verified = False
                if os.path.isfile(sig_path):
                    with open(statement_path, "rb") as f:
                        data = f.read()
                    with open(sig_path, "rb") as f:
                        signature = f.read()
                    verified = _ssh_verify(kernel.NAMESPACE, signers,
                                            stmt.get("signer"), signature, data)
                entry["verdict"] = "signed" if verified else "unverified"
                if not verified:
                    ok = False
            else:
                entry["verdict"] = "unanchored"
            attestations.append(entry)
    return {"ok": ok and bool(attestations), "attestations": attestations}


# =============================================================================
# the signing ceremony: accountable authorization over the chain
# =============================================================================

def review_packet(d: str, ws=None) -> dict:
    v = kernel.verify(d)
    a = kernel.audit(d)
    manifest = kernel.read_manifest(d)
    try:
        sr = registry.sign_root(d, ws)
    except kernel.ClaimError:
        sr = None
    return {
        "root": v["root"],
        "build_digest": kernel.build_digest(d),
        "sign_root": sr,
        "audit": {"ok": a["ok"], "verdict": a["verdict"]},
        "proof": manifest.get("proof"),
    }


def sign(d: str, key_path: str, identity: str, ws=None) -> dict:
    pkt = review_packet(d, ws=ws)
    if not pkt["audit"]["ok"]:
        raise kernel.ClaimError(
            f"cannot sign {d!r}: audit did not reproduce ({pkt['audit']['verdict']})")

    claim_root = pkt["root"]
    packet = {
        "root": claim_root,
        "build_digest": pkt["build_digest"],
        "sign_root": pkt["sign_root"],
        "proof": bool(pkt["proof"]),
    }
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(sign_dir, exist_ok=True)
    base = claim_root
    packet_rel = f"{kernel.SIGN_DIR}/{base}.packet.json"
    packet_path = os.path.join(d, packet_rel)
    _util.write_json(packet_path, packet)
    with open(packet_path, "rb") as f:
        packet_digest = hashlib.sha256(f.read()).hexdigest()

    statement = {
        "root": claim_root,
        "identity": identity,
        "packet_digest": packet_digest,
        "ceremony": CEREMONY,
        "when": _util.stamp(),
    }
    statement_rel = f"{kernel.SIGN_DIR}/{base}.sign.json"
    statement_path = os.path.join(d, statement_rel)
    _util.write_json(statement_path, statement)

    sig_rel = statement_rel + ".sig"
    sig_path = os.path.join(d, sig_rel)
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key_path, "-n", kernel.SIGN_NAMESPACE,
         statement_path], check=True, capture_output=True)
    return {"ceremony": CEREMONY, "signature": sig_rel,
             "statement": statement_rel, "packet": packet_rel}


def sign_check(d: str, ws=None, signers: str = None) -> dict:
    claim_root = kernel.verify(d)["root"]
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    authorizations = []
    ok = False
    if os.path.isdir(sign_dir):
        for fn in sorted(os.listdir(sign_dir)):
            if not fn.endswith(".sign.json"):
                continue
            spath = os.path.join(sign_dir, fn)
            sig_path = spath + ".sig"
            try:
                stmt = _util.read_json(spath)
            except kernel.ClaimError:
                continue
            if stmt.get("root") != claim_root:
                continue
            signer = stmt.get("identity")

            packet_file = fn[: -len(".sign.json")] + ".packet.json"
            ppath = os.path.join(sign_dir, packet_file)
            packet_holds = False
            proof_recorded = False
            if os.path.isfile(ppath):
                with open(ppath, "rb") as f:
                    raw = f.read()
                if hashlib.sha256(raw).hexdigest() == stmt.get("packet_digest"):
                    try:
                        packet = json.loads(raw)
                    except json.JSONDecodeError:
                        packet = None
                    if isinstance(packet, dict) and packet.get("root") == claim_root:
                        try:
                            current_digest = kernel.build_digest(d)
                        except kernel.ClaimError:
                            current_digest = None
                        if packet.get("build_digest") == current_digest:
                            packet_holds = True
                            proof_recorded = bool(packet.get("proof"))

            verified = False
            if signers and os.path.isfile(sig_path) and isinstance(signer, str):
                with open(spath, "rb") as f:
                    data = f.read()
                with open(sig_path, "rb") as f:
                    signature = f.read()
                verified = _ssh_verify(kernel.SIGN_NAMESPACE, signers, signer,
                                        signature, data)

            if verified and packet_holds:
                verdict = "authorized"
            elif verified:
                verdict = "unauthorized"
            else:
                verdict = "unverified"
            row_ok = verdict == "authorized"
            ok = ok or row_ok
            authorizations.append({"identity": signer, "verdict": verdict,
                                     "packet_holds": packet_holds,
                                     "proof_recorded": proof_recorded})
    return {"ok": ok, "authorizations": authorizations}
