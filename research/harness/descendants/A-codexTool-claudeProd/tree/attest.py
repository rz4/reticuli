"""Attestation and the signing ceremony — a claim meets other parties.

Two acts live here, and they are deliberately different.

An **attestation** says *I obtained these results on this build*.  It is
residue ABOUT a claim that travels WITH it, it may only be made over a claim
whose verdicts reproduce from its own bytes — never a carried verdict — and
it is bound to the BUILD, not merely the claim: regenerating after signing
keeps the root (that freedom is the equivalence class) but is a different
build, so the old attestation refuses.

A **signing ceremony** is accountable authorization over the chain.  SIGNED
means AUTHORIZED by a signer the verifier anchors AND PROVEN by a recorded
crosscheck; the two facts are coupled, and both are verifier-relative through
the anchor.  The statement binds a review PACKET by digest, so what a human
opened to see what they were authorizing is itself part of what was signed.

**Unanchored, nothing is authorized to you.**  With no `allowed_signers`
file, `ssh-keygen` can only answer `check-novalidate`: the signature is valid
for whatever key is embedded IN it, and a statement re-signed by any key
looks exactly like the keyholder's.  The honest verdict is then `intact` — a
statement was signed — never `authorized`.  That was found the hard way, by
walking a receiver's path on this repository's own signed claim and reading
`authorized = true` off a forged signature.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess

from . import _util, kernel, registry

#: Where attestations live — residue, outside every root.
ATTEST = ".reticuli/attest"
#: The ceremony this tool performs, named in every statement it signs.
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _slug(identity: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", identity).strip("-") or "signer"


def _sign_file(path: str, key: str, namespace: str) -> str:
    """Make a detached ssh signature over a file's exact bytes."""
    if not shutil.which("ssh-keygen"):
        raise kernel.ClaimError(
            "ssh-keygen is not on PATH, so nothing can be signed here")
    signature = path + ".sig"
    if os.path.isfile(signature):
        os.remove(signature)          # ssh-keygen prompts before overwriting
    done = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
        capture_output=True, text=True, check=False)
    if done.returncode != 0 or not os.path.isfile(signature):
        raise kernel.ClaimError(
            f"signing failed: {(done.stderr or done.stdout).strip()[-300:]}")
    return signature


def _intact(path: str, namespace: str) -> bool:
    """Is the signature self-consistent, whatever key made it?

    This establishes that a statement WAS signed and nothing more; it is the
    strongest thing an unanchored verifier can say.
    """
    if not shutil.which("ssh-keygen") or not os.path.isfile(path + ".sig"):
        return False
    with open(path, "rb") as handle:
        payload = handle.read()
    done = subprocess.run(
        ["ssh-keygen", "-Y", "check-novalidate", "-n", namespace,
         "-s", path + ".sig"],
        input=payload, capture_output=True, check=False)
    return done.returncode == 0


def _anchored(path: str, namespace: str, signers: str, identity: str) -> bool:
    """Does the verifier's OWN anchor verify this signature for this identity?"""
    if not signers or not os.path.isfile(signers):
        return False
    if not shutil.which("ssh-keygen") or not os.path.isfile(path + ".sig"):
        return False
    with open(path, "rb") as handle:
        payload = handle.read()
    done = subprocess.run(
        ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", identity,
         "-n", namespace, "-s", path + ".sig"],
        input=payload, capture_output=True, check=False)
    return done.returncode == 0


# -- attestation ------------------------------------------------------------


