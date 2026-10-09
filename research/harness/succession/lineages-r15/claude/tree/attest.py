"""Attestation: a keyholder's signed statement of a build (`spec/layers.md`).

`attest`/`check` are the plain attestation: sign only a claim whose
verdicts reproduce from their own bytes right now (a cold `kernel.audit`,
never a carried verdict), in the `reticuli` namespace, domain-separated
from both the record's namespace and the authorization ceremony's.
`review_packet`/`sign`/`sign_check` are the ceremony: an accountable
authorization over the signed chain, bound to a packet the signer
reviewed -- SIGNED means AUTHORIZED (by a trusted signer) AND PROVEN (a
recorded proof); `kernel.phase` is the sole judge of that coupling, reading
exactly the on-disk shape this module writes under `kernel.SIGN_DIR`.

Stdlib only.
"""
import hashlib
import json
import os
import shutil
import subprocess

from reticuli import _util, kernel, registry

ATTEST = ".reticuli/attest"

_CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _allowed_identities(allowed_signers: str) -> list:
    identities = []
    with open(allowed_signers, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head = line.split(" ", 1)[0]
            identities.extend(head.split(","))
    return identities


def _ssh_verify(allowed_signers: str, identity_name: str, namespace: str,
                 signature_path: str, data: bytes) -> bool:
    if not shutil.which("ssh-keygen"):
        return False
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", identity_name, "-n", namespace, "-s", signature_path],
            input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _check_novalidate(signature_path: str, namespace: str, data: bytes) -> bool:
    if not shutil.which("ssh-keygen"):
        return False
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "check-novalidate", "-n", namespace, "-s", signature_path],
            input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _sign_file(path: str, key: str, namespace: str) -> str:
    """Sign `path` in `namespace`, removing any stale `.sig` first -- else
    `ssh-keygen -Y sign` prompts interactively before overwriting one.
    """
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
                    check=True, capture_output=True)
    return sig_path


# -- attest / check: the plain attestation. --------------------------------


def attest(d: str, key: str, identity_name: str) -> dict:
    """Sign a statement of `d`'s current build: its root and build digest,
    earned by a cold audit right now -- never a carried verdict.
    """
    result = kernel.audit(d)
    if not result.get("ok"):
        raise kernel.ClaimError(
            f"cannot attest {d!r}: audit did not earn ({result.get('verdict')})")

    manifest = kernel.read_manifest(d)
    statement = {
        "root": manifest["root"],
        "build_digest": kernel.build_digest(d),
        "identity": identity_name,
        "when": _util.stamp(),
    }
    out_dir = os.path.join(d, ATTEST)
    os.makedirs(out_dir, exist_ok=True)
    idx = sum(1 for n in os.listdir(out_dir) if n.endswith(".statement.json"))
    spath = os.path.join(out_dir, f"{idx:04d}.statement.json")
    _util.write_json(spath, statement)
    sig_path = _sign_file(spath, key, kernel.NAMESPACE)

    return {
        "signature": os.path.relpath(sig_path, d),
        "statement": os.path.relpath(spath, d),
    }


def check(d: str, signers=None) -> dict:
    """Verify every attestation under `d`: structurally intact (the
    signature still matches the statement's exact bytes), not drifted (the
    statement's root/build digest still match the claim's current ones),
    and -- with `signers` given -- signed by a trusted identity.
    """
    out_dir = os.path.join(d, ATTEST)
    attestations = []
    if os.path.isdir(out_dir):
        try:
            current_root = kernel.verify(d).get("root")
            current_bd = kernel.build_digest(d)
        except kernel.ClaimError:
            current_root = None
            current_bd = None

        for name in sorted(os.listdir(out_dir)):
            if not name.endswith(".statement.json"):
                continue
            spath = os.path.join(out_dir, name)
            sig_path = spath + ".sig"
            if not os.path.isfile(sig_path):
                continue
            with open(spath, "rb") as f:
                raw = f.read()
            try:
                statement = json.loads(raw)
            except json.JSONDecodeError:
                statement = {}

            sig_valid = _check_novalidate(sig_path, kernel.NAMESPACE, raw)
            verdict = "intact" if sig_valid else "tampered"
            signer_identity = None
            if signers and sig_valid:
                identity_claimed = statement.get("identity")
                if identity_claimed and os.path.isfile(signers):
                    for ident in _allowed_identities(signers):
                        if ident == identity_claimed and \
                                _ssh_verify(signers, ident, kernel.NAMESPACE, sig_path, raw):
                            signer_identity = ident
                            break
                verdict = "signed" if signer_identity else "unauthorized"

            drifted = statement.get("root") != current_root or \
                statement.get("build_digest") != current_bd
            ok = sig_valid and not drifted and (signer_identity is not None if signers else True)
            attestations.append({
                "statement": os.path.relpath(spath, d),
                "signature": os.path.relpath(sig_path, d),
                "identity": statement.get("identity"),
                "root": statement.get("root"),
                "verdict": verdict,
                "drifted": drifted,
                "ok": ok,
            })

    overall_ok = bool(attestations) and all(a["ok"] for a in attestations)
    return {"ok": overall_ok, "attestations": attestations}


