"""Attestation and authorization: a claim meeting other parties.

Two acts, two namespaces, never interchangeable. An **attestation** says "I
ran this build and these are the results"; an **authorization** says "I, the
keyholder, stand behind this claim". A signature made for one purpose must
not be presentable for another, so domain separation is cryptographic rather
than conventional.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess

from . import kernel
from . import registry
from ._util import read_json, write_json

#: Where attestations live. Residue ABOUT the claim, travelling WITH it.
ATTEST = ".reticuli/attest"

#: The named ceremony an authorization is performed under.
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _slug(identity: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", identity or "anonymous").strip("-")


def _signed_outputs(claim: str) -> dict:
    """The concrete bytes an attestation freezes, output by output."""
    parsed = kernel.load_recipe(claim)
    frozen = {}
    for step in kernel.produces(parsed):
        output = step.get("output")
        path = os.path.join(claim, output or "")
        if output and os.path.isfile(path):
            with open(path, "rb") as handle:
                frozen[output] = hashlib.sha256(handle.read()).hexdigest()
    return frozen


def _ssh_sign(path: str, key: str, namespace: str) -> str:
    signature = path + ".sig"
    if os.path.exists(signature):
        os.remove(signature)
    done = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
        capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise kernel.ClaimError(
            f"could not sign {os.path.basename(path)}: "
            f"{(done.stderr or done.stdout)[-300:]}")
    return signature


def _ssh_intact(path: str, namespace: str) -> bool:
    """Self-consistency only: the signature is valid for whatever key is IN it."""
    signature = path + ".sig"
    if not os.path.isfile(signature) or not shutil.which("ssh-keygen"):
        return False
    with open(path, "rb") as handle:
        payload = handle.read()
    done = subprocess.run(
        ["ssh-keygen", "-Y", "check-novalidate", "-n", namespace,
         "-s", signature],
        input=payload, capture_output=True, check=False)
    return done.returncode == 0


def _ssh_anchored(path: str, namespace: str, signers: str,
                  identity: str) -> bool:
    signature = path + ".sig"
    if not os.path.isfile(signature) or not shutil.which("ssh-keygen"):
        return False
    with open(path, "rb") as handle:
        payload = handle.read()
    done = subprocess.run(
        ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", identity,
         "-n", namespace, "-s", signature],
        input=payload, capture_output=True, check=False)
    return done.returncode == 0


def _anchor(signers: str | None) -> str | None:
    if signers and os.path.isfile(signers):
        return signers
    from_env = os.environ.get("RETICULI_SIGNERS")
    if not signers and from_env and os.path.isfile(from_env):
        return from_env
    return None


# --------------------------------------------------------------------------
# attestation: a signed statement of one build

def attest(claim: str, key: str, identity: str) -> dict:
    """Notarize THIS build. Never a carried verdict, never a broken claim."""
    checked = kernel.verify(claim)
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"will not attest a broken claim: the bytes present do not "
            f"recompute to the sealed root")
    judged = kernel.audit(claim)
    if not judged["ok"]:
        raise kernel.ClaimError(
            f"will not notarize a carried verdict: {claim} does not re-earn "
            f"its gates ({judged['verdict']})")
    statement = {"act": "attestation", "namespace": kernel.NAMESPACE,
                 "identity": identity, "name": checked["name"],
                 "root": checked["root"],
                 "build_digest": kernel.build_digest(claim),
                 "outputs": _signed_outputs(claim), "when": kernel._now()}
    relative = f"{ATTEST}/{_slug(identity)}.attest.json"
    path = os.path.join(claim, relative)
    write_json(path, statement)
    _ssh_sign(path, key, kernel.NAMESPACE)
    return {"statement": relative, "signature": relative + ".sig",
            "identity": identity, "root": statement["root"],
            "build_digest": statement["build_digest"]}


def check(claim: str, signers: str | None = None) -> dict:
    """Read every attestation in the drawer and say what each one is worth."""
    drawer = os.path.join(claim, ATTEST)
    anchor = _anchor(signers)
    checked = kernel.verify(claim)
    current = _signed_outputs(claim)
    rows = []
    for name in sorted(os.listdir(drawer) if os.path.isdir(drawer) else []):
        if not name.endswith(".attest.json"):
            continue
        path = os.path.join(drawer, name)
        statement = read_json(path)
        if not isinstance(statement, dict):
            rows.append({"statement": name, "verdict": "broken",
                         "intact": False, "drifted": True,
                         "names_this_root": False, "identity": None})
            continue
        identity = statement.get("identity") or ""
        intact = _ssh_intact(path, kernel.NAMESPACE)
        trusted = bool(anchor) and _ssh_anchored(
            path, kernel.NAMESPACE, anchor, identity)
        frozen = statement.get("outputs") or {}
        drifted = any(current.get(out) != digest
                      for out, digest in frozen.items())
        rows.append({
            "statement": name, "identity": identity,
            "root": statement.get("root"),
            "intact": intact, "anchored": bool(anchor), "trusted": trusted,
            "drifted": drifted,
            "names_this_root": statement.get("root") == checked["recomputed"],
            "verdict": "signed" if trusted else
                       ("intact" if intact else "broken"),
        })
    ok = bool(rows) and all(
        row["intact"] and row["names_this_root"] and not row["drifted"]
        and (row["trusted"] or not anchor) for row in rows)
    return {"ok": ok, "anchored": bool(anchor), "attestations": rows,
            "root": checked["root"]}


# --------------------------------------------------------------------------
# authorization: the signing ceremony

def review_packet(claim: str, ws: str | None = None) -> dict:
    """What a keyholder stands behind, assembled for a human to read."""
    checked = kernel.verify(claim)
    manifest = kernel.read_manifest(claim)
    components = manifest.get("components") or []
    judged = (registry.audit_deep(claim, ws) if components
              else kernel.audit(claim))
    return {"ceremony": CEREMONY, "name": checked["name"],
            "root": checked["recomputed"],
            "build_digest": kernel.build_digest(claim),
            "sign_root": registry.sign_root(claim, ws),
            "audit": {"ok": bool(judged["ok"]),
                      "verdict": judged.get("verdict"),
                      "gates": judged.get("gates") or [],
                      "layers": judged.get("layers") or []},
            "proof": manifest.get("proof"),
            "composed": [c.get("component") for c in components]}


def sign(claim: str, key: str, identity: str, ws: str | None = None) -> dict:
    """The accountable act: a human authorizes a chain root, having read it.

    Refuses a claim whose verdicts do not reproduce -- and, where the claim
    declares components, refuses unless the COMPOSED verdict re-earns: the
    statement names the chain root, so the endorsement must reach as deep as
    the identity it signs.
    """
    checked = kernel.verify(claim)
    if not checked["ok"]:
        raise kernel.ClaimError(
            "will not authorize a broken claim: identity does not hold")
    judged = kernel.audit(claim)
    if not judged["ok"]:
        raise kernel.ClaimError(
            f"will not authorize {claim}: its verdicts do not reproduce "
            f"({judged['verdict']})")
    manifest = kernel.read_manifest(claim)
    if manifest.get("components"):
        deep = registry.audit_deep(claim, ws)
        if not deep["ok"]:
            broken = [row.get("name") for row in deep.get("layers") or []
                      if not row.get("ok")]
            raise kernel.ClaimError(
                f"will not authorize {claim}: the composed verdict does not "
                f"re-earn ({', '.join(str(b) for b in broken)})")
    packet = review_packet(claim, ws)
    slug = _slug(identity)
    packet_rel = f"{kernel.SIGN_DIR}/{slug}.packet.json"
    packet_path = os.path.join(claim, packet_rel)
    os.makedirs(os.path.dirname(packet_path), exist_ok=True)
    with open(packet_path, "w", encoding="utf-8") as handle:
        json.dump(packet, handle, sort_keys=True)
    with open(packet_path, encoding="utf-8") as handle:
        stored = json.load(handle)
    digest = hashlib.sha256(
        json.dumps(stored, sort_keys=True).encode("utf-8")).hexdigest()
    statement = {"act": "authorization", "ceremony": CEREMONY,
                 "namespace": kernel.SIGN_NAMESPACE, "identity": identity,
                 "root": packet["root"], "packet_digest": digest,
                 "proof_recorded": bool(packet.get("proof")),
                 "sign_root": packet["sign_root"], "when": kernel._now()}
    statement_rel = f"{kernel.SIGN_DIR}/{slug}.sign.json"
    statement_path = os.path.join(claim, statement_rel)
    with open(statement_path, "w", encoding="utf-8") as handle:
        json.dump(statement, handle, sort_keys=True)
    _ssh_sign(statement_path, key, kernel.SIGN_NAMESPACE)
    return {"ceremony": CEREMONY, "statement": statement_rel,
            "signature": statement_rel + ".sig", "packet": packet_rel,
            "identity": identity, "root": packet["root"],
            "sign_root": packet["sign_root"],
            "proof_recorded": statement["proof_recorded"]}


def sign_check(claim: str, ws: str | None = None,
               signers: str | None = None) -> dict:
    """What is authorized TO YOU -- which is a question about your anchor.

    Unanchored, ssh-keygen can only answer `check-novalidate`: the signature
    is valid for whatever key is embedded in it, so a statement re-signed by
    any key looks exactly like the keyholder's. The honest verdict is then
    `intact` -- a statement was signed -- and never authorization.
    """
    anchor = _anchor(signers)
    drawer = os.path.join(claim, kernel.SIGN_DIR)
    checked = kernel.verify(claim)
    current_build = kernel.build_digest(claim)
    rows = []
    for name in sorted(os.listdir(drawer) if os.path.isdir(drawer) else []):
        if not name.endswith(".sign.json"):
            continue
        path = os.path.join(drawer, name)
        statement = read_json(path)
        if not isinstance(statement, dict):
            rows.append({"statement": name, "verdict": "broken",
                         "identity": None, "packet_holds": False,
                         "proof_recorded": False, "drifted": True,
                         "intact": False, "names_this_root": False})
            continue
        identity = statement.get("identity") or ""
        intact = _ssh_intact(path, kernel.SIGN_NAMESPACE)
        trusted = bool(anchor) and _ssh_anchored(
            path, kernel.SIGN_NAMESPACE, anchor, identity)
        packet_path = path[:-len(".sign.json")] + ".packet.json"
        packet = read_json(packet_path)
        packet_holds = False
        drifted = True
        if isinstance(packet, dict):
            digest = hashlib.sha256(
                json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()
            packet_holds = digest == statement.get("packet_digest")
            drifted = not (packet.get("root") == checked["recomputed"]
                           and packet.get("build_digest") == current_build)
        rows.append({
            "statement": name, "identity": identity,
            "root": statement.get("root"),
            "intact": intact, "anchored": bool(anchor), "trusted": trusted,
            "packet_holds": packet_holds, "drifted": drifted,
            "names_this_root": statement.get("root") == checked["recomputed"],
            "proof_recorded": bool(statement.get("proof_recorded")),
            "verdict": "authorized" if trusted else
                       ("intact" if intact else "broken"),
        })
    ok = bool(anchor) and bool(rows) and all(
        row["verdict"] == "authorized" and row["packet_holds"]
        and not row["drifted"] and row["names_this_root"] for row in rows)
    return {"ok": ok, "anchored": bool(anchor), "authorizations": rows,
            "root": checked["root"]}


def sign_root(claim: str, ws: str | None = None) -> str:
    """The chain root a signature names (the exchange layer's fold)."""
    return registry.sign_root(claim, ws)
