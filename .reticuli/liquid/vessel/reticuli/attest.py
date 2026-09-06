"""Attestation: a realization that speaks for itself to others.

Quarantine protects the verifier from a hostile record; attestation is the
converse — a keyholder's signed statement that *this* realization verified
fresh on their machine: the root, every output's hash, the gates' quarantine
record, the cost. Signed with `ssh-keygen -Y` (the key you already have), in
in-toto Statement shape so foreign tooling can read it. Attestations are
residue *about* the claim, never part of it — they live in .reticuli/attest/,
travel with the record (export carries them), and never enter the root.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess

from . import kernel

ATTEST = os.path.join(kernel.STORE, "attest")
MINT = kernel.MINT
NAMESPACE = kernel.NAMESPACE
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://github.com/rz4/reticuli/attest/v1"
MINT_TYPE = "https://github.com/rz4/reticuli/mint/v1"
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _sh(argv: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=stdin, capture_output=True, check=False)


def _sign(path: str, key: str, namespace: str = NAMESPACE) -> subprocess.CompletedProcess:
    """Sign `path` with ssh-keygen -Y under `namespace`, writing `path.sig`.
    Removes any existing signature first: `ssh-keygen -Y sign` PROMPTS to
    overwrite an existing .sig and, with no tty, leaves the stale one in place —
    so a re-attest or re-mint would silently keep the old signature over new
    bytes. We overwrite cleanly. Attestation and mint sign in DIFFERENT
    namespaces (see kernel.MINT_NAMESPACE), so their signatures cannot be
    confused for one another."""
    sig = path + ".sig"
    if os.path.exists(sig):
        os.remove(sig)
    return _sh(["ssh-keygen", "-Y", "sign", "-f", os.path.expanduser(key),
                "-n", namespace, path])


def _slug(identity: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", identity.lower()).strip("-") or "signer"


def _gates(d: str) -> list[dict]:
    """The ledger's gate lines — the quarantine evidence the statement carries."""
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
    """The in-toto statement for this realization, as it stands on disk."""
    m = kernel.read_manifest(d)
    recipe = kernel.load_recipe(d)
    outputs = {kernel._out(s): kernel._hf(kernel._safe(d, kernel._out(s)))
               for s in recipe.get("step", [])
               if os.path.isfile(kernel._safe(d, kernel._out(s)))}
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
    """Sign this realization. Refuses a record that is broken *or* whose
    verdicts do not reproduce from its own bytes (kernel.audit) — an
    attestation says the gates passed here, now, against these bytes; it must
    never notarize a carried verdict."""
    a = kernel.audit(d)
    if not a["ok"]:
        raise kernel.ReticuliError(
            "attest: refusing to sign — the record is broken or its verdicts "
            "do not reproduce from its bytes")
    v = kernel.verify(d)
    st = statement(d, identity)
    os.makedirs(os.path.join(d, ATTEST), exist_ok=True)
    path = os.path.join(d, ATTEST, f"{_slug(identity)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, sort_keys=True)
        f.write("\n")
    r = _sign(path, key)
    if r.returncode != 0:
        raise kernel.ReticuliError(f"attest: signing failed: {r.stderr.decode().strip()[:200]}")
    rel = os.path.join(ATTEST, f"{_slug(identity)}.json")
    return {"name": v["name"], "root": v["root"], "identity": identity,
            "statement": rel, "signature": rel + ".sig"}


def check(d: str, signers: str | None = None) -> dict:
    """Verify this record's attestations. With an allowed-signers file the
    signer's identity is verified; without one, only that each signature is
    intact for the bytes it covers ("intact", signer untrusted). The statement
    must name this record's current root AND its signed output hashes must
    still be the bytes on disk — an attestation speaks for a REALIZATION, not
    just a claim; free bytes are outside the root, so a free redo after signing
    keeps the root but is a different realization, and the old attestation
    must refuse (re-attest the new bytes instead)."""
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
                   or kernel._hf(kernel._safe(d, o)) != hsh]
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


# -- the mint ceremony: accountable authorization over the chain -------------


def review_packet(d: str, ws: str | None = None, prior: str | None = None) -> dict:
    """The canonical bundle a keyholder reviews before authorizing a mint: the
    claim root, the chain (mint) root, the realization digest, the normalized
    recipe, the seed digests, the gate sources, the component chain, and a fresh
    audit verdict. With a prior mint, the diff — whether the chain moved. This is
    what a signature is *over*: the reviewer sees exactly what they authorize."""
    from . import registry
    v = kernel.verify(d)
    m = kernel.read_manifest(d)
    recipe = kernel.load_recipe(d)
    a = kernel.audit(d)
    packet = {
        "name": v["name"], "root": v["root"], "fresh": v["ok"],
        "mint": registry.mint_root(d, ws),
        "realization_digest": kernel.realization_digest(d),
        "recipe": recipe,
        "seeds": {s: kernel._hf(kernel._safe(d, s)) for s in kernel._seeds(recipe)
                  if os.path.isfile(kernel._safe(d, s))},
        "gates": [s["run"] for s in recipe.get("step", []) if s.get("kind") == "gate"],
        "components": m.get("components", []),
        "audit": {"ok": a["ok"], "gates": a["gates"]},
        # honesty about the ladder: whether a three-machine proof was recorded
        # (residue — readable, not locally re-verifiable). The reviewer sees it,
        # the signature binds it: a mint can never be mistaken for a proof.
        "proof": m.get("proof"),
    }
    if prior is not None:
        packet["diff"] = {"prior_mint": prior, "moved": prior != packet["mint"]}
    return packet


