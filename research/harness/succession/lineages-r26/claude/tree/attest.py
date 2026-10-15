"""Attestation: a keyholder's signed statement of a build.

`attest`/`check` are the plain attestation -- "I looked at this build and
its verdicts reproduced", refusing to notarize a carried verdict (a gate
that does not re-earn) or a broken claim (identity itself does not hold).
`sign`/`sign_check`/`review_packet` are the signing CEREMONY: accountable
authorization over a claim's whole chain, landing exactly the artifacts
`reticuli.kernel`'s own `phase()` looks for under `SIGN_DIR` -- SIGNED
means AUTHORIZED (by a trusted signer) AND PROVEN (a recorded proof), and
a composed claim's ceremony re-earns the COMPOSED verdict (the deep audit)
before endorsing the chain, never just its own gates.

Only `reticuli.kernel`'s pinned public surface, plus `reticuli._util` and
`reticuli.registry`, are consumed.
"""
import hashlib
import os
import subprocess

from reticuli import kernel
from . import _util
from . import registry

ATTEST = ".reticuli/attest"

_CEREMONY = "RETICULI_CLAIM_BASIN_V1"


# -- ssh signature primitives --------------------------------------------------


def _ssh_sign(key: str, namespace: str, path: str) -> None:
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
                   check=True, capture_output=True)


def _ssh_verify(data: bytes, signature_path: str, namespace: str,
                 allowed_signers: str, principal) -> bool:
    if not principal or not os.path.isfile(signature_path) or not os.path.isfile(allowed_signers):
        return False
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", principal,
             "-n", namespace, "-s", signature_path],
            input=data, capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


# ==============================================================================
# attest / check: a signed statement of this build
# ==============================================================================


def attest(d: str, key: str, principal: str) -> dict:
    """Sign a statement of this build -- never a carried verdict: the
    claim's identity must hold, and every gate must re-earn, cold."""
    ver = kernel.verify(d)
    if not ver["ok"]:
        raise kernel.ClaimError("attest refuses a claim whose identity does not hold")
    au = kernel.audit(d)
    if not au.get("ok"):
        raise kernel.ClaimError("attest refuses a claim whose verdicts do not reproduce")

    manifest = kernel.read_manifest(d)
    stmt = {"root": ver["root"], "build_digest": kernel.build_digest(d),
            "name": manifest.get("name"), "identity": principal, "when": _util.stamp()}

    att_dir = os.path.join(d, ATTEST)
    os.makedirs(att_dir, exist_ok=True)
    stmt_path = os.path.join(att_dir, "statement.json")
    _util.write_json(stmt_path, stmt)
    _ssh_sign(key, kernel.NAMESPACE, stmt_path)

    return {"signature": os.path.relpath(stmt_path + ".sig", d),
            "statement": os.path.relpath(stmt_path, d)}


def check(d: str, signers: str = None) -> dict:
    """Whether this build's attestation(s) still name the present bytes,
    and (with an anchor) whether the signer is one the anchor trusts."""
    att_dir = os.path.join(d, ATTEST)
    rows = []
    if os.path.isdir(att_dir):
        for fn in sorted(os.listdir(att_dir)):
            if not fn.endswith(".json"):
                continue
            stmt_path = os.path.join(att_dir, fn)
            sig_path = stmt_path + ".sig"
            try:
                stmt = _util.read_json(stmt_path)
            except kernel.ClaimError:
                rows.append({"drifted": True, "verdict": "corrupt"})
                continue

            try:
                ver = kernel.verify(d)
                live_bd = kernel.build_digest(d)
            except kernel.ClaimError:
                ver, live_bd = {"ok": False, "root": None}, None

            drifted = (not ver["ok"]) or stmt.get("root") != ver.get("root") \
                or stmt.get("build_digest") != live_bd
            entry = {"root": stmt.get("root"), "drifted": drifted,
                    "identity": stmt.get("identity")}

            if signers and os.path.isfile(signers):
                with open(stmt_path, "rb") as f:
                    stmt_bytes = f.read()
                principal = stmt.get("identity")
                sig_ok = _ssh_verify(stmt_bytes, sig_path, kernel.NAMESPACE, signers, principal)
                if not sig_ok:
                    entry["verdict"] = "invalid"
                elif drifted:
                    entry["verdict"] = "drifted"
                else:
                    entry["verdict"] = "signed"
            else:
                entry["verdict"] = "drifted" if drifted else "unsigned"
            rows.append(entry)

    ok = bool(rows) and all(
        not r.get("drifted") and r.get("verdict") not in ("invalid", "corrupt") for r in rows
    )
    return {"ok": ok, "attestations": rows}


# ==============================================================================
# the signing ceremony: accountable authorization over the chain
# ==============================================================================


