"""Signed statements about a build -- for other parties.

Two different acts live here, and they sign in two different ssh
namespaces, because a signature made for one purpose must never be
presentable for another:

  * ATTESTATION (`reticuli`): "I obtained these results from these bytes."
    It speaks for a BUILD, so it records the concrete output digests;
    regenerating an implementation keeps the root (that freedom IS the
    equivalence class) and is a different build, which the old attestation
    must refuse.
  * AUTHORIZATION (`reticuli.mint`): "I, a keyholder, stand behind this
    chain." The ceremony re-earns the verdicts first -- and on a claim that
    declares components it re-earns the COMPOSED verdict, because the
    statement names the chain root.

Trust is verifier-relative throughout. With no reachable anchor,
`ssh-keygen` can only answer check-novalidate -- the signature is valid for
whatever key is embedded IN it -- so an unanchored check establishes that a
statement was signed, never whose it is. Unanchored, nothing is authorized
to you.
"""
import json
import os
import re
import shutil
import subprocess

from . import _util
from . import kernel

ATTEST = ".reticuli/attest"
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _slug(identity: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", identity or "anonymous").strip("-")


def _need_ssh() -> None:
    if not shutil.which("ssh-keygen"):
        raise kernel.ClaimError(
            "ssh-keygen is not on this host, so nothing here can be signed")


def _sign_file(path: str, key: str, namespace: str) -> str:
    _need_ssh()
    signature = path + ".sig"
    if os.path.isfile(signature):
        os.remove(signature)
    done = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
        capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise kernel.ClaimError(
            f"the signature could not be made: "
            f"{(done.stderr or done.stdout).strip()[-200:]}")
    return signature


def _intact(path: str, namespace: str) -> bool:
    """Self-consistent: these bytes carry this signature. It says nothing
    about WHOSE key made it."""
    if not shutil.which("ssh-keygen") or not os.path.isfile(path + ".sig"):
        return False
    with open(path, "rb") as handle:
        data = handle.read()
    done = subprocess.run(
        ["ssh-keygen", "-Y", "check-novalidate", "-n", namespace,
         "-s", path + ".sig"],
        input=data, capture_output=True, check=False)
    return done.returncode == 0


def _verified(path: str, identity: str, namespace: str,
              signers: str | None) -> bool:
    """Anchored: a key the VERIFIER named made this signature."""
    if not signers or not os.path.isfile(signers) or not identity or \
            not shutil.which("ssh-keygen") or \
            not os.path.isfile(path + ".sig"):
        return False
    with open(path, "rb") as handle:
        data = handle.read()
    done = subprocess.run(
        ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", identity,
         "-n", namespace, "-s", path + ".sig"],
        input=data, capture_output=True, check=False)
    return done.returncode == 0


def _anchor(signers: str | None = None):
    return signers or os.environ.get("RETICULI_SIGNERS")


def _outputs(claim: str) -> dict:
    """The concrete bytes an attestation speaks for."""
    parsed = kernel.load_recipe(claim)
    found = {}
    for step in parsed.get("step") or []:
        output = step.get("output")
        path = os.path.join(claim, output or "")
        if output and os.path.isfile(path):
            found[output] = _util.hash_file(path)
    return found


