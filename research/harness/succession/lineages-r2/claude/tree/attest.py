"""attest: a keyholder's signed statement of a build (spec/layers.md).

`attest`/`check` are the plain form -- a keyholder states "this root, this
build, on this day" -- and refuse to notarize a claim whose verdicts do not
freshly reproduce (`kernel.audit`): never a carried verdict, and never a
broken one. `sign`/`sign_check` are the accountable ceremony: they refuse a
claim whose verdicts do not reproduce (audit), then sign a review packet
naming the chain root, the audit, and whether a proof is recorded --
SIGNED means AUTHORIZED (by a trusted signer) AND PROVEN (a recorded
proof), and the statement says which, so authorization is never mistaken
for proof. `kernel.phase` reads this same on-disk shape to decide
`sealed`/`signed`.

Stdlib only, plus the system `ssh-keygen` for the actual signing/verifying.
"""
import json
import os
import subprocess

from . import _util, kernel, registry

ATTEST = ".reticuli/attest"

CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _ssh_sign(keypath: str, namespace: str, path: str) -> None:
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)  # ssh-keygen prompts before overwriting one
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", keypath, "-n", namespace, path],
                   check=True, capture_output=True)


def _ssh_verify(allowed_signers: str, identity: str, namespace: str,
                 sig_path: str, data: bytes) -> bool:
    if not os.path.isfile(allowed_signers) or not os.path.isfile(sig_path):
        return False
    try:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", identity,
             "-n", namespace, "-s", sig_path],
            input=data, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _ssh_intact(namespace: str, sig_path: str, data: bytes) -> bool:
    """Whether a signature is structurally intact over `data` -- checked
    against the key the signature itself carries, anchored to no identity
    (`ssh-keygen -Y check-novalidate`): "this signature is real", without
    "and I trust who made it"."""
    if not os.path.isfile(sig_path):
        return False
    try:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "check-novalidate", "-n", namespace, "-s", sig_path],
            input=data, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


# ---------------------------------------------------------------------------
# the plain form: a statement about a build
# ---------------------------------------------------------------------------

def attest(d: str, keypath: str, identity: str) -> dict:
    """Sign a statement of `d`'s current build: refuses unless every verdict
    reproduces fresh from `d`'s own bytes (`kernel.audit`) -- never a
    carried verdict, never a broken claim."""
    aud = kernel.audit(d)
    if not aud["ok"]:
        raise kernel.ClaimError(
            f"attest refuses {d!r}: verdicts do not reproduce from present bytes")
    manifest = kernel.read_manifest(d)
    att_dir = os.path.join(d, ATTEST)
    os.makedirs(att_dir, exist_ok=True)

    statement = {
        "identity": identity,
        "root": manifest["root"],
        "build_digest": kernel.build_digest(d),
        "when": _util.stamp(),
    }
    stmt_path = os.path.join(att_dir, f"{identity}.json")
    _util.write_json(stmt_path, statement)
    _ssh_sign(keypath, kernel.NAMESPACE, stmt_path)

    return {"signature": os.path.relpath(stmt_path + ".sig", d),
            "statement": os.path.relpath(stmt_path, d)}


def check(d: str, signers: str = None) -> dict:
    """Read back every attestation under `d`: intact (signature verifies
    over unmodified bytes), drifted (intact, but the build has moved on --
    a different build under the same root), or signed (intact, and the
    signer is anchored in `signers`)."""
    try:
        v = kernel.verify(d)
    except kernel.ClaimError:
        v = {"ok": False}
    if not v.get("ok"):
        return {"ok": False, "attestations": []}
    current_root = v["root"]
    try:
        current_digest = kernel.build_digest(d)
    except kernel.ClaimError:
        current_digest = None

    att_dir = os.path.join(d, ATTEST)
    attestations = []
    if os.path.isdir(att_dir):
        for name in sorted(os.listdir(att_dir)):
            if not name.endswith(".json"):
                continue
            stmt_path = os.path.join(att_dir, name)
            sig_path = stmt_path + ".sig"
            entry = {"identity": name[: -len(".json")], "verdict": "invalid", "drifted": False}
            try:
                with open(stmt_path, "rb") as f:
                    stmt_bytes = f.read()
                statement = json.loads(stmt_bytes)
            except (OSError, json.JSONDecodeError):
                statement = None
            if isinstance(statement, dict) and _ssh_intact(kernel.NAMESPACE, sig_path, stmt_bytes):
                drifted = (statement.get("root") != current_root
                           or statement.get("build_digest") != current_digest)
                entry["drifted"] = drifted
                if drifted:
                    entry["verdict"] = "drifted"
                else:
                    entry["verdict"] = "intact"
                    identity_name = statement.get("identity")
                    if signers and isinstance(identity_name, str) and \
                       _ssh_verify(signers, identity_name, kernel.NAMESPACE, sig_path, stmt_bytes):
                        entry["verdict"] = "signed"
            attestations.append(entry)

    if signers:
        ok = bool(attestations) and all(a["verdict"] == "signed" for a in attestations)
    else:
        ok = bool(attestations) and all(a["verdict"] in ("intact", "signed") for a in attestations)
    return {"ok": ok, "attestations": attestations}