def review_packet(d: str, ws: str = None) -> dict:
    """What a keyholder reviews before signing: identity, the folded
    sign-root, the own-gate audit, and (composed claims) the deep audit."""
    ws = ws or d
    ver = kernel.verify(d)
    au = kernel.audit(d)

    overall_ok = bool(au.get("ok"))
    layers = []
    if registry.components_of(d):
        deep = registry.audit_deep(d, ws)
        overall_ok = overall_ok and deep.get("ok", False)
        layers = deep.get("layers", [])

    return {
        "root": ver["root"],
        "sign_root": registry.sign_root(d, ws),
        "build_digest": kernel.build_digest(d),
        "audit": {"ok": overall_ok, "gates": au.get("gates", []), "layers": layers},
        "proof": registry.proof_of(d),
    }


def sign(d: str, key: str, principal: str, ws: str = None) -> dict:
    """The ceremony: refuses a claim whose own verdicts do not reproduce,
    or (composed) whose chain does not re-earn; signs the folded chain
    root and the review packet, for `kernel.phase` to recognize."""
    ws = ws or d
    ver = kernel.verify(d)
    if not ver["ok"]:
        raise kernel.ClaimError("sign refuses a claim whose identity does not hold")
    au = kernel.audit(d)
    if not au.get("ok"):
        raise kernel.ClaimError("sign must refuse a claim whose verdicts do not reproduce")

    if registry.components_of(d):
        deep = registry.audit_deep(d, ws)
        if not deep.get("ok"):
            raise kernel.ClaimError(
                "sign refuses: the composed verdict does not re-earn across the chain")

    sign_root_value = registry.sign_root(d, ws)
    live_root = ver["root"]
    live_bd = kernel.build_digest(d)
    proof = registry.proof_of(d)

    packet = {"root": live_root, "build_digest": live_bd,
              "sign_root": sign_root_value, "proof": proof}

    mint_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(mint_dir, exist_ok=True)
    packet_path = os.path.join(mint_dir, "sign.packet.json")
    _util.write_json(packet_path, packet)
    with open(packet_path, "rb") as f:
        packet_bytes = f.read()
    packet_digest = hashlib.sha256(packet_bytes).hexdigest()

    stmt = {"ceremony": _CEREMONY, "identity": principal, "root": live_root,
            "sign_root": sign_root_value, "packet_digest": packet_digest,
            "proof_recorded": bool(proof), "when": _util.stamp()}
    stmt_path = os.path.join(mint_dir, "sign.sign.json")
    _util.write_json(stmt_path, stmt)
    _ssh_sign(key, kernel.SIGN_NAMESPACE, stmt_path)

    return {"ceremony": _CEREMONY,
            "signature": os.path.relpath(stmt_path + ".sig", d),
            "statement": os.path.relpath(stmt_path, d),
            "packet": os.path.relpath(packet_path, d),
            "sign_root": sign_root_value}


def sign_check(d: str, ws: str = None, signers: str = None) -> dict:
    """Whether the ceremony's statement is authorized (a trusted signer)
    and its packet holds (the exact bytes the signer reviewed)."""
    mint_dir = os.path.join(d, kernel.SIGN_DIR)
    rows = []
    if os.path.isdir(mint_dir):
        for fn in sorted(os.listdir(mint_dir)):
            if not fn.endswith(".sign.json"):
                continue
            stmt_path = os.path.join(mint_dir, fn)
            sig_path = stmt_path + ".sig"
            packet_path = os.path.join(mint_dir, fn[: -len(".sign.json")] + ".packet.json")
            try:
                stmt = _util.read_json(stmt_path)
            except kernel.ClaimError:
                rows.append({"identity": None, "verdict": "corrupt",
                            "packet_holds": False, "proof_recorded": False})
                continue

            principal = stmt.get("identity")
            verified = False
            if signers and os.path.isfile(signers) and os.path.isfile(sig_path):
                with open(stmt_path, "rb") as f:
                    stmt_bytes = f.read()
                verified = _ssh_verify(stmt_bytes, sig_path, kernel.SIGN_NAMESPACE,
                                       signers, principal)

            packet_holds = False
            if os.path.isfile(packet_path):
                with open(packet_path, "rb") as f:
                    packet_bytes = f.read()
                packet_holds = hashlib.sha256(packet_bytes).hexdigest() == stmt.get("packet_digest")

            rows.append({"identity": principal,
                        "verdict": "authorized" if verified else "unauthorized",
                        "packet_holds": packet_holds,
                        "proof_recorded": bool(stmt.get("proof_recorded"))})

    ok = any(r["verdict"] == "authorized" and r["packet_holds"] for r in rows)
    return {"ok": ok, "authorizations": rows}
