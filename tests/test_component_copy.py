"""Shared ancestors must stay compact and portable when claims are copied."""
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reticuli import kernel, pack, registry, transfer


def test_shared_ancestors_survive_copy_and_transport(tmp_path):
    source = tmp_path / "source"
    layers = []
    for index in range(9):
        room = source / f"layer{index}"
        room.mkdir(parents=True)
        (room / "impl.py").write_text("answer = 42\n")
        (room / "check.py").write_text(
            "from impl import answer\nassert answer == 42\n"
            "open('OK', 'w').write('ok')\n")
        component = None if not layers else {
            "name": layers[-1].name, "claim": str(layers[-1]),
            "outputs": ["impl.py"],
        }
        pack.pack(str(room), room.name, ["impl.py"], ["check.py"],
                  "python3 check.py", "OK", component=component, claim_format=4)
        store = room / kernel.STORE / "sealed"
        store.mkdir(parents=True, exist_ok=True)
        for ancestor in layers:
            link = store / ancestor.name
            if not link.exists():
                link.symlink_to(ancestor, target_is_directory=True)
        layers.append(room)

    copied = tmp_path / "copied"
    registry.copy_claim(str(layers[-1]), str(copied))
    root = kernel.read_manifest(str(copied))["root"]
    # Exactly one physical implementation per layer, not an unfolded tree.
    implementations = [Path(base) / name for base, _, names in os.walk(copied)
                       for name in names if name == "impl.py"]
    assert len(implementations) == len(layers)
    shutil.rmtree(source)
    assert kernel.verify(str(copied))["ok"]
    assert registry.audit_deep(str(copied))["ok"]
    assert len(registry.chain(str(copied))) == len(layers) - 1

    archive = tmp_path / "claim.tar"
    transfer.export(str(copied), str(archive))
    shutil.rmtree(copied)
    restored = tmp_path / "restored"
    transfer.import_(str(archive), str(restored))
    assert kernel.read_manifest(str(restored))["root"] == root
    assert registry.audit_deep(str(restored))["ok"]
