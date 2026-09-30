"""Signed build attestations and accountable chain authorization."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile

from . import kernel, registry
from ._util import stamp, write_json

ATTEST = ".reticuli/attest"
CEREMONY = "RETICULI_CLAIM_BASIN_V1"


def _bytes(value):
    return json.dumps(value, sort_keys=True).encode()


def _sign(path, key, namespace):
    try:
        if os.path.exists(path + ".sig"):
            os.unlink(path + ".sig")
        subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, path],
                       check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise kernel.ClaimError(f"cannot sign {path}: {exc}") from exc


def _public(key):
    try:
        with open(key + ".pub", encoding="utf-8") as stream:
            kind, blob = stream.read().split()[:2]
        return kind + " " + blob
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read signing key: {exc}") from exc


def _verify(path, signature, namespace, identity, signers=None, public=None):
    temporary = None
    if signers is None:
        if not public:
            return False
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as stream:
            temporary = stream.name
            stream.write(identity + " " + public + "\n")
        signers = temporary
    try:
        with open(path, "rb") as stream:
            data = stream.read()
        done = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", signers,
                               "-I", identity, "-n", namespace, "-s", signature],
                              input=data, capture_output=True, timeout=30)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        if temporary:
            os.unlink(temporary)


def _audit(directory):
    checked = kernel.verify(directory)
    if not checked["ok"] or not registry.audit_deep(directory)["ok"]:
        raise kernel.ClaimError("claim verdicts do not reproduce")
    return checked


def attest(directory, key, identity):
    checked = _audit(directory)
    statement = {"root": checked["root"], "build_digest": kernel.build_digest(directory),
                 "identity": identity, "public": _public(key), "when": stamp()}
    name = hashlib.sha256(_bytes(statement)).hexdigest()[:16] + ".json"
    relative = ATTEST + "/" + name
    path = os.path.join(directory, relative)
    write_json(path, statement)
    _sign(path, key, kernel.NAMESPACE)
    return {"statement": relative, "signature": relative + ".sig", "root": checked["root"]}


def check(directory, signers=None):
    folder = os.path.join(directory, ATTEST)
    rows = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(folder, name)
            try:
                with open(path, encoding="utf-8") as stream:
                    stmt = json.load(stream)
                holds = _verify(path, path + ".sig", kernel.NAMESPACE,
                                stmt["identity"], signers, stmt.get("public"))
                drifted = (stmt["root"] != kernel.verify(directory)["root"] or
                           stmt["build_digest"] != kernel.build_digest(directory))
                rows.append({"statement": os.path.relpath(path, directory), "verdict":
                             "signed" if holds and not drifted else "refused",
                             "drifted": drifted, "ok": holds and not drifted})
            except (OSError, ValueError, KeyError, kernel.ClaimError):
                rows.append({"statement": os.path.relpath(path, directory),
                             "verdict": "refused", "drifted": False, "ok": False})
    return {"ok": bool(rows) and all(row["ok"] for row in rows), "attestations": rows}


def review_packet(directory, *, ws=None):
    checked = _audit(directory)
    manifest = kernel.read_manifest(directory)
    return {"root": checked["root"], "build_digest": kernel.build_digest(directory),
            "sign_root": registry.sign_root(directory, ws), "audit": registry.audit_deep(directory, ws=ws),
            "proof": manifest.get("proof"), "components": manifest.get("components", [])}


def sign(directory, key, identity, *, ws=None):
    packet = review_packet(directory, ws=ws)
    digest = hashlib.sha256(_bytes(packet)).hexdigest()
    folder = os.path.join(directory, kernel.SIGN_DIR)
    os.makedirs(folder, exist_ok=True)
    base = hashlib.sha256(identity.encode()).hexdigest()[:16]
    packet_relative = kernel.SIGN_DIR + "/" + base + ".packet.json"
    statement_relative = kernel.SIGN_DIR + "/" + base + ".sign.json"
    statement = {"ceremony": CEREMONY, "identity": identity, "public": _public(key),
                 "packet_digest": digest, "root": packet["root"],
                 "sign_root": packet["sign_root"], "build_digest": packet["build_digest"],
                 "proof_recorded": bool(packet["proof"]), "when": stamp()}
    write_json(os.path.join(directory, packet_relative), packet)
    write_json(os.path.join(directory, statement_relative), statement)
    _sign(os.path.join(directory, statement_relative), key, kernel.SIGN_NAMESPACE)
    return {"ceremony": CEREMONY, "packet": packet_relative,
            "statement": statement_relative, "signature": statement_relative + ".sig"}


def sign_check(directory, *, ws=None, signers=None):
    folder = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".sign.json"):
                continue
            path = os.path.join(folder, name)
            packet_path = path[:-10] + ".packet.json"
            try:
                with open(path, encoding="utf-8") as stream:
                    stmt = json.load(stream)
                with open(packet_path, encoding="utf-8") as stream:
                    packet = json.load(stream)
                packet_holds = hashlib.sha256(_bytes(packet)).hexdigest() == stmt["packet_digest"]
                current = (packet["root"] == kernel.verify(directory)["root"] and
                           packet["build_digest"] == kernel.build_digest(directory) and
                           packet["sign_root"] == registry.sign_root(directory, ws) and
                           packet.get("proof") == kernel.read_manifest(directory).get("proof"))
                signed = _verify(path, path + ".sig", kernel.SIGN_NAMESPACE,
                                 stmt["identity"], signers, stmt.get("public"))
                ok = packet_holds and current and signed
                rows.append({"verdict": "authorized" if ok else "refused", "ok": ok,
                             "packet_holds": packet_holds,
                             "proof_recorded": stmt.get("proof_recorded", False)})
            except (OSError, ValueError, KeyError, kernel.ClaimError):
                rows.append({"verdict": "refused", "ok": False, "packet_holds": False,
                             "proof_recorded": False})
    return {"ok": bool(rows) and all(row["ok"] for row in rows), "authorizations": rows}
