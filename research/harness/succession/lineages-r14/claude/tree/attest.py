"""Attestation: a keyholder's signed statement of a build (spec/layers.md).

Two distinct ceremonies live here. `attest`/`check` are lightweight
testimony: sign only a build whose verdicts reproduce from their own bytes
-- never a carried verdict -- and refuse a drifted or tampered statement.
`sign`/`sign_check` are the accountable authorization ceremony: they write
the `.reticuli/mint` statement and review packet that `kernel.phase` (the
kernel's own, already-pinned reader) consults to decide whether a claim is
merely authorized or fully SIGNED -- authorized by a trusted key AND proven
by a recorded crosscheck.
"""
import hashlib
import json
import os
import subprocess

from reticuli import kernel, _util, registry

ATTEST = ".reticuli/attest"
_CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True).encode("utf-8")


def _slug(identity: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in identity) or "signer"


def _ssh_sign(path: str, key: str, namespace: str) -> None:
    # ssh-keygen -Y sign prompts before overwriting an existing `.sig`; a
    # re-sign over the same statement name must remove the stale one first,
    # or the prompt (answered by nothing, since stdin carries no input for
    # this subprocess) hangs or silently refuses.
    sig_path = path + ".sig"
    if os.path.exists(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
                    check=True, capture_output=True)


