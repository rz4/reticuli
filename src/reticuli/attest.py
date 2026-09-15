"""Attestation: a build that speaks for itself to others.

The sandbox protects the verifier from a hostile claim; attestation is the
converse — a keyholder's signed statement that *this* build verified fresh on
their machine: the root, every output's hash, the gates' sandbox record, the
cost. Signed with `ssh-keygen -Y` (the key you already have), in in-toto
Statement shape so foreign tooling can read it. Attestations are residue *about*
the claim, never part of it — they live in .reticuli/attest/, travel with the
claim (export carries them), and never enter the root.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess

from . import kernel
from ._util import declared_inputs, hash_bytes, safe_path, step_output, write_json

ATTEST = os.path.join(kernel.STORE, "attest")
SIGN_DIR = kernel.SIGN_DIR
NAMESPACE = kernel.NAMESPACE
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://github.com/rz4/reticuli/attest/v1"
# the wire strings are carried from v1 unchanged, for signature interop, while
# the namespace question in spec/claim-format.md stays open; the CONSTANT names
# speak v2 (spec/kernel-api.md)
SIGN_TYPE = "https://github.com/rz4/reticuli/mint/v1"
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _sh(argv: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=stdin, capture_output=True, check=False)


def _hash_file(path: str) -> str:
    """sha256 of a file's bytes (v1: `kernel._hf`; the v2 kernel keeps its file
    hasher private, so the layer hashes the bytes itself)."""
    with open(path, "rb") as f:
        return hash_bytes(f.read())


def _ssh_sign(path: str, key: str, namespace: str = NAMESPACE) -> subprocess.CompletedProcess:
    """Sign `path` with ssh-keygen -Y under `namespace`, writing `path.sig`.
    Removes any existing signature first: `ssh-keygen -Y sign` PROMPTS to
    overwrite an existing .sig and, with no tty, leaves the stale one in place —
    so a re-attestation or re-signing would silently keep the old signature over
    new bytes. We overwrite cleanly. Attestation and the signing ceremony use
    DIFFERENT namespaces (see kernel.SIGN_NAMESPACE), so their signatures cannot
    be confused for one another."""
    sig = path + ".sig"
    if os.path.exists(sig):
        os.remove(sig)
    return _sh(["ssh-keygen", "-Y", "sign", "-f", os.path.expanduser(key),
                "-n", namespace, path])


def _slug(identity: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", identity.lower()).strip("-") or "signer"


def _gates(d: str) -> list[dict]:
    """The ledger's gate lines — the sandbox evidence the statement carries."""
    path = os.path.join(d, kernel.LEDGER)
    out = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("event") == "gate":
                    out.append(e)
    return out


def statement(d: str, identity: str) -> dict:
    """The in-toto statement for this build, as it stands on disk."""
    m = kernel.read_manifest(d)
    recipe = kernel.load_recipe(d)
    outputs = {step_output(s): _hash_file(safe_path(d, step_output(s)))
               for s in recipe.get("step", [])
               if os.path.isfile(safe_path(d, step_output(s)))}
    return {
        "_type": STATEMENT_TYPE,
        "subject": [{"name": m["name"], "digest": {"reticuliRoot": m["root"]}}],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "identity": identity,
            "when": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "outputs": outputs,
            "gates": _gates(d),
            "cost": kernel.cost(d),
        },
    }


def attest(d: str, key: str, identity: str) -> dict:
    """Sign this build. Refuses a claim that is broken *or* whose verdicts do not
    reproduce from its own bytes (kernel.audit) — an attestation says the gates
    passed here, now, against these bytes; it must never notarize a carried
    verdict."""
    a = kernel.audit(d)
    if not a["ok"]:
        raise kernel.ClaimError(
            "attest: refusing to sign — the claim is broken or its verdicts "
            "do not reproduce from its bytes")
    v = kernel.verify(d)
    st = statement(d, identity)
    os.makedirs(os.path.join(d, ATTEST), exist_ok=True)
    path = os.path.join(d, ATTEST, f"{_slug(identity)}.json")
    write_json(path, st)
    r = _ssh_sign(path, key)
    if r.returncode != 0:
        raise kernel.ClaimError(f"attest: signing failed: {r.stderr.decode().strip()[:200]}")
    rel = os.path.join(ATTEST, f"{_slug(identity)}.json")
    return {"name": v["name"], "root": v["root"], "identity": identity,
            "statement": rel, "signature": rel + ".sig"}