def _packet_digest(packet: dict) -> str:
    return kernel._h(json.dumps(packet, sort_keys=True).encode())


def mint(d: str, key: str, identity: str, ws: str | None = None) -> dict:
    """Authorize a record as solid: sign its CHAIN root and the review packet's
    digest with ssh-keygen -Y, under a key outside agent authority. This is
    ACCOUNTABLE AUTHORIZATION AFTER A DEFINED CEREMONY — a keyholder vouches that
    they reviewed the packet and authorize this mint. It is non-repudiable
    authorization, NOT proof the review was diligent. Refuses unless the verdicts
    reproduce from the record's own bytes (audit). The signed statement names the
    portable chain root, so anyone can recompute the chain and check it."""
    a = kernel.audit(d)
    if not a["ok"]:
        raise kernel.ReticuliError(
            "mint: refusing — the verdicts do not reproduce from the record's bytes (audit)")
    packet = review_packet(d, ws)
    os.makedirs(os.path.join(d, MINT), exist_ok=True)
    slug = _slug(identity)
    ppath = os.path.join(d, MINT, f"{slug}.packet.json")
    spath = os.path.join(d, MINT, f"{slug}.mint.json")
    with open(ppath, "w", encoding="utf-8") as f:
        json.dump(packet, f, indent=2, sort_keys=True)
        f.write("\n")
    statement = {"_type": MINT_TYPE, "ceremony": CEREMONY, "identity": identity,
                 "root": packet["root"], "mint": packet["mint"],
                 "packet_digest": _packet_digest(packet),
                 "proof_recorded": bool(packet.get("proof")),
                 "when": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")}
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(statement, f, indent=2, sort_keys=True)
        f.write("\n")
    r = _sign(spath, key, kernel.MINT_NAMESPACE)      # the mint's own signature domain
    if r.returncode != 0:
        raise kernel.ReticuliError(f"mint: signing failed: {r.stderr.decode().strip()[:200]}")
    rel = os.path.join(MINT, f"{slug}.mint.json")
    return {"name": packet["name"], "root": packet["root"], "mint": packet["mint"],
            "identity": identity, "ceremony": CEREMONY,
            "packet": os.path.join(MINT, f"{slug}.packet.json"),
            "statement": rel, "signature": rel + ".sig"}


def mint_check(d: str, ws: str | None = None, signers: str | None = None) -> dict:
    """Verify a record's mint authorizations. Recomputes the chain root (portable,
    content-only) and confirms each signed statement still names it with an intact
    signature AND that the stored review packet still hashes to the signed packet
    digest — the packet is what the keyholder reviewed; unbound, it could be
    swapped after the fact. With a signers file the authorizer's identity is
    verified too. Each row reports `proof_recorded`: whether the statement says a
    three-machine proof was recorded at ceremony time — authorization and proof
    are separate rungs, and the ceremony never conflates them."""
    from . import registry
    current = registry.mint_root(d, ws)
    results = []
    base = os.path.join(d, MINT)
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if not name.endswith(".mint.json"):
            continue
        path = os.path.join(base, name)
        with open(path, "rb") as f:
            raw = f.read()
        st = json.loads(raw)
        identity = st.get("identity", "")
        try:
            packet_holds = (_packet_digest(kernel._read(path[: -len(".mint.json")]
                                                        + ".packet.json"))
                            == st.get("packet_digest"))
        except (OSError, ValueError):
            packet_holds = False
        if signers:
            r = _sh(["ssh-keygen", "-Y", "verify", "-f", os.path.expanduser(signers),
                     "-I", identity, "-n", kernel.MINT_NAMESPACE, "-s", path + ".sig"], stdin=raw)
            verdict = "authorized" if r.returncode == 0 else "invalid"
        else:
            r = _sh(["ssh-keygen", "-Y", "check-novalidate", "-n", kernel.MINT_NAMESPACE,
                     "-s", path + ".sig"], stdin=raw)
            verdict = "intact" if r.returncode == 0 else "invalid"
        matches = st.get("mint") == current
        results.append({"identity": identity, "ceremony": st.get("ceremony"),
                        "chain_holds": matches, "packet_holds": packet_holds,
                        "proof_recorded": st.get("proof_recorded"), "verdict": verdict,
                        "ok": verdict in ("authorized", "intact") and matches
                        and packet_holds})
    return {"name": kernel.read_manifest(d)["name"], "mint": current,
            "authorizations": results, "ok": bool(results) and all(x["ok"] for x in results)}