def attest(claimdir: str, key: str, identity: str) -> dict:
    """Sign a statement of this build's results, for other parties.

    Refused over a claim that does not verify (there is nothing to be about)
    and over one whose gates do not reproduce from the bytes present: an
    attestation over a carried verdict would notarize someone else's past.
    """
    checked = kernel.verify(claimdir)
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"{claimdir!r} does not verify, so there is nothing to attest: "
            f"the bytes present do not recompute to the sealed root")
    verdict = kernel.audit(claimdir)
    if not verdict["ok"]:
        raise kernel.ClaimError(
            f"the verdicts in {claimdir!r} do not reproduce from its own "
            f"bytes ({verdict['verdict']}); an attestation is never made over "
            f"a carried verdict")
    where = os.path.join(claimdir, ATTEST)
    os.makedirs(where, exist_ok=True)
    statement = {
        "attestation": 1, "identity": identity, "name": checked["name"],
        "root": checked["root"], "build_digest": kernel.build_digest(claimdir),
        "verdict": verdict["verdict"], "when": _util.stamp(),
        "gates": [{"output": g["output"], "status": g["status"],
                   "sandbox": g.get("quarantine") or "none"}
                  for g in verdict["gates"]],
        "environment": kernel._judging_host(),
    }
    path = os.path.join(where, f"{_slug(identity)}.attest.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(statement, handle, sort_keys=True)
    _sign_file(path, key, kernel.NAMESPACE)
    relative = os.path.relpath(path, claimdir).replace(os.sep, "/")
    return {"statement": relative, "signature": relative + ".sig",
            "identity": identity, "root": checked["root"]}


def check(claimdir: str, signers: str = None) -> dict:
    """Read every attestation about this claim and say what each supports."""
    where = os.path.join(claimdir, ATTEST)
    anchor = signers or os.environ.get(kernel._ENV_SIGNERS)
    checked = kernel.verify(claimdir)
    digest = kernel.build_digest(claimdir)
    rows = []
    if os.path.isdir(where):
        for name in sorted(os.listdir(where)):
            if not name.endswith(".attest.json"):
                continue
            path = os.path.join(where, name)
            try:
                statement = kernel._read_json(path)
            except kernel.ClaimError as exc:
                rows.append({"statement": name, "verdict": "unreadable",
                             "ok": False, "drifted": False,
                             "detail": str(exc)})
                continue
            identity = statement.get("identity") or ""
            intact = _intact(path, kernel.NAMESPACE)
            trusted = _anchored(path, kernel.NAMESPACE, anchor, identity)
            drifted = statement.get("build_digest") != digest
            names_root = statement.get("root") == checked["recomputed"]
            verdict = "signed" if trusted else (
                "intact" if intact else "broken")
            rows.append({
                "statement": name, "identity": identity, "verdict": verdict,
                "drifted": drifted, "names_root": names_root,
                "anchored": bool(trusted),
                "ok": bool(intact and names_root and not drifted
                           and (trusted or not anchor)),
            })
    return {"ok": bool(rows) and all(r["ok"] for r in rows),
            "anchored": bool(anchor and os.path.isfile(anchor)),
            "root": checked["root"], "attestations": rows}


# -- the signing ceremony ---------------------------------------------------


def review_packet(claimdir: str, ws: str = None) -> dict:
    """What a signer stands behind: the chain root, and the verdict beneath it.

    The packet is assembled for a HUMAN to read, and it is what the signature
    binds by digest — so the reviewable artifact on disk cannot later be
    anything other than what was authorized.
    """
    checked = kernel.verify(claimdir)
    verdict = registry.audit_deep(claimdir, ws)
    manifest = kernel.read_manifest(claimdir)
    return {
        "name": checked["name"],
        "root": checked["recomputed"],
        "build_digest": kernel.build_digest(claimdir),
        "sign_root": registry.sign_root(claimdir, ws),
        "audit": {
            "ok": bool(verdict["ok"]), "verdict": verdict["verdict"],
            "gates": [{"output": g["output"], "status": g["status"],
                       "sandbox": g.get("quarantine") or "none"}
                      for g in verdict["gates"]],
            "layers": [{"name": r["name"], "ok": bool(r["ok"]),
                        "status": r["status"]} for r in verdict["layers"]],
        },
        "proof": manifest.get("proof"),
    }


def sign(claimdir: str, key: str, identity: str, ws: str = None) -> dict:
    """The ceremony: re-earn the verdict, then authorize the chain root.

    On a claim that declares components the COMPOSED verdict is what is
    re-earned.  The shallow half alone was not enough: a composed claim whose
    component was forged — its own gate blind, the deep audit refusing — was
    SIGNED, with `sign_root` folding the broken chain into signed identity.
    """
    checked = kernel.verify(claimdir)
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"{claimdir!r} does not verify; a signature over a claim whose "
            f"bytes do not recompute would name nothing")
    own = kernel.audit(claimdir)
    if not own["ok"]:
        raise kernel.ClaimError(
            f"the verdicts in {claimdir!r} do not reproduce ({own['verdict']});"
            f" a signature is never made over a carried verdict")
    if kernel.read_manifest(claimdir).get("components"):
        deep = registry.audit_deep(claimdir, ws)
        if not deep["ok"]:
            broken = [r["name"] for r in deep["layers"] if not r["ok"]]
            raise kernel.ClaimError(
                f"the composed verdict for {claimdir!r} does not re-earn "
                f"({', '.join(broken) or 'a layer beneath it'}); the "
                f"statement names the CHAIN root, so the chain is what must "
                f"hold")

    packet = review_packet(claimdir, ws)
    where = os.path.join(claimdir, kernel.SIGN_DIR)
    os.makedirs(where, exist_ok=True)
    slug = _slug(identity)
    packet_path = os.path.join(where, f"{slug}.packet.json")
    with open(packet_path, "w", encoding="utf-8") as handle:
        json.dump(packet, handle, sort_keys=True)
    digest = hashlib.sha256(
        json.dumps(packet, sort_keys=True).encode("utf-8")).hexdigest()
    statement = {
        "ceremony": CEREMONY, "identity": identity,
        "root": packet["root"], "sign_root": packet["sign_root"],
        "packet_digest": digest,
        "proof_recorded": bool(packet["proof"]),
        "when": _util.stamp(),
    }
    statement_path = os.path.join(where, f"{slug}.sign.json")
    with open(statement_path, "w", encoding="utf-8") as handle:
        json.dump(statement, handle, sort_keys=True)
    _sign_file(statement_path, key, kernel.SIGN_NAMESPACE)
    relative = os.path.relpath(statement_path, claimdir).replace(os.sep, "/")
    return {
        "ceremony": CEREMONY, "identity": identity,
        "statement": relative, "signature": relative + ".sig",
        "packet": os.path.relpath(packet_path, claimdir).replace(os.sep, "/"),
        "root": packet["root"], "sign_root": packet["sign_root"],
        "proof_recorded": statement["proof_recorded"],
    }


