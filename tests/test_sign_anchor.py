"""Authorization requires an anchor: what a receiver can and cannot conclude.

Found 2026-11-03 by walking a receiver's path on the repository's own signed
claim. `sign_check`'s roll-up accepted an unanchored `intact` row as `ok`, so
a statement re-signed with a throwaway key the keyholder had never seen
reported `authorized = true` and exit 0. `docs/receiving.md` had the doctrine
right in prose ("with no allowed_signers file, the answer is always nothing is
authorized to you") while the tool said the opposite, and the one criterion
covering this surface only ever exercised the anchored path -- the
configuration the author runs, not the one a stranger has.

The four cases a receiver can be in, pinned here as a matrix:

    anchor?  signature   verdict     ok
    no       genuine     intact      False   nothing is authorized TO YOU
    no       forged      intact      False   indistinguishable from genuine
    yes      genuine     authorized  True
    yes      forged      invalid     False

The third and fourth rows are the point of an anchor: only there does the
tool distinguish the keyholder from anyone else.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import attest, kernel

RECIPE = (
    '[claim]\nname = "vouched"\ninputs = ["check.py"]\n\n'
    '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
    '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
    'run = "python3 check.py && printf ok > OK"\n'
)
FILES = {
    "check.py": "from impl import answer\nassert answer == 42\n"
                "open('OK', 'w').write('ok')\n",
    "impl.py": "answer = 42\n",
    "OK": "ok",
}

IDENTITY = "keyholder@example.org"


def _keypair(path, comment):
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(path), "-N", "",
                    "-C", comment, "-q"], check=True)
    return path


def _anchor(path, pub, identity=IDENTITY):
    """An allowed_signers file: the receiver's own trust anchor."""
    key = Path(pub).read_text().split()
    path.write_text(f"{identity} {key[0]} {key[1]}\n")
    return path


@pytest.fixture
def signed(tmp_path):
    """A sealed, audited, signed claim plus the keyholder's key."""
    if shutil.which("ssh-keygen") is None:
        pytest.skip("ssh-keygen is not on this host")
    claim = tmp_path / "claim"
    claim.mkdir()
    (claim / "reticuli.toml").write_text(RECIPE)
    for name, body in FILES.items():
        (claim / name).write_text(body)
    kernel.seal(str(claim))
    key = _keypair(tmp_path / "keyholder", "the keyholder")
    attest.sign(str(claim), str(key), IDENTITY)
    return claim, key


def _resign_with(claim, key):
    """Re-sign the EXISTING statement with another key: the forgery a
    receiver must not mistake for the keyholder's authorization. The
    statement's bytes, identity string included, are untouched."""
    base = Path(claim) / kernel.SIGN_DIR
    stmt = next(p for p in base.iterdir() if p.name.endswith(".sign.json"))
    sig = Path(str(stmt) + ".sig")
    sig.unlink()
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key),
                    "-n", kernel.SIGN_NAMESPACE, str(stmt)],
                   check=True, capture_output=True)


class TestUnanchored:
    def test_a_genuine_signature_is_intact_but_not_authorized(self, signed):
        claim, _ = signed
        r = attest.sign_check(str(claim))
        assert r["anchored"] is False
        (row,) = r["authorizations"]
        assert row["verdict"] == "intact", "the signature IS self-consistent"
        assert row["chain_holds"] and row["packet_holds"]
        assert r["ok"] is False, (
            "without an anchor nothing is authorized to the receiver: "
            "`intact` says a statement was signed, not whose it is")

    def test_a_forged_signature_is_indistinguishable(self, signed):
        claim, _ = signed
        forger = _keypair(Path(claim).parent / "forger", "not-the-keyholder")
        _resign_with(claim, forger)
        r = attest.sign_check(str(claim))
        (row,) = r["authorizations"]
        assert row["verdict"] == "intact"
        assert row["identity"] == IDENTITY, (
            "the identity a row prints comes from the statement's own bytes, "
            "which the signer wrote: it is a claim, not a verification")
        assert r["ok"] is False, "a forgery must not read as authorized"


class TestAnchored:
    def test_the_keyholders_signature_authorizes(self, signed, tmp_path):
        claim, key = signed
        anchor = _anchor(tmp_path / "allowed_signers", str(key) + ".pub")
        r = attest.sign_check(str(claim), signers=str(anchor))
        assert r["anchored"] is True and r["ok"] is True
        assert r["authorizations"][0]["verdict"] == "authorized"

    def test_a_forgery_is_caught_as_invalid(self, signed, tmp_path):
        claim, key = signed
        anchor = _anchor(tmp_path / "allowed_signers", str(key) + ".pub")
        forger = _keypair(tmp_path / "forger", "not-the-keyholder")
        _resign_with(claim, forger)
        r = attest.sign_check(str(claim), signers=str(anchor))
        assert r["authorizations"][0]["verdict"] == "invalid", (
            "anchored, the key that actually signed is checked against the "
            "receiver's anchor, and a stranger's key fails it")
        assert r["ok"] is False

    def test_an_anchor_naming_another_identity_does_not_authorize(
            self, signed, tmp_path):
        claim, key = signed
        # the receiver trusts somebody, just not this signer
        anchor = _anchor(tmp_path / "allowed_signers", str(key) + ".pub",
                         identity="someone.else@example.org")
        r = attest.sign_check(str(claim), signers=str(anchor))
        assert r["ok"] is False, "trust is per-identity, not per-key-file"


class TestTheSignatureFreezesAnImplementation:
    def test_editing_a_generated_output_breaks_the_chain(self, signed, tmp_path):
        claim, key = signed
        anchor = _anchor(tmp_path / "allowed_signers", str(key) + ".pub")
        assert attest.sign_check(str(claim), signers=str(anchor))["ok"]
        # the root does not move (generated bytes are outside identity)...
        (claim / "impl.py").write_text("answer = 6 * 7\n")
        assert kernel.verify(str(claim))["ok"], "identity floats above the impl"
        # ...but the signature froze THIS implementation, so it no longer holds
        r = attest.sign_check(str(claim), signers=str(anchor))
        assert r["authorizations"][0]["chain_holds"] is False
        assert r["ok"] is False, (
            "a signature binds the build digest: re-implementing requires "
            "re-authorizing, even though the claim is the same claim")


class TestTheStatementIsNotTrustedOnRead:
    def test_a_swapped_packet_refuses(self, signed, tmp_path):
        claim, key = signed
        anchor = _anchor(tmp_path / "allowed_signers", str(key) + ".pub")
        base = claim / kernel.SIGN_DIR
        packet = next(p for p in base.iterdir() if p.name.endswith(".packet.json"))
        doc = json.loads(packet.read_text())
        doc["gates"] = 99                      # rewrite what was "reviewed"
        packet.write_text(json.dumps(doc))
        r = attest.sign_check(str(claim), signers=str(anchor))
        assert r["authorizations"][0]["packet_holds"] is False
        assert r["ok"] is False, (
            "the packet is what the keyholder reviewed; unbound it could be "
            "swapped after the fact")

    def test_an_unsigned_claim_is_not_ok(self, tmp_path):
        claim = tmp_path / "bare"
        claim.mkdir()
        (claim / "reticuli.toml").write_text(RECIPE)
        for name, body in FILES.items():
            (claim / name).write_text(body)
        kernel.seal(str(claim))
        r = attest.sign_check(str(claim))
        assert r["authorizations"] == [] and r["ok"] is False, (
            "no statements is not vacuous approval")
        assert os.path.isdir(claim)
