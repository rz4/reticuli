"""attest: a keyholder's signed statement of a build (spec/layers.md "exchange").

`attest`/`check` are a lightweight claim-level attestation: sign the
current build, and check later whether the signed bytes still match disk
(a drifted build refuses the old attestation). `sign`/`sign_check` are the
accountable ceremony: refuse a claim whose verdicts do not reproduce
(shallow for an uncomposed claim, the composed verdict for one that
declares components), sign the chain root and a review packet, and verify
against a recomputed chain -- SIGNED means AUTHORIZED (a trusted signer)
AND PROVEN (a recorded proof), the two facts coupled through the packet.
"""
import hashlib
import json
import os
import subprocess

from reticuli import _util, kernel, registry

ATTEST = ".reticuli/attest"
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _verify_sig(signers_path, namespace, identity_str, sig_path, data: bytes) -> bool:
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", signers_path, "-I", identity_str,
             "-n", namespace, "-s", sig_path],
            input=data, capture_output=True, timeout=30, check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def _sign_file(key: str, namespace: str, path: str) -> None:
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
                   check=True, capture_output=True)


def _own_ok(d: str) -> bool:
    return kernel.audit(d)["ok"]


def _composed_ok(d: str, ws=None):
    comps = registry.components_of(d)
    if not comps:
        return True, None
    deep = registry.audit_deep(d, ws)
    return deep["ok"], deep


# -- lightweight attestation: a signed statement of this build -------------

def attest(d: str, key: str, identity_str: str) -> dict:
    """Sign the current build: refuses a claim whose verdicts (shallow, or
    composed if it declares components) do not reproduce -- never
    notarizes a carried verdict."""
    v = kernel.verify(d)
    comps = registry.components_of(d)
    if comps:
        a = registry.audit_deep(d)
        a_ok = a["ok"]
    else:
        a_ok = kernel.audit(d)["ok"]
    if not v["ok"] or not a_ok:
        raise kernel.ClaimError("attest refuses: this claim's verdicts do not reproduce")

    root = v["root"]
    digest = kernel.build_digest(d)
    statement = {"identity": identity_str, "root": root, "build_digest": digest,
                 "when": _util.stamp()}
    stmt_dir = os.path.join(d, ATTEST)
    os.makedirs(stmt_dir, exist_ok=True)
    stmt_rel = ATTEST + "/" + root[:16] + ".json"
    stmt_path = os.path.join(d, stmt_rel)
    with open(stmt_path, "wb") as f:
        f.write(json.dumps(statement, sort_keys=True).encode())
    _sign_file(key, kernel.NAMESPACE, stmt_path)
    return {"signature": stmt_rel + ".sig", "statement": stmt_rel, "root": root}


def check(d: str, signers=None) -> dict:
    """Whether every attestation under `d` is intact, undrifted, and (with
    `signers` given) verifies against the anchor."""
    stmt_dir = os.path.join(d, ATTEST)
    attestations = []
    ok_overall = True
    found_any = False
    if os.path.isdir(stmt_dir):
        for fname in sorted(os.listdir(stmt_dir)):
            if not fname.endswith(".json"):
                continue
            found_any = True
            stmt_path = os.path.join(stmt_dir, fname)
            sig_path = stmt_path + ".sig"
            with open(stmt_path, "rb") as f:
                raw = f.read()
            try:
                stmt = json.loads(raw)
            except ValueError:
                attestations.append({"verdict": "malformed", "drifted": False})
                ok_overall = False
                continue
            try:
                current_digest = kernel.build_digest(d)
            except kernel.ClaimError:
                current_digest = None
            drifted = stmt.get("build_digest") != current_digest
            if signers is not None:
                verified = os.path.isfile(sig_path) and os.path.isfile(signers) and \
                    _verify_sig(signers, kernel.NAMESPACE, stmt.get("identity", ""), sig_path, raw)
                verdict = "signed" if verified else "unverified"
                ok_this = verified and not drifted
            else:
                canonical = json.dumps(stmt, sort_keys=True).encode()
                intact = canonical == raw
                verdict = "unsigned" if intact else "tampered"
                ok_this = intact and not drifted
            attestations.append({"verdict": verdict, "drifted": drifted})
            if not ok_this:
                ok_overall = False
    return {"ok": ok_overall and found_any, "attestations": attestations}


# -- the signing ceremony: authorized AND proven ----------------------------