def sign_check(claimdir: str, ws: str = None, signers: str = None) -> dict:
    """Verify the authorizations on a claim, as the RECEIVER's anchor sees them.

    `intact` is not authorization: it says a statement was signed, not whose
    it is.  So an unanchored check can never report `authorized`, and a
    stranger's signature is asserted INDISTINGUISHABLE there — which is
    exactly why the verdict must refuse.
    """
    anchor = signers or os.environ.get(kernel._ENV_SIGNERS)
    anchored = bool(anchor and os.path.isfile(anchor))
    where = os.path.join(claimdir, kernel.SIGN_DIR)
    checked = kernel.verify(claimdir)
    digest = kernel.build_digest(claimdir)
    try:
        chain = registry.sign_root(claimdir, ws)
    except kernel.ClaimError:
        chain = None
    rows = []
    if os.path.isdir(where):
        for name in sorted(os.listdir(where)):
            if not name.endswith(".sign.json"):
                continue
            path = os.path.join(where, name)
            try:
                statement = kernel._read_json(path)
            except kernel.ClaimError as exc:
                rows.append({"statement": name, "verdict": "unreadable",
                             "ok": False, "detail": str(exc)})
                continue
            identity = statement.get("identity") or ""
            intact = _intact(path, kernel.SIGN_NAMESPACE)
            trusted = _anchored(path, kernel.SIGN_NAMESPACE, anchor, identity)
            packet_path = os.path.join(
                where, name[:-len(".sign.json")] + ".packet.json")
            packet, holds, drifted = None, False, True
            if os.path.isfile(packet_path):
                try:
                    packet = kernel._read_json(packet_path)
                except kernel.ClaimError:
                    packet = None
            if isinstance(packet, dict):
                holds = hashlib.sha256(
                    json.dumps(packet, sort_keys=True).encode()
                ).hexdigest() == statement.get("packet_digest")
                drifted = packet.get("build_digest") != digest
            rows.append({
                "statement": name, "identity": identity,
                "verdict": "authorized" if trusted else (
                    "intact" if intact else "broken"),
                "anchored": bool(trusted),
                "packet_holds": bool(holds),
                "drifted": bool(drifted),
                "names_root": statement.get("root") == checked["recomputed"],
                "names_chain": statement.get("sign_root") == chain,
                "proof_recorded": bool(statement.get("proof_recorded")),
                "ok": bool(trusted and holds and not drifted
                           and statement.get("root") == checked["recomputed"]),
            })
    return {"ok": bool(rows) and anchored and all(r["ok"] for r in rows),
            "anchored": anchored, "root": checked["root"],
            "sign_root": chain, "authorizations": rows}