# ---------------------------------------------------------------------------
# the ceremony: accountable authorization over the chain
# ---------------------------------------------------------------------------

def review_packet(d: str, ws: str = None) -> dict:
    """What a keyholder reviews before authorizing: the claim's own root and
    audit, and the chain root folding every declared component beneath it
    (`registry.sign_root`). Carries `proof` (possibly `None`) so a reviewer
    always sees where on the ladder -- authorized-only or authorized-and-
    proven -- this signature will land."""
    manifest = kernel.read_manifest(d)
    return {
        "root": manifest["root"],
        "build_digest": kernel.build_digest(d),
        "sign_root": registry.sign_root(d, ws),
        "audit": kernel.audit(d),
        "proof": manifest.get("proof"),
    }


def sign(d: str, keypath: str, identity: str, ws: str = None) -> dict:
    """The signing ceremony: refuses a claim whose verdicts do not reproduce
    (audit), then signs a review packet and a statement naming whether a
    proof is recorded -- authorization is never mistaken for proof."""
    aud = kernel.audit(d)
    if not aud["ok"]:
        raise kernel.ClaimError(
            f"sign refuses {d!r}: verdicts do not reproduce from present bytes")

    manifest = kernel.read_manifest(d)
    pkt = review_packet(d, ws=ws)
    proof_recorded = bool(manifest.get("proof"))

    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(sign_dir, exist_ok=True)
    packet_path = os.path.join(sign_dir, f"{identity}.packet.json")
    _util.write_json(packet_path, pkt)
    with open(packet_path, "rb") as f:
        packet_bytes = f.read()

    statement = {
        "identity": identity,
        "ceremony": CEREMONY,
        "root": pkt["root"],
        "build_digest": pkt["build_digest"],
        "packet_digest": _util.hash_bytes(packet_bytes),
        "proof_recorded": proof_recorded,
        "when": _util.stamp(),
    }
    stmt_path = os.path.join(sign_dir, f"{identity}.sign.json")
    _util.write_json(stmt_path, statement)
    _ssh_sign(keypath, kernel.SIGN_NAMESPACE, stmt_path)

    return {
        "ceremony": CEREMONY,
        "signature": os.path.relpath(stmt_path + ".sig", d),
        "statement": os.path.relpath(stmt_path, d),
        "packet": os.path.relpath(packet_path, d),
    }


def sign_check(d: str, ws: str = None, signers: str = None) -> dict:
    """Read back every authorization ceremony under `d`: authorized when
    the statement's signature verifies against `signers` AND the statement's
    recorded digest still binds the exact packet on disk -- a forged or
    missing packet, or a tampered statement, refuses."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    authorizations = []
    if os.path.isdir(sign_dir):
        for name in sorted(os.listdir(sign_dir)):
            if not name.endswith(".sign.json"):
                continue
            prefix = name[: -len(".sign.json")]
            stmt_path = os.path.join(sign_dir, name)
            sig_path = stmt_path + ".sig"
            packet_path = os.path.join(sign_dir, f"{prefix}.packet.json")
            row = {"identity": prefix, "verdict": "unauthorized",
                   "packet_holds": False, "proof_recorded": False}
            if os.path.isfile(stmt_path) and os.path.isfile(sig_path):
                with open(stmt_path, "rb") as f:
                    stmt_bytes = f.read()
                try:
                    statement = json.loads(stmt_bytes)
                except json.JSONDecodeError:
                    statement = None
                if isinstance(statement, dict):
                    row["proof_recorded"] = bool(statement.get("proof_recorded"))
                    if os.path.isfile(packet_path):
                        with open(packet_path, "rb") as f:
                            packet_bytes = f.read()
                        row["packet_holds"] = (
                            _util.hash_bytes(packet_bytes) == statement.get("packet_digest"))
                    identity_name = statement.get("identity")
                    verified = bool(signers) and isinstance(identity_name, str) and \
                        _ssh_verify(signers, identity_name, kernel.SIGN_NAMESPACE, sig_path, stmt_bytes)
                    if verified and row["packet_holds"]:
                        row["verdict"] = "authorized"
            authorizations.append(row)
    ok = bool(authorizations) and all(
        a["verdict"] == "authorized" and a["packet_holds"] for a in authorizations)
    return {"ok": ok, "authorizations": authorizations}
