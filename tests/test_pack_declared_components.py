"""Recipe-in-place packing must honor `from` steps.

A produce step's `from = "<component>"` declares that a registered claim
supplies the output. The flag path (`pack --component`) writes the manifest
links every downstream verb keys on — incremental rebuild, deep audit,
export of the dependency chain — but the recipe-in-place path dropped
them, so a composed claim sealed from its reticuli.toml rebuilt into a
room missing a whole layer (found by the first codex rebuild of a
composed claim: its conftest import of the component failed).
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import kernel, pack, registry


def _component(tmp_path):
    comp = tmp_path / "comp"
    comp.mkdir()
    (comp / "impl.py").write_text("answer = 42\n")
    (comp / "check.py").write_text(
        "from impl import answer\nassert answer == 42\n"
        "open('OK', 'w').write('ok')\n")
    pack.pack(str(comp), "comp", ["impl.py"], ["check.py"],
              "python3 check.py", "OK")
    return comp


def _upper(tmp_path, comp, from_name="comp"):
    ws = tmp_path / "upper"
    ws.mkdir()
    if comp is not None:
        registry.pull(str(comp), str(ws))
    else:
        (ws / "impl.py").write_text("answer = 42\n")
    (ws / "check2.py").write_text(
        "from impl import answer\nassert answer == 42\n"
        "open('OK2', 'w').write('ok')\n")
    (ws / "reticuli.toml").write_text(
        '[claim]\nname = "upper"\ninputs = ["check2.py"]\n\n'
        '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n'
        f'from = "{from_name}"\n\n'
        '[[step]]\nkind = "gate"\noutput = "OK2"\nclass = "validated"\n'
        'run = "python3 check2.py && printf ok > OK2"\n')
    return ws


def test_from_steps_become_manifest_links(tmp_path):
    comp = _component(tmp_path)
    ws = _upper(tmp_path, comp)
    pack.pack_declared(str(ws))
    links = kernel.read_manifest(str(ws)).get("components")
    assert links, "the sealed manifest must carry the component links"
    assert links[0]["component"] == "comp"
    assert links[0]["output"] == "impl.py"
    assert links[0]["root"] == kernel.read_manifest(str(comp))["root"]


def test_from_step_without_registered_component_refuses(tmp_path):
    ws = _upper(tmp_path, None, from_name="ghost")
    with pytest.raises(kernel.ClaimError, match="ghost"):
        pack.pack_declared(str(ws))
    assert not os.path.isfile(ws / kernel.MANIFEST), "nothing may seal"