# -- attestation -----------------------------------------------------------
def attest(claim: str, key: str, identity: str) -> dict:
    """Sign a statement of the results THIS machine obtained.

    Never a carried verdict: the gates are re-run here, on these bytes, and
    a claim whose verdicts do not reproduce is refused rather than notarized.
    """
    checked = kernel.verify(claim)
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"the bytes present do not recompute to {claim}'s sealed root, "
            f"so there is nothing to attest to")
    verdict = kernel.audit(claim)
    if not verdict["ok"]:
        raise kernel.ClaimError(
            f"an attestation is never a carried verdict: {claim}'s gates do "
            f"not reproduce from the bytes present ({verdict['verdict']})")
    drawer = os.path.join(claim, ATTEST)
    os.makedirs(drawer, exist_ok=True)
    statement = {"identity": identity, "root": checked["root"],
                 "build_digest": kernel.build_digest(claim),
                 "outputs": _outputs(claim), "when": _util.stamp(),
                 "audit": verdict["verdict"], "namespace": kernel.NAMESPACE}
    path = os.path.join(drawer, f"{_slug(identity)}.attest.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(statement, sort_keys=True))
    signature = _sign_file(path, key, kernel.NAMESPACE)
    return {"statement": os.path.relpath(path, claim),
            "signature": os.path.relpath(signature, claim),
            "root": checked["root"], "identity": identity}


def check(claim: str, signers: str | None = None) -> dict:
    """Read every attestation on this claim and say what it still means."""
    drawer = os.path.join(claim, ATTEST)
    anchor = _anchor(signers)
    rows = []
    checked = kernel.verify(claim)
    digest = kernel.build_digest(claim)
    present = _outputs(claim)
    if os.path.isdir(drawer):
        for name in sorted(os.listdir(drawer)):
            if not name.endswith(".attest.json"):
                continue
            path = os.path.join(drawer, name)
            statement = _util.read_json(path)
            if not isinstance(statement, dict):
                rows.append({"statement": name, "verdict": "unreadable",
                             "drifted": True, "identity": None})
                continue
            identity = statement.get("identity")
            verified = _verified(path, identity, kernel.NAMESPACE, anchor)
            intact = _intact(path, kernel.NAMESPACE)
            drifted = (statement.get("build_digest") != digest or
                       statement.get("outputs") != present)
            rows.append({
                "statement": name, "identity": identity,
                "when": statement.get("when"),
                "names_this_root": statement.get("root") == checked["root"],
                "drifted": drifted,
                "verdict": "signed" if verified else (
                    "intact" if intact else "broken")})
    ok = bool(rows) and checked["ok"] and all(
        not r["drifted"] and r.get("names_this_root")
        and r["verdict"] in ("signed", "intact") for r in rows)
    return {"ok": ok, "anchored": bool(anchor), "root": checked["root"],
            "attestations": rows}


# -- the signing ceremony --------------------------------------------------
def review_packet(claim: str, ws: str | None = None) -> dict:
    """What a keyholder is asked to stand behind, assembled in one place."""
    from . import registry
    checked = kernel.verify(claim)
    manifest = kernel.read_manifest(claim)
    composed = bool(manifest.get("components"))
    verdict = registry.audit_deep(claim, ws=ws) if composed \
        else kernel.audit(claim)
    return {"root": checked["root"],
            "name": checked["name"],
            "build_digest": kernel.build_digest(claim),
            "sign_root": registry.sign_root(claim, ws),
            "audit": {"ok": bool(verdict["ok"]),
                      "verdict": verdict["verdict"],
                      "gates": [{"output": g["output"],
                                 "status": g["status"]}
                                for g in verdict.get("gates") or []],
                      "layers": [{"name": r["name"], "ok": r["ok"]}
                                 for r in verdict.get("layers") or []]},
            "composed": composed,
            "proof": manifest.get("proof"),
            "when": _util.stamp()}


def sign(claim: str, key: str, identity: str, ws: str | None = None) -> dict:
    """The ceremony: a human authorizes a chain, accountably.

    Refuses a claim whose verdicts do not reproduce -- and, where the claim
    declares components, whose COMPOSED verdict does not, because the
    statement names the chain root and an endorsement composes.
    """
    from . import registry
    checked = kernel.verify(claim)
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"{claim} does not recompute to its sealed root: nothing to "
            f"authorize")
    own = kernel.audit(claim)
    if not own["ok"]:
        raise kernel.ClaimError(
            f"the ceremony refuses a claim whose verdicts do not reproduce "
            f"({own['verdict']})")
    manifest = kernel.read_manifest(claim)
    if manifest.get("components"):
        deep = registry.audit_deep(claim, ws=ws)
        if not deep["ok"]:
            broken = [r["name"] for r in deep["layers"] if not r["ok"]]
            raise kernel.ClaimError(
                f"the composed verdict does not re-earn, so this chain "
                f"cannot be endorsed: {', '.join(broken) or 'a component'}")
    packet = review_packet(claim, ws=ws)
    drawer = os.path.join(claim, kernel.SIGN_DIR)
    os.makedirs(drawer, exist_ok=True)
    stem = os.path.join(drawer, _slug(identity))
    packet_bytes = json.dumps(packet, sort_keys=True).encode("utf-8")
    with open(stem + ".packet.json", "wb") as handle:
        handle.write(packet_bytes)
    statement = {"identity": identity, "root": checked["root"],
                 "sign_root": packet["sign_root"],
                 "packet_digest": _util.hash_bytes(packet_bytes),
                 "proof_recorded": bool(manifest.get("proof")),
                 "ceremony": CEREMONY, "when": _util.stamp()}
    with open(stem + ".sign.json", "w", encoding="utf-8") as handle:
        handle.write(json.dumps(statement, sort_keys=True))
    signature = _sign_file(stem + ".sign.json", key, kernel.SIGN_NAMESPACE)
    return {"ceremony": CEREMONY,
            "statement": os.path.relpath(stem + ".sign.json", claim),
            "packet": os.path.relpath(stem + ".packet.json", claim),
            "signature": os.path.relpath(signature, claim),
            "sign_root": packet["sign_root"], "root": checked["root"],
            "identity": identity}


def sign_check(claim: str, ws: str | None = None,
               signers: str | None = None) -> dict:
    """Judge the authorizations on this claim against a recomputed chain."""
    anchor = _anchor(signers)
    drawer = os.path.join(claim, kernel.SIGN_DIR)
    rows = []
    try:
        chain = sign_root(claim, ws)
    except kernel.ClaimError:
        chain = None
    if os.path.isdir(drawer):
        for name in sorted(os.listdir(drawer)):
            if not name.endswith(".sign.json"):
                continue
            path = os.path.join(drawer, name)
            statement = _util.read_json(path)
            if not isinstance(statement, dict):
                rows.append({"statement": name, "verdict": "unreadable",
                             "packet_holds": False, "identity": None,
                             "proof_recorded": False})
                continue
            identity = statement.get("identity")
            packet_path = path[:-len(".sign.json")] + ".packet.json"
            packet_holds = False
            if os.path.isfile(packet_path):
                with open(packet_path, "rb") as handle:
                    packet_holds = _util.hash_bytes(handle.read()) == \
                        statement.get("packet_digest")
            verified = _verified(path, identity, kernel.SIGN_NAMESPACE,
                                 anchor)
            intact = _intact(path, kernel.SIGN_NAMESPACE)
            rows.append({
                "statement": name, "identity": identity,
                "when": statement.get("when"),
                "verdict": "authorized" if verified else (
                    "intact" if intact else "broken"),
                "packet_holds": packet_holds,
                "names_this_chain": statement.get("sign_root") == chain,
                "proof_recorded": bool(statement.get("proof_recorded"))})
    ok = bool(rows) and bool(anchor) and all(
        r["verdict"] == "authorized" and r["packet_holds"] for r in rows)
    return {"ok": ok, "anchored": bool(anchor), "sign_root": chain,
            "authorizations": rows}


def sign_root(claim: str, ws: str | None = None) -> str:
    from . import registry
    return registry.sign_root(claim, ws)