def _ssh_verify(data: bytes, sig_path: str, namespace: str, signers: str, identity) -> bool:
    if not signers or not os.path.isfile(signers) or not os.path.isfile(sig_path):
        return False
    argv = ["ssh-keygen", "-Y", "verify", "-f", signers, "-n", namespace,
            "-s", sig_path, "-I", identity or ""]
    try:
        done = subprocess.run(argv, input=data, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


# ===========================================================================
# attest / check: testimony about one build
# ===========================================================================

def attest(d: str, key: str, identity: str) -> dict:
    """Sign a statement of THIS build. Refuses a claim whose verdicts do
    not reproduce from its own present bytes -- an attestation is never
    notarized over a carried verdict."""
    audited = kernel.audit(d)
    if not audited["ok"]:
        raise kernel.ClaimError(f"attest refuses an unearned claim: {audited}")

    root = kernel.verify(d)["root"]
    digest = kernel.build_digest(d)
    statement = {"identity": identity, "root": root, "build_digest": digest,
                 "when": _util.stamp()}

    attest_dir = os.path.join(d, ATTEST)
    os.makedirs(attest_dir, exist_ok=True)
    stem = _slug(identity)
    stmt_rel = os.path.join(ATTEST, f"{stem}.json")
    sig_rel = stmt_rel + ".sig"
    stmt_path = os.path.join(d, stmt_rel)
    with open(stmt_path, "wb") as f:
        f.write(_canonical(statement))
    _ssh_sign(stmt_path, key, kernel.NAMESPACE)

    return {"statement": stmt_rel, "signature": sig_rel, "root": root}


def _statements(d: str) -> list:
    attest_dir = os.path.join(d, ATTEST)
    if not os.path.isdir(attest_dir):
        return []
    return [os.path.join(ATTEST, name) for name in sorted(os.listdir(attest_dir))
            if name.endswith(".json")]


def check(d: str, signers: str = None) -> dict:
    """Is each attestation under `d` intact (its bytes are exactly its own
    canonical serialization), non-drifted (its build digest still matches
    the bytes present), and -- given `signers` -- signed by an anchored
    identity?"""
    current_root = kernel.verify(d)["root"]
    current_digest = kernel.build_digest(d)

    results = []
    for stmt_rel in _statements(d):
        stmt_path = os.path.join(d, stmt_rel)
        sig_path = stmt_path + ".sig"
        entry = {"statement": stmt_rel}
        try:
            with open(stmt_path, "rb") as f:
                raw = f.read()
            statement = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            results.append({**entry, "verdict": "tampered", "ok": False, "drifted": False})
            continue

        intact = isinstance(statement, dict) and _canonical(statement) == raw
        root_matches = intact and statement.get("root") == current_root
        drifted = root_matches and statement.get("build_digest") != current_digest
        entry_ok = root_matches and not drifted

        if entry_ok and signers:
            if _ssh_verify(raw, sig_path, kernel.NAMESPACE, signers, statement.get("identity")):
                verdict = "signed"
            else:
                verdict = "unverified"
                entry_ok = False
        elif entry_ok:
            verdict = "intact"
        elif drifted:
            verdict = "drifted"
        else:
            verdict = "tampered"

        entry.update(verdict=verdict, ok=entry_ok, drifted=bool(drifted))
        results.append(entry)

    return {"ok": bool(results) and all(r["ok"] for r in results), "attestations": results}


# ===========================================================================
# the signing ceremony: accountable authorization over a proven chain
# ===========================================================================

def review_packet(d: str, ws: str) -> dict:
    """What a keyholder reviews before signing: the claim's identity, the
    DAG's folded sign_root, a fresh cold audit, and whether a proof is
    currently recorded -- the reviewer sees the whole ladder, not just the
    final rung."""
    manifest = kernel.read_manifest(d)
    audited = kernel.audit(d)
    return {
        "root": manifest["root"],
        "build_digest": kernel.build_digest(d),
        "sign_root": registry.sign_root(d, ws),
        "audit": audited,
        "proof": manifest.get("proof"),
    }


def sign(d: str, key: str, identity: str, ws: str) -> dict:
    """Authorize `d`'s current root: refuses unless its verdicts reproduce
    now, writes the review packet reviewed and a statement naming whether a
    proof was recorded at the time of signing, and signs the statement in
    the mint namespace. `kernel.phase` decides SIGNED from these files plus
    `manifest['proof']` -- a trusted authorization with no recorded proof
    stays merely `sealed` to any verifier."""
    packet = review_packet(d, ws)
    if not packet["audit"]["ok"]:
        raise kernel.ClaimError(f"sign refuses a claim whose verdicts do not reproduce: {packet['audit']}")

    manifest = kernel.read_manifest(d)
    root = manifest["root"]
    proof_recorded = bool(manifest.get("proof"))

    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    os.makedirs(sign_dir, exist_ok=True)
    stem = _slug(identity)
    packet_rel = os.path.join(kernel.SIGN_DIR, f"{stem}.packet.json")
    stmt_rel = os.path.join(kernel.SIGN_DIR, f"{stem}.sign.json")
    sig_rel = stmt_rel + ".sig"

    packet_bytes = _canonical(packet)
    with open(os.path.join(d, packet_rel), "wb") as f:
        f.write(packet_bytes)
    packet_digest = hashlib.sha256(packet_bytes).hexdigest()

    statement = {
        "ceremony": _CEREMONY,
        "identity": identity,
        "root": root,
        "build_digest": packet["build_digest"],
        "proof_recorded": proof_recorded,
        "packet_digest": packet_digest,
        "when": _util.stamp(),
    }
    stmt_path = os.path.join(d, stmt_rel)
    with open(stmt_path, "wb") as f:
        f.write(_canonical(statement))
    _ssh_sign(stmt_path, key, kernel.SIGN_NAMESPACE)

    return {"ceremony": _CEREMONY, "statement": stmt_rel, "signature": sig_rel,
            "packet": packet_rel, "root": root}


def sign_check(d: str, ws: str, signers: str = None) -> dict:
    """The ceremony's own integrity: is each statement signed by an
    anchored identity, and does the packet it names still hash to what was
    signed and still describe the claim's current root and build digest?
    Distinct from `kernel.phase`: an authorization can be intact here --
    and so report `ok` -- while the claim has no recorded proof and is
    therefore not yet SIGNED."""
    current_root = kernel.verify(d)["root"]
    current_digest = kernel.build_digest(d)
    sign_dir = os.path.join(d, kernel.SIGN_DIR)

    rows = []
    if os.path.isdir(sign_dir):
        for fname in sorted(os.listdir(sign_dir)):
            if not fname.endswith(".sign.json"):
                continue
            stmt_path = os.path.join(sign_dir, fname)
            sig_path = stmt_path + ".sig"
            try:
                with open(stmt_path, "rb") as f:
                    stmt_bytes = f.read()
                stmt = json.loads(stmt_bytes)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(stmt, dict):
                continue

            identity = stmt.get("identity")
            verified = bool(signers) and _ssh_verify(
                stmt_bytes, sig_path, kernel.SIGN_NAMESPACE, signers, identity)
            root_matches = stmt.get("root") == current_root
            authorized = verified and root_matches

            packet_holds = False
            packet_name = fname[: -len(".sign.json")] + ".packet.json"
            packet_path = os.path.join(sign_dir, packet_name)
            if os.path.isfile(packet_path):
                with open(packet_path, "rb") as f:
                    packet_bytes = f.read()
                if hashlib.sha256(packet_bytes).hexdigest() == stmt.get("packet_digest"):
                    try:
                        packet = json.loads(packet_bytes)
                    except json.JSONDecodeError:
                        packet = None
                    if isinstance(packet, dict) and packet.get("root") == current_root \
                            and packet.get("build_digest") == current_digest:
                        packet_holds = True

            rows.append({
                "identity": identity,
                "verdict": "authorized" if authorized else "unverified",
                "packet_holds": packet_holds,
                "proof_recorded": bool(stmt.get("proof_recorded")),
            })

    ok = bool(rows) and any(r["verdict"] == "authorized" and r["packet_holds"] for r in rows)
    return {"ok": ok, "authorizations": rows}