# -- review_packet / sign / sign_check: the authorization ceremony. -------


def review_packet(d: str, ws=None) -> dict:
    """Assemble what a signer reviews before authorizing `d`: its current
    root and build digest, the folded signature-chain root, a fresh audit,
    and whether a proof is already recorded.
    """
    doc = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    return {
        "root": kernel.root(doc, d),
        "build_digest": kernel.build_digest(d),
        "sign_root": registry.sign_root(d, ws),
        "audit": kernel.audit(d),
        "proof": manifest.get("proof"),
    }


def sign(d: str, key: str, identity_name: str, ws=None) -> dict:
    """The ceremony: refuse a claim whose verdicts do not reproduce, sign
    the chain root and the review packet the signer reviewed.
    """
    packet = review_packet(d, ws)
    if not packet["audit"].get("ok"):
        raise kernel.ClaimError(
            f"cannot sign {d!r}: audit did not earn ({packet['audit'].get('verdict')})")

    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(sign_dir, exist_ok=True)
    base = hashlib.sha256(identity_name.encode("utf-8")).hexdigest()[:16]

    ppath = os.path.join(sign_dir, base + ".packet.json")
    _util.write_json(ppath, packet)
    packet_digest = hashlib.sha256(
        json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()

    statement = {
        "ceremony": _CEREMONY,
        "identity": identity_name,
        "packet_digest": packet_digest,
    }
    spath = os.path.join(sign_dir, base + ".sign.json")
    _util.write_json(spath, statement)
    sig_path = _sign_file(spath, key, kernel.SIGN_NAMESPACE)

    return {
        "ceremony": _CEREMONY,
        "signature": os.path.relpath(sig_path, d),
        "statement": os.path.relpath(spath, d),
        "packet": os.path.relpath(ppath, d),
    }


def sign_check(d: str, ws=None, signers=None) -> dict:
    """The reviewer's own view of the ceremony: per statement, whether a
    trusted identity authorized it, whether the signed packet still holds
    (digest matches, and names the claim's current root/build digest), and
    whether a proof was recorded -- authorization and proof kept distinct.
    """
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    authorizations = []
    if os.path.isdir(sign_dir):
        try:
            doc = kernel.load_recipe(d)
            current_root = kernel.root(doc, d)
            current_bd = kernel.build_digest(d)
        except kernel.ClaimError:
            current_root = None
            current_bd = None

        for name in sorted(os.listdir(sign_dir)):
            if not name.endswith(".sign.json"):
                continue
            spath = os.path.join(sign_dir, name)
            sig_path = spath + ".sig"
            if not os.path.isfile(sig_path):
                continue
            with open(spath, "rb") as f:
                raw = f.read()
            try:
                statement = json.loads(raw)
            except json.JSONDecodeError:
                statement = {}

            identity_claimed = statement.get("identity")
            verdict = "unauthorized"
            if signers and identity_claimed and os.path.isfile(signers):
                for ident in _allowed_identities(signers):
                    if ident == identity_claimed and \
                            _ssh_verify(signers, ident, kernel.SIGN_NAMESPACE, sig_path, raw):
                        verdict = "authorized"
                        break

            packet_name = name[: -len(".sign.json")] + ".packet.json"
            ppath = os.path.join(sign_dir, packet_name)
            packet_holds = False
            proof_recorded = False
            if os.path.isfile(ppath):
                try:
                    packet = _util.read_json(ppath)
                except kernel.ClaimError:
                    packet = None
                if packet is not None:
                    pdig = hashlib.sha256(
                        json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()
                    if pdig == statement.get("packet_digest") and \
                            packet.get("root") == current_root and \
                            packet.get("build_digest") == current_bd:
                        packet_holds = True
                        proof_recorded = bool(packet.get("proof"))

            authorizations.append({
                "identity": identity_claimed,
                "verdict": verdict,
                "packet_holds": packet_holds,
                "proof_recorded": proof_recorded,
                "ok": verdict == "authorized" and packet_holds,
            })

    overall_ok = bool(authorizations) and all(a["ok"] for a in authorizations)
    return {"ok": overall_ok, "authorizations": authorizations}