def check(d: str, signers: str | None = None) -> dict:
    """Verify this claim's attestations. With an allowed-signers file the
    signer's identity is verified; without one, only that each signature is
    intact for the bytes it covers ("intact", signer untrusted). The statement
    must name this claim's current root AND its signed output hashes must still
    be the bytes on disk — an attestation speaks for a BUILD, not just a claim;
    generated bytes are outside the root, so a regeneration after signing keeps
    the root but is a different build, and the old attestation must refuse
    (re-attest the new bytes instead)."""
    v = kernel.verify(d)
    results = []
    base = os.path.join(d, ATTEST)
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if not name.endswith(".json"):
            continue
        path = os.path.join(base, name)
        with open(path, "rb") as f:
            raw = f.read()
        st = json.loads(raw)
        identity = st.get("predicate", {}).get("identity", "")
        roots = {dg for s in st.get("subject", []) for dg in s.get("digest", {}).values()}
        drifted = [o for o, hsh in st.get("predicate", {}).get("outputs", {}).items()
                   if not os.path.isfile(os.path.join(d, o))
                   or _hash_file(safe_path(d, o)) != hsh]
        if signers:
            r = _sh(["ssh-keygen", "-Y", "verify", "-f", os.path.expanduser(signers),
                     "-I", identity, "-n", NAMESPACE, "-s", path + ".sig"], stdin=raw)
            verdict = "signed" if r.returncode == 0 else "invalid"
        else:
            r = _sh(["ssh-keygen", "-Y", "check-novalidate", "-n", NAMESPACE,
                     "-s", path + ".sig"], stdin=raw)
            verdict = "intact" if r.returncode == 0 else "invalid"
        results.append({"identity": identity, "verdict": verdict,
                        "root_match": v["root"] in roots, "drifted": drifted,
                        "when": st.get("predicate", {}).get("when"),
                        "ok": verdict in ("signed", "intact") and v["root"] in roots
                        and not drifted})
    return {"name": v["name"], "root": v["root"], "fresh": v["ok"],
            "attestations": results,
            "ok": v["ok"] and bool(results) and all(x["ok"] for x in results)}


# -- the signing ceremony: accountable authorization over the chain ----------


def review_packet(d: str, ws: str | None = None, prior: str | None = None) -> dict:
    """The canonical bundle a keyholder reviews before authorizing a signature:
    the claim root, the chain root, the build digest, the normalized recipe, the
    input digests, the gate sources, the component chain, and a fresh audit
    verdict. With a prior chain root, the diff — whether the chain moved. This is
    what a signature is *over*: the reviewer sees exactly what they authorize.

    `root`, `build_digest` and `proof` are not decoration: the kernel's phase
    test reads them back out of the stored packet and refuses to call a claim
    `signed` unless all three still describe the bytes on disk."""
    from . import registry
    v = kernel.verify(d)
    m = kernel.read_manifest(d)
    recipe = kernel.load_recipe(d)
    a = kernel.audit(d)
    packet = {
        "name": v["name"], "root": v["root"], "fresh": v["ok"],
        "sign_root": registry.sign_root(d, ws),
        "build_digest": kernel.build_digest(d),
        "recipe": recipe,
        "inputs": {s: _hash_file(safe_path(d, s)) for s in declared_inputs(recipe)
                   if os.path.isfile(safe_path(d, s))},
        "gates": [s["run"] for s in recipe.get("step", []) if s.get("kind") == "gate"],
        "components": m.get("components", []),
        "audit": {"ok": a["ok"], "gates": a["gates"]},
        # honesty about the ladder: whether a crosscheck proof was recorded
        # (residue — readable, not locally re-verifiable). The reviewer sees it,
        # the signature binds it: a signature can never be mistaken for a proof.
        "proof": m.get("proof"),
    }
    if prior is not None:
        packet["diff"] = {"prior_sign_root": prior, "moved": prior != packet["sign_root"]}
    return packet


def _packet_digest(raw: bytes) -> str:
    """The digest a signature binds the review packet by: sha256 of the packet
    file's BYTES as they stand on disk.

    v1 hashed a canonical re-serialization, so a reformatted packet still
    matched. The v2 kernel hashes the stored bytes directly when it decides
    whether a claim is `signed`, so this layer must agree with it byte for byte
    — otherwise nothing it signs could ever reach the signed phase.
    """
    return hash_bytes(raw)


