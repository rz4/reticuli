"""Attestation: a keyholder's signed statement of a build, and the signing
ceremony that authorizes a chain.

`attest`/`check` are the simple form: a signed statement naming the root and
build digest `kernel.audit` just re-earned -- refusing to notarize a carried
verdict or a broken claim -- kept beside the claim at `ATTEST`, in the
kernel's own attestation namespace. A build that drifts (different generated
bytes under the same root) makes the old attestation refuse; the exact bytes
restored, it holds again.

`sign`/`sign_check` are the ceremony: `review_packet` assembles what a human
reviews (the root, the folded signature-chain node, the audit, and -- for a
composed claim -- the deep chain audit) and `sign` refuses unless every piece
holds, then writes a `.sign.json` statement plus the `.packet.json` it binds
to, in exactly the shape `kernel.phase`'s own `_is_signed` reads: SIGNED means
AUTHORIZED (a trusted signer) AND PROVEN (`proof_recorded`), and the packet
digest ties the statement to the one packet a human actually reviewed.
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


def _signers(anchor: str) -> list:
    if not anchor or not os.path.isfile(anchor):
        return []
    names = []
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            who = line.split(None, 1)[0]
            names.extend(who.split(","))
    seen = set()
    ordered = []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def _authorized(anchor: str, principal: str) -> bool:
    return principal in _signers(anchor)


def _ssh_verify(data: bytes, sig_path: str, anchor: str, namespace: str, principal: str) -> bool:
    if not anchor or not _authorized(anchor, principal) or not os.path.isfile(sig_path):
        return False
    result = subprocess.run(
        ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", principal,
         "-n", namespace, "-s", sig_path],
        input=data, capture_output=True, timeout=30,
    )
    return result.returncode == 0


def _ssh_sign(key: str, namespace: str, path: str) -> None:
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
        check=True, capture_output=True,
    )


# ------------------------------------------------------------- attestation --

def attest(d: str, key: str, identity: str) -> dict:
    """Sign a statement of this build: `kernel.audit` must re-earn every
    verdict first -- attest never notarizes a carried verdict or a broken
    claim."""
    audited = kernel.audit(d)
    if not audited["ok"]:
        raise kernel.ClaimError(f"attest refuses an unearned claim: {audited}")
    manifest = kernel.read_manifest(d)
    build_digest = kernel.build_digest(d)
    stmt = {
        "root": manifest["root"],
        "build_digest": build_digest,
        "identity": identity,
        "when": _util.stamp(),
    }
    name = f"{manifest['root']}.json"
    stmt_path = os.path.join(d, ATTEST, name)
    _util.write_json(stmt_path, stmt)
    _ssh_sign(key, kernel.NAMESPACE, stmt_path)
    return {
        "statement": os.path.join(ATTEST, name),
        "signature": os.path.join(ATTEST, name + ".sig"),
        "root": manifest["root"],
    }


def check(d: str, signers: str = None) -> dict:
    """Every attestation kept beside `d`: intact (the recorded build
    digest matches the bytes present) and, where `signers` is given,
    signed by one of its listed principals."""
    attest_dir = os.path.join(d, ATTEST)
    if not os.path.isdir(attest_dir):
        return {"ok": False, "attestations": []}

    try:
        cur_bd = kernel.build_digest(d)
    except kernel.ClaimError:
        cur_bd = None

    attestations = []
    ok = True
    for fn in sorted(os.listdir(attest_dir)):
        if not fn.endswith(".json"):
            continue
        stmt_path = os.path.join(attest_dir, fn)
        sig_path = stmt_path + ".sig"
        try:
            with open(stmt_path, "rb") as f:
                raw = f.read()
            stmt = json.loads(raw)
        except (OSError, ValueError):
            ok = False
            attestations.append({"verdict": "malformed"})
            continue

        drifted = stmt.get("build_digest") != cur_bd
        entry_ok = not drifted
        verdict = "drifted" if drifted else "intact"

        if signers is not None:
            signer = stmt.get("identity")
            verified = bool(signer) and _ssh_verify(raw, sig_path, signers, kernel.NAMESPACE, signer)
            if drifted:
                verdict, entry_ok = "drifted", False
            elif verified:
                verdict, entry_ok = "signed", True
            else:
                verdict, entry_ok = "unsigned", False

        attestations.append({
            "verdict": verdict, "drifted": drifted,
            "identity": stmt.get("identity"), "root": stmt.get("root"),
        })
        if not entry_ok:
            ok = False

    return {"ok": ok, "attestations": attestations}


# ----------------------------------------------------------------- ceremony --

def review_packet(d: str, ws: str = None) -> dict:
    """What a human reviews before signing: the root, the folded
    signature-chain node, the cold audit, and -- for a composed claim --
    the deep chain audit. Never raises; `sign` reads this to decide."""
    manifest = kernel.read_manifest(d)
    audited = kernel.audit(d)
    comp_links = registry.components(d)
    deep = None
    if comp_links:
        deep = registry.audit_deep(d, ws)
    pkt = {
        "root": manifest["root"],
        "sign_root": registry.sign_root(d, ws) if audited["ok"] else None,
        "build_digest": kernel.build_digest(d),
        "audit": audited,
        "proof": manifest.get("proof"),
        "components": comp_links,
    }
    if deep is not None:
        pkt["deep_audit"] = deep
    return pkt


def sign(d: str, key: str, identity: str, ws: str = None) -> dict:
    """The signing ceremony: refuse a claim whose own verdicts do not
    reproduce, or -- naming it -- a composed claim whose chain does not
    re-earn; else sign the review packet and the chain root."""
    pkt = review_packet(d, ws)
    if not pkt["audit"]["ok"]:
        raise kernel.ClaimError(
            f"sign refuses a claim whose verdicts do not reproduce: {pkt['audit']}")
    if pkt.get("deep_audit") is not None and not pkt["deep_audit"]["ok"]:
        raise kernel.ClaimError(
            f"sign refuses a composed claim whose chain does not re-earn: {pkt['deep_audit']}")

    manifest = kernel.read_manifest(d)
    packet_doc = {
        "root": manifest["root"],
        "sign_root": pkt["sign_root"],
        "build_digest": pkt["build_digest"],
        "audit": {"ok": pkt["audit"]["ok"]},
        "proof": manifest.get("proof"),
    }
    packet_digest = hashlib.sha256(
        json.dumps(packet_doc, sort_keys=True).encode("utf-8")).hexdigest()

    prefix = manifest["root"]
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    packet_path = os.path.join(sign_dir, f"{prefix}.packet.json")
    _util.write_json(packet_path, packet_doc)

    stmt = {
        "ceremony": CEREMONY,
        "identity": identity,
        "root": manifest["root"],
        "packet_digest": packet_digest,
        "build_digest": pkt["build_digest"],
        "proof_recorded": bool(manifest.get("proof")),
        "when": _util.stamp(),
    }
    stmt_path = os.path.join(sign_dir, f"{prefix}.sign.json")
    _util.write_json(stmt_path, stmt)
    _ssh_sign(key, kernel.SIGN_NAMESPACE, stmt_path)

    return {
        "ceremony": CEREMONY,
        "packet": os.path.join(kernel.SIGN_DIR, f"{prefix}.packet.json"),
        "statement": os.path.join(kernel.SIGN_DIR, f"{prefix}.sign.json"),
        "signature": os.path.join(kernel.SIGN_DIR, f"{prefix}.sign.json.sig"),
        "sign_root": pkt["sign_root"],
    }


def sign_check(d: str, ws: str = None, signers: str = None) -> dict:
    """Every signing statement kept beside `d`: whether its signer is
    trusted by `signers`, and whether the stored review packet it binds
    to -- byte for byte, via the packet digest -- still holds."""
    manifest = kernel.read_manifest(d)
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    authorizations = []
    ok = True
    if not os.path.isdir(sign_dir):
        return {"ok": False, "authorizations": []}

    for fn in sorted(os.listdir(sign_dir)):
        if not fn.endswith(".sign.json"):
            continue
        stmt_path = os.path.join(sign_dir, fn)
        sig_path = stmt_path + ".sig"
        prefix = fn[: -len(".sign.json")]
        packet_path = os.path.join(sign_dir, prefix + ".packet.json")

        try:
            with open(stmt_path, "rb") as f:
                stmt_bytes = f.read()
            stmt = json.loads(stmt_bytes)
        except (OSError, ValueError):
            ok = False
            authorizations.append({"verdict": "malformed"})
            continue

        signer = stmt.get("identity")
        proof_recorded = bool(stmt.get("proof_recorded"))
        verdict = "unauthorized"
        packet_holds = False

        if signer and _ssh_verify(stmt_bytes, sig_path, signers, kernel.SIGN_NAMESPACE, signer):
            verdict = "authorized"
            if os.path.isfile(packet_path):
                try:
                    with open(packet_path, "r", encoding="utf-8") as f:
                        packet = json.load(f)
                    packet_digest = hashlib.sha256(
                        json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()
                    packet_holds = (
                        packet_digest == stmt.get("packet_digest")
                        and packet.get("build_digest") == kernel.build_digest(d)
                        and packet.get("proof") == manifest.get("proof")
                    )
                except (OSError, ValueError):
                    packet_holds = False

        row = {"identity": signer, "verdict": verdict,
               "packet_holds": packet_holds, "proof_recorded": proof_recorded}
        authorizations.append(row)
        if verdict != "authorized" or not packet_holds:
            ok = False

    return {"ok": ok, "authorizations": authorizations}
