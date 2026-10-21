"""A furnished claim must travel whole: export carries every pinned file.

The recipe's literal `inputs` list is not the pinned set — the declared
`environment` file and an inputs manifest's entries are hashed into the
root too. A tar missing any of them unpacks to a directory that cannot
re-derive its own root (found by the first crosscheck of a furnished
claim: its M2 leg materialized without requirements.lock).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import kernel, transfer


def _seal(d, recipe_toml, files):
    d.mkdir()
    (d / "reticuli.toml").write_text(recipe_toml)
    for name, body in files.items():
        path = d / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    kernel.seal(str(d))


def test_export_carries_the_environment_file(tmp_path):
    _seal(tmp_path / "claim",
          '[claim]\nname = "furnished"\ninputs = ["check.py"]\n'
          'environment = "requirements.lock"\n\n'
          '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
          'run = "python3 check.py && printf ok > OK"\n',
          {"check.py": "assert True\n",
           "requirements.lock": "# pinned\n",
           "OK": "ok"})
    archive = tmp_path / "furnished.tar"
    transfer.export(str(tmp_path / "claim"), str(archive))
    out = transfer.import_(str(archive), str(tmp_path / "copy"))
    assert out["verdict"] == "fresh", "the imported bytes must re-derive the sealed root"
    assert os.path.isfile(tmp_path / "copy" / "requirements.lock")


def test_export_carries_manifest_listed_inputs(tmp_path):
    _seal(tmp_path / "claim",
          '[claim]\nname = "corpus"\nformat = 2\ninputs_manifest = "INPUTS"\n\n'
          '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
          'run = "python3 check.py && printf ok > OK"\n',
          {"INPUTS": "check.py\ncases/a.txt\n",
           "check.py": "assert True\n",
           "cases/a.txt": "a\n",
           "OK": "ok"})
    archive = tmp_path / "corpus.tar"
    transfer.export(str(tmp_path / "claim"), str(archive))
    out = transfer.import_(str(archive), str(tmp_path / "copy"))
    assert out["verdict"] == "fresh", "the imported bytes must re-derive the sealed root"
    assert os.path.isfile(tmp_path / "copy" / "cases" / "a.txt")