def sign(d: str, key: str, identity: str, ws: str | None = None) -> dict:
    """Authorize a claim as signed: sign its CHAIN root and the review packet's
    digest with ssh-keygen -Y, under a key outside agent authority. This is
    ACCOUNTABLE AUTHORIZATION AFTER A DEFINED CEREMONY — a keyholder vouches that
    they reviewed the packet and authorize this signature. It is non-repudiable
    authorization, NOT proof the review was diligent. Refuses unless the verdicts
    reproduce from the claim's own bytes (audit). The signed statement names the
    portable chain root, so anyone can recompute the chain and check it."""
    a = kernel.audit(d)
    if not a["ok"]:
        raise kernel.ClaimError(
            "sign: refusing — the verdicts do not reproduce from the claim's bytes (audit)")
    packet = review_packet(d, ws)
    os.makedirs(os.path.join(d, SIGN_DIR), exist_ok=True)
    slug = _slug(identity)
    ppath = os.path.join(d, SIGN_DIR, f"{slug}.packet.json")
    spath = os.path.join(d, SIGN_DIR, f"{slug}.sign.json")
    write_json(ppath, packet)
    with open(ppath, "rb") as f:                  # the digest covers what landed
        packet_bytes = f.read()
    st = {"_type": SIGN_TYPE, "ceremony": CEREMONY, "identity": identity,
          "root": packet["root"], "sign_root": packet["sign_root"],
          "packet_digest": _packet_digest(packet_bytes),
          "proof_recorded": bool(packet.get("proof")),
          "when": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")}
    write_json(spath, st)
    r = _ssh_sign(spath, key, kernel.SIGN_NAMESPACE)   # the ceremony's own domain
    if r.returncode != 0:
        raise kernel.ClaimError(f"sign: signing failed: {r.stderr.decode().strip()[:200]}")
    rel = os.path.join(SIGN_DIR, f"{slug}.sign.json")
    return {"name": packet["name"], "root": packet["root"],
            "sign_root": packet["sign_root"],
            "identity": identity, "ceremony": CEREMONY,
            "packet": os.path.join(SIGN_DIR, f"{slug}.packet.json"),
            "statement": rel, "signature": rel + ".sig"}


def sign_check(d: str, ws: str | None = None, signers: str | None = None) -> dict:
    """Verify a claim's signing authorizations. Recomputes the chain root
    (portable, content-only) and confirms each signed statement still names it
    with an intact signature AND that the stored review packet still hashes to
    the signed packet digest — the packet is what the keyholder reviewed;
    unbound, it could be swapped after the fact. With a signers file the
    authorizer's identity is verified too. Each row reports `proof_recorded`:
    whether the statement says a crosscheck proof was recorded at ceremony time —
    authorization and proof are separate rungs, and the ceremony never conflates
    them."""
    from . import registry
    current = registry.sign_root(d, ws)
    results = []
    base = os.path.join(d, SIGN_DIR)
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if not name.endswith(".sign.json"):
            continue
        path = os.path.join(base, name)
        with open(path, "rb") as f:
            raw = f.read()
        st = json.loads(raw)
        identity = st.get("identity", "")
        try:
            with open(path[: -len(".sign.json")] + ".packet.json", "rb") as f:
                packet_holds = _packet_digest(f.read()) == st.get("packet_digest")
        except OSError:
            packet_holds = False
        if signers:
            r = _sh(["ssh-keygen", "-Y", "verify", "-f", os.path.expanduser(signers),
                     "-I", identity, "-n", kernel.SIGN_NAMESPACE, "-s", path + ".sig"],
                    stdin=raw)
            verdict = "authorized" if r.returncode == 0 else "invalid"
        else:
            r = _sh(["ssh-keygen", "-Y", "check-novalidate", "-n", kernel.SIGN_NAMESPACE,
                     "-s", path + ".sig"], stdin=raw)
            verdict = "intact" if r.returncode == 0 else "invalid"
        matches = st.get("sign_root") == current
        results.append({"identity": identity, "ceremony": st.get("ceremony"),
                        "chain_holds": matches, "packet_holds": packet_holds,
                        "proof_recorded": st.get("proof_recorded"), "verdict": verdict,
                        "ok": verdict in ("authorized", "intact") and matches
                        and packet_holds})
    return {"name": kernel.read_manifest(d)["name"], "sign_root": current,
            "authorizations": results, "ok": bool(results) and all(x["ok"] for x in results)}
