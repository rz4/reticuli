"""Exchange conformance gate — the acceptance check of the `exchange` layer.

Claims meeting claims — and other parties: the registry (claim stores,
content-addressed component links, DAG-aware rebuild), transfer (deterministic
tar, verify-on-import, volatile history stays home), and attestation (a
keyholder's signed statement of a build: signs only claims whose verdicts
reproduce from their own bytes — never a carried verdict — refuses tampered
statements, anchors identity to allowed signers). Layers on the kernel; knows
nothing of authoring or the CLI. Writes EXCHANGE_OK iff the layer conforms.
Stdlib only, so it runs in any clean workspace.

    python3 checks/exchange_check.py       (from the repository root)
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

# the package ships from src/; inside a sealed claim's workspace it sits at the
# root beside this check
sys.path.insert(0, "src" if os.path.isdir("src/reticuli") else ".")
from reticuli import attest, kernel, registry, transfer

LIB = '''[claim]
name = "lib"

[[step]]
kind = "gate"
output = "lib.txt"
run = "printf LIBDATA > lib.txt"
class = "validated"
'''

APP = '''[claim]
name = "app"
inputs = ["dep.txt"]

[[step]]
kind = "produce"
output = "app.txt"
request = "any note"
class = "generated"

[[step]]
kind = "gate"
output = "V"
run = "grep -qi implementation app.txt && grep -q LIBDATA dep.txt && printf ok > V"
class = "validated"
'''


LIBCODE = '''[claim]
name = "libcode"
inputs = ["lib_check.py"]

[[step]]
kind = "produce"
output = "lib.py"
request = "val() returns 42"
class = "generated"

[[step]]
kind = "gate"
output = "LIB_OK"
run = "python3 lib_check.py"
class = "validated"
'''

APPCODE = '''[claim]
name = "appcode"
inputs = ["app_check.py"]

[[step]]
kind = "produce"
output = "lib.py"
class = "generated"
from = "libcode"
request = "supplied by the libcode component"

[[step]]
kind = "produce"
output = "app.py"
request = "answer() returns val()"
class = "generated"

[[step]]
kind = "gate"
output = "APP_OK"
run = "python3 app_check.py"
class = "validated"
'''

# the kernel hands a producer the ABSOLUTE path of the output it wants next
# ($RETICULI_OUTPUT), so a dispatching producer matches on the tail
CODE_PRODUCER = (
    'case "$RETICULI_OUTPUT" in '
    '*/lib.py|lib.py) printf "def val(): return 42\\n" > lib.py ;; '
    '*/app.py|app.py) printf "from lib import val\\ndef answer(): return val()\\n" > app.py ;; '
    'esac'
)


def _write(d: str, files: dict) -> None:
    os.makedirs(d, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(d, name), "w") as f:
            f.write(content)


def _digest(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def battery() -> None:
    d = tempfile.mkdtemp()
    try:
        ws = os.path.join(d, "ws")
        lib = os.path.join(ws, ".reticuli", "sealed", "lib")
        _write(lib, {"claim.toml": LIB, "lib.txt": "LIBDATA"})
        kernel.seal(lib)

        # a pinned input that content-matches a claim's output is a dependency
        _write(ws, {"dep.txt": "LIBDATA"})
        links = registry.detect_components(ws, ["dep.txt"])
        assert any(x["component"] == "lib" for x in links), "content-addressed link"

        app = os.path.join(ws, ".reticuli", "sealed", "app")
        _write(app, {"claim.toml": APP, "dep.txt": "LIBDATA",
                     "app.txt": "one implementation\n", "V": "ok"})
        registry.seal_with(app, components=links)
        names = {r["name"] for r in registry.claims(ws)}
        assert names == {"app", "lib"}, "the claim store"
        edges = registry.deps(ws)["claims"]
        assert any(e["status"] == "ok" for n in edges for e in n["depends_on"]), "the DAG"

        # DAG-aware rebuild: the chain reproduces from the leaves
        m3 = os.path.join(d, "m3")
        out = registry.rebuild_chain(app, "printf 'another implementation' > app.txt", m3, ws=ws)
        assert out["root"] == kernel.verify(app)["root"], "chain reproduces"
        assert any(c["component"] == "lib" for c in out["rebuilt_components"]), "leaf first"
        # a rebuilt claim must keep its provenance: the manifest carries the
        # component links it was rebuilt from (else its component tree is blind)
        assert kernel.read_manifest(m3).get("components"), "rebuild preserves provenance"

        # pull: a claim becomes a dependency of a fresh workspace
        ws2 = os.path.join(d, "ws2")
        os.makedirs(ws2)
        pulled = registry.pull(app, ws2)
        assert pulled["materialized"] and os.path.isfile(os.path.join(ws2, "V")), "pull"

        # transfer: deterministic tar, verify-on-import, ledger stays home
        tar_path = os.path.join(d, "m3.tar")
        transfer.export(m3, tar_path)
        with tarfile.open(tar_path) as t:
            assert ".reticuli/ledger.jsonl" not in t.getnames(), "events don't travel"
        back = transfer.import_(tar_path, os.path.join(d, "back"))
        assert back["ok"] and back["root"] == out["root"], "identity travels"

        # declared content ONLY: a stray file dropped in the claim's directory
        # must not ride along, and two exports of one claim are byte-identical.
        # (An export that walks the tree instead of the recipe leaks the workspace.)
        with open(os.path.join(m3, "stray-residue.txt"), "w") as f:
            f.write("laptop junk that is not part of the claim\n")
        leak_tar = os.path.join(d, "leak.tar")
        transfer.export(m3, leak_tar)
        with tarfile.open(leak_tar) as t:
            assert "stray-residue.txt" not in t.getnames(), "undeclared bytes must not travel"
        det_tar = os.path.join(d, "det.tar")
        transfer.export(m3, det_tar)
        assert _digest(leak_tar) == _digest(det_tar), "export is byte-deterministic"
        os.remove(os.path.join(m3, "stray-residue.txt"))

        # attestation: a signed statement of this build, for other parties
        key = os.path.join(d, "key")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", key], check=True)
        a = attest.attest(m3, key, "checker@basin")
        assert os.path.isfile(os.path.join(m3, a["signature"])), "signed"
        assert attest.check(m3)["ok"], "intact and naming this root"
        # an attestation is residue ABOUT the claim that travels WITH it
        att_tar = os.path.join(d, "attested.tar")
        transfer.export(m3, att_tar)
        with tarfile.open(att_tar) as t:
            assert any(n.startswith(".reticuli/attest/") for n in t.getnames()), \
                "attestations travel with the claim"
        signers = os.path.join(d, "allowed_signers")
        with open(key + ".pub") as f:
            keytype, blob = f.read().split()[:2]
        with open(signers, "w") as f:
            f.write(f"checker@basin {keytype} {blob}\n")
        checked = attest.check(m3, signers)
        assert checked["ok"] and checked["attestations"][0]["verdict"] == "signed", "identity anchored"
        # an attestation speaks for a BUILD, not just a claim: regenerating after
        # signing keeps the root (that freedom is the equivalence class) but is a
        # different build — the signed output hashes no longer match the disk,
        # and the old attestation must refuse. Restore the exact bytes and it
        # holds again.
        with open(os.path.join(m3, "app.txt")) as f:
            app_bytes = f.read()
        with open(os.path.join(m3, "app.txt"), "w") as f:
            f.write("a drifted implementation\n")
        drifted = attest.check(m3)
        assert not drifted["ok"] and drifted["attestations"][0]["drifted"], \
            "a drifted build refuses the old attestation"
        with open(os.path.join(m3, "app.txt"), "w") as f:
            f.write(app_bytes)
        assert attest.check(m3)["ok"], "the frozen bytes restored, the attestation holds"
        st_path = os.path.join(m3, a["statement"])
        with open(st_path, "a") as f:
            f.write("\n")                                        # tamper the statement
        assert not attest.check(m3, signers)["ok"], "a tampered statement refuses"
        imported = os.path.join(d, "back")
        with open(os.path.join(imported, "app.txt"), "w") as f:
            f.write("no longer satisfies the gate\n")            # generated: root still fresh
        assert kernel.verify(imported)["ok"], "identity survives a generated tamper"
        try:
            attest.attest(imported, key, "checker@basin")
            raise AssertionError("attest must never notarize a carried verdict")
        except kernel.ClaimError:
            pass
        with open(os.path.join(imported, "V"), "w") as f:
            f.write("tampered")                                  # and a broken pin refuses too
        try:
            attest.attest(imported, key, "checker@basin")
            raise AssertionError("attest must refuse a broken claim")
        except kernel.ClaimError:
            pass

        # the signature chain: signed identity folds bottom-up over the DAG, and
        # localizes — a change at one layer moves its node and every node above,
        # never one below (the lowest node that moves names the floor).
        lib_s = registry.sign_root(lib, ws)
        app_s = registry.sign_root(app, ws)
        assert app_s == kernel.sign_node(kernel.verify(app)["root"],
                                         kernel.build_digest(app), [lib_s]), \
            "app's node folds lib's node (bottom-up)"
        with open(os.path.join(app, "app.txt"), "w") as f:
            f.write("one implementation, differently\n")          # regenerate app
        assert registry.sign_root(app, ws) != app_s, "editing a layer's bytes moves its node"
        assert registry.sign_root(lib, ws) == lib_s, "the floor's node held (localization)"
        # a chain root over an incomplete DAG is not a chain root: a declared
        # component missing from the registry must refuse the fold, not elide.
        lib_aside = os.path.join(d, "lib-aside")
        shutil.move(lib, lib_aside)
        try:
            registry.sign_root(app, ws)
            raise AssertionError("sign_root must refuse a missing declared component")
        except kernel.ClaimError:
            pass
        shutil.move(lib_aside, lib)
        assert registry.sign_root(lib, ws) == lib_s, "restored, the fold holds again"

        # the signing ceremony: accountable authorization over the chain. Refuses
        # a claim whose verdicts do not reproduce (audit), signs the chain root
        # and the review packet, and verifies against a recomputed chain. SIGNED
        # means AUTHORIZED (by a trusted signer) AND PROVEN (a recorded proof) —
        # the two facts are coupled, and both are verifier-relative through the
        # anchor.
        mm = os.path.join(d, "mm")                                 # a fresh, clean build
        registry.rebuild_chain(app, "printf 'yet another implementation' > app.txt", mm, ws=ws)
        pkt = attest.review_packet(mm, ws=ws)
        assert pkt["sign_root"] and pkt["root"] and pkt["audit"]["ok"], "the review packet is assembled"
        assert "proof" in pkt, "the packet carries proof status — the reviewer sees the ladder"
        signed = attest.sign(mm, key, "checker@basin", ws=ws)
        assert signed["ceremony"] == "RETICULI_CLAIM_BASIN_V1", "the ceremony is named"
        assert os.path.isfile(os.path.join(mm, signed["signature"])), "the statement is signed"
        checked = attest.sign_check(mm, ws=ws, signers=signers)
        assert checked["authorizations"][0]["verdict"] == "authorized", "authorizer identity anchored"
        row = checked["authorizations"][0]
        assert row["packet_holds"], "the signed digest binds the stored review packet"
        assert row["proof_recorded"] is False, \
            "the statement says whether a proof was recorded (none here) — " \
            "authorization is never mistaken for proof"
        os.environ["RETICULI_SIGNERS"] = signers                   # anchor: trust checker@basin
        try:
            assert kernel.phase(mm) == "sealed", "authorized but not proven is not signed"
            # the packet is what the keyholder reviewed: swap it or delete it and
            # the authorization must refuse.
            ppath = os.path.join(mm, signed["packet"])
            with open(ppath) as f:
                packet_bytes = f.read()
            with open(ppath, "w") as f:
                f.write('{"audit": {"ok": true}, "note": "forged after the ceremony"}\n')
            assert not attest.sign_check(mm, ws=ws, signers=signers)["ok"], "a forged packet refuses"
            os.remove(ppath)
            assert not attest.sign_check(mm, ws=ws, signers=signers)["ok"], "a missing packet refuses"
            with open(ppath, "w") as f:
                f.write(packet_bytes)
            assert attest.sign_check(mm, ws=ws, signers=signers)["ok"], "the exact packet restored, holds"

            # now record a genuine proof on mm (preserving its components) and
            # re-sign: trusted authorization + recorded proof = signed.
            comps = kernel.read_manifest(mm).get("components")
            m2mm = os.path.join(d, "m2mm")
            shutil.copytree(mm, m2mm)
            m3mm = os.path.join(d, "m3mm")
            registry.rebuild_chain(app, "printf 'a third implementation' > app.txt", m3mm, ws=ws)
            tm = kernel.crosscheck(mm, m2mm, m3mm)
            assert tm["satisfied"], "mm crosschecks against a distinct M2/M3"
            registry.seal_with(mm, proof={"kind": "crosscheck", "m2": tm["roots"]["M2"],
                                          "m3": tm["roots"]["M3"]}, components=comps)
            attest.sign(mm, key, "checker@basin", ws=ws)          # re-sign over the proven claim
            assert kernel.phase(mm) == "signed", "trusted authorization + recorded proof = signed"
            with open(os.path.join(mm, signed["statement"]), "a") as f:
                f.write("\n")                                     # tamper the signed statement
            assert not attest.sign_check(mm, ws=ws, signers=signers)["ok"], "a tampered signature refuses"
            assert kernel.phase(mm) == "sealed", "and demotes: the authorization no longer verifies"
        finally:
            os.environ.pop("RETICULI_SIGNERS", None)
        broke = os.path.join(d, "broke")
        registry.rebuild_chain(app, "printf 'a broken implementation' > app.txt", broke, ws=ws)
        with open(os.path.join(broke, "V"), "w") as f:
            f.write("carried, not earned")
        try:
            attest.sign(broke, key, "checker@basin", ws=ws)
            raise AssertionError("sign must refuse a claim whose verdicts do not reproduce")
        except kernel.ClaimError:
            pass

        # GATES COMPOSE, VERDICTS NEVER CARRY. A dependent that ships a component's
        # code (a `from` produce step) must have that code re-earned by the
        # component's OWN gate, on the shipped bytes: audit_deep. A forgery the
        # dependent's gate cannot see — the component's claim broken, the
        # dependent's check still green — fails the dependent's deep audit, and
        # the deep crosscheck with it. And the component's CLAIM (recipe, inputs,
        # pins; never its generated bytes) travels with an export, so an import
        # can re-earn every layer from the bytes it received.
        libc = os.path.join(d, "libcode")
        _write(libc, {"claim.toml": LIBCODE, "lib.py": "def val():\n    return 42\n",
                      "lib_check.py": "import sys\nsys.path.insert(0, '.')\nfrom lib import val\n"
                                      "assert val() == 42\nopen('LIB_OK', 'w').write('lib-ok\\n')\n"})
        subprocess.run("python3 lib_check.py", shell=True, cwd=libc, check=True)
        rl = kernel.seal(libc)
        appc = os.path.join(d, "appcode")
        _write(appc, {"claim.toml": APPCODE, "lib.py": "def val():\n    return 42\n",
                      "app.py": "from lib import val\n\n\ndef answer():\n    return val()\n",
                      "app_check.py": "import sys\nsys.path.insert(0, '.')\nfrom app import answer\n"
                                      "assert answer() == 42\nopen('APP_OK', 'w').write('app-ok\\n')\n"})
        shutil.copytree(libc, os.path.join(appc, ".reticuli", "sealed", "libcode"))
        subprocess.run("python3 app_check.py", shell=True, cwd=appc, check=True)
        registry.seal_with(appc, components=[{"input": "lib.py", "component": "libcode",
                                              "root": rl["root"], "output": "lib.py"}])
        deep = registry.audit_deep(appc)
        assert deep["ok"] and [r["root"] for r in deep["rungs"]] == [rl["root"]], "the chain audits deep"
        assert deep["rungs"][0]["bytes_from"] == ["lib.py"], "on the dependent's shipped bytes"
        with open(os.path.join(appc, "lib.py"), "w") as f:      # breaks lib's claim, not app's
            f.write("def val():\n    return 42\nimport sys\nif 'lib_check' in sys.argv[0]: raise SystemExit(1)\n")
        assert kernel.verify(appc)["ok"] and kernel.audit(appc)["ok"], "the dependent's own gate is blind to it"
        deep = registry.audit_deep(appc)
        assert not deep["ok"] and deep["rungs"][0]["name"] == "libcode" and not deep["rungs"][0]["ok"], \
            "the component's gate, re-run on the shipped bytes, is not"
        shutil.rmtree(os.path.join(appc, ".reticuli", "sealed"))
        assert registry.audit_deep(appc)["rungs"][0]["status"] == "unresolved", "an unresolvable layer is a failed layer"
        shutil.copytree(libc, os.path.join(appc, ".reticuli", "sealed", "libcode"))
        with open(os.path.join(appc, "lib.py"), "w") as f:
            f.write("def val():\n    return 42\n")
        ctar = os.path.join(d, "appcode.tar")
        transfer.export(appc, ctar)
        with tarfile.open(ctar) as t:
            names = set(t.getnames())
        assert ".reticuli/deps/libcode/lib_check.py" in names and \
            ".reticuli/deps/libcode/.reticuli/manifest.json" in names, "the component's claim travels"
        assert ".reticuli/deps/libcode/lib.py" not in names, "its generated bytes do not"
        m2c = os.path.join(d, "appcode-m2")
        assert transfer.import_(ctar, m2c)["ok"]
        assert registry.audit_deep(m2c)["ok"], "the import re-earns every layer from bytes alone"
        m3c = os.path.join(d, "appcode-m3")
        registry.rebuild_chain(appc, CODE_PRODUCER, m3c)
        assert registry.crosscheck_deep(appc, m2c, m3c)["satisfied"], "deep crosscheck holds on an honest chain"
        with open(os.path.join(m3c, "lib.py"), "w") as f:
            f.write("def val():\n    return 42\nimport sys\nif 'lib_check' in sys.argv[0]: raise SystemExit(1)\n")
        assert kernel.crosscheck(appc, m2c, m3c)["satisfied"], "a shallow crosscheck is fooled by a forged layer"
        assert not registry.crosscheck_deep(appc, m2c, m3c)["satisfied"], "the deep one is not"

        # the registry reports phase from the verifiable state, never from a
        # manifest bit: injecting "proof" into a stored claim's manifest must not
        # surface it as signed anywhere (claims, deps, structure).
        forged = kernel.read_manifest(app)
        forged["proof"] = {"kind": "crosscheck", "m2": "forged", "m3": "forged"}
        with open(os.path.join(app, kernel.MANIFEST), "w") as f:
            json.dump(forged, f)
        assert all(r["phase"] == "sealed" for r in registry.claims(ws)), \
            "an injected proof must not surface as signed in the registry"
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    with open("EXCHANGE_OK", "w") as f:
        f.write("exchange-ok\n")
    print("exchange-ok")
