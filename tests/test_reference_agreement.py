"""The two identity implementations must agree on every claim, including the
ones that use an environment file or an inputs manifest.

The reference sealer exists to be a second, independent implementation of
spec/identity.md; its whole value is that the kernel cannot be the only
witness to a root. A claim feature the reference did not hash would give
that claim two different roots under the two tools -- a silent leak in the
one cross-check the identity has. Witnessed on an environment-declaring
claim after Phase 1 shipped the feature; pinned here.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import kernel, reference

GATE = ('\n\n[[step]]\nkind = "gate"\noutput = "V"\n'
        'class = "validated"\nrun = "printf v > V"\n')


def _seal_and_compare(d) -> tuple[str, str]:
    return kernel.root(kernel.load_recipe(str(d)), str(d)), reference.root(str(d))


def test_agree_on_a_declared_environment(tmp_path):
    (tmp_path / "reticuli.toml").write_text(
        '[claim]\nname = "e"\nenvironment = "req.lock"\ninputs = ["a.txt"]'
        + GATE)
    (tmp_path / "req.lock").write_text("pkg==1.0 --hash=sha256:" + "0" * 64 + "\n")
    (tmp_path / "a.txt").write_text("alpha\n")
    (tmp_path / "V").write_text("v")
    k, r = _seal_and_compare(tmp_path)
    assert k == r, "the environment file is a pinned input to both"


def test_agree_on_an_inputs_manifest(tmp_path):
    (tmp_path / "reticuli.toml").write_text(
        '[claim]\nname = "m"\nformat = 2\ninputs_manifest = "INPUTS"' + GATE)
    (tmp_path / "INPUTS").write_text("a.txt\nb.txt\n")
    (tmp_path / "a.txt").write_text("A\n")
    (tmp_path / "b.txt").write_text("B\n")
    (tmp_path / "V").write_text("v")
    k, r = _seal_and_compare(tmp_path)
    assert k == r, "the manifest and every path it names are pinned to both"


@pytest.mark.parametrize("claim", [
    # examples/kernel was retired while the kernel is decomposed into sub-claims;
    # it will be re-sealed as the settled core once the split lands.
    "examples/tomli", "examples/quirkcalc",
    "examples/weak", "examples/make",
])
def test_every_shipped_claim_still_agrees(claim):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, claim)
    assert kernel.root(kernel.load_recipe(d), d) == reference.root(d), \
        f"{claim}: the two implementations disagree"