def review_packet(d: str, ws=None) -> dict:
    """What a signer would review: identity, the signature-chain root, the
    composed (or shallow) audit, and whether a proof is currently recorded."""
    v = kernel.verify(d)
    ok, deep = _composed_ok(d, ws)
    audit_result = deep if deep is not None else kernel.audit(d)
    manifest = kernel.read_manifest(d)
    return {
        "root": v["root"],
        "build_digest": kernel.build_digest(d),
        "sign_root": registry.sign_root(d, ws),
        "audit": audit_result,
        "proof": manifest.get("proof"),
    }


def sign(d: str, key: str, identity_str: str, ws=None) -> dict:
    """The ceremony: refuse an unreproduced own verdict, refuse a composed
    claim whose chain does not re-earn, then sign the chain root and a
    review packet."""
    if not _own_ok(d):
        raise kernel.ClaimError("sign refuses: this claim's own verdicts do not reproduce")
    ok, _deep = _composed_ok(d, ws)
    if not ok:
        raise kernel.ClaimError("sign refuses: the composed verdict does not re-earn across the chain")

    pkt = review_packet(d, ws)
    manifest = kernel.read_manifest(d)
    packet = {"root": pkt["root"], "build_digest": pkt["build_digest"],
              "sign_root": pkt["sign_root"], "proof": manifest.get("proof")}
    packet_bytes = json.dumps(packet, sort_keys=True).encode()
    packet_digest = hashlib.sha256(packet_bytes).hexdigest()

    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(sign_dir, exist_ok=True)
    prefix = pkt["root"][:16]
    sign_rel = os.path.relpath(sign_dir, d)
    packet_rel = sign_rel + "/" + prefix + ".packet.json"
    stmt_rel = sign_rel + "/" + prefix + ".sign.json"
    packet_path = os.path.join(d, packet_rel)
    stmt_path = os.path.join(d, stmt_rel)

    with open(packet_path, "wb") as f:
        f.write(packet_bytes)
    statement = {"identity": identity_str, "root": pkt["root"], "packet_digest": packet_digest,
                 "ceremony": CEREMONY, "when": _util.stamp()}
    with open(stmt_path, "wb") as f:
        f.write(json.dumps(statement, sort_keys=True).encode())
    _sign_file(key, kernel.SIGN_NAMESPACE, stmt_path)

    return {"ceremony": CEREMONY, "signature": stmt_rel + ".sig", "statement": stmt_rel,
            "packet": packet_rel, "sign_root": pkt["sign_root"], "root": pkt["root"]}


def sign_check(d: str, ws=None, signers=None) -> dict:
    """Whether every authorization statement under `d` is signed by a
    trusted key over a packet that still matches the live claim."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    authorizations = []
    ok_overall = True
    found_any = False
    if os.path.isdir(sign_dir):
        for fname in sorted(os.listdir(sign_dir)):
            if not fname.endswith(".sign.json"):
                continue
            found_any = True
            stmt_path = os.path.join(sign_dir, fname)
            sig_path = stmt_path + ".sig"
            with open(stmt_path, "rb") as f:
                stmt_bytes = f.read()
            try:
                stmt = json.loads(stmt_bytes)
            except ValueError:
                authorizations.append({"verdict": "malformed", "packet_holds": False,
                                        "proof_recorded": False})
                ok_overall = False
                continue

            prefix = fname[: -len(".sign.json")]
            packet_path = os.path.join(sign_dir, prefix + ".packet.json")
            packet_holds = False
            proof_recorded = False
            if os.path.isfile(packet_path):
                with open(packet_path, "rb") as f:
                    packet_bytes = f.read()
                if hashlib.sha256(packet_bytes).hexdigest() == stmt.get("packet_digest"):
                    try:
                        packet = json.loads(packet_bytes)
                        manifest = kernel.read_manifest(d)
                        packet_holds = packet.get("root") == manifest.get("root")
                        proof_recorded = bool(packet.get("proof")) and \
                            packet.get("proof") == manifest.get("proof")
                    except ValueError:
                        pass

            verified = False
            if signers and os.path.isfile(signers) and os.path.isfile(sig_path):
                verified = _verify_sig(signers, kernel.SIGN_NAMESPACE,
                                       stmt.get("identity", ""), sig_path, stmt_bytes)
            verdict = "authorized" if verified else "unauthorized"
            ok_this = verified and packet_holds
            authorizations.append({"verdict": verdict, "packet_holds": packet_holds,
                                    "proof_recorded": proof_recorded})
            if not ok_this:
                ok_overall = False
    return {"ok": ok_overall and found_any, "authorizations": authorizations}
