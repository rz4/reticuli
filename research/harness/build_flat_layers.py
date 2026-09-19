"""Prep a second full self-rebuild — one flat, self-contained claim per layer.

Why flat: `ret rebuild -o` does not carry a claim's component store into the
blind room (see research/provenance/revision-2026-09-19-self-rebuild-tightening.md),
so a middle layer built the selfclaim way cannot resolve the layers below it and
rebuild wrongly asks the producer to regrow the whole stack. This sidesteps that:
each layer's LOWER modules are declared as pinned INPUTS (present, read-only) and
only that layer's OWN modules are `generated`. `ret rebuild` then withholds just
the layer's modules and hands the producer everything beneath as context — which
is also the realistic setting for regrowing one part of a known codebase.

    PYTHONPATH=src python3 research/harness/build_flat_layers.py --into DIR [--only LAYER]

It prints, per layer, a ready-to-run rebuild command. Run those in a real
terminal (no ten-minute wall, no background kill); see research/harness/README.md.

The kernel layer has nothing beneath it, so its flat claim is the true blind
kernel rebuild (from kernel_check.py alone). The surface layer is the whole tool
minus the surface modules; cli.py (~2,560 lines) is the beast there.
"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import pack

# The same six layers scripts/selfclaim.py builds, in order. (layer, modules it
# ADDS, its acceptance check, the verdict that check writes.)
LAYERS = [
    ("kernel", ["__init__.py", "kernel.py"],
     "criteria/kernel_check.py", "KERNEL_OK"),
    ("exchange", ["_util.py", "registry.py", "transfer.py", "attest.py",
                  "record.py"],
     "criteria/exchange_check.py", "EXCHANGE_OK"),
    ("authoring", ["render.py", "authoring.py", "feedback.py", "pack.py"],
     "criteria/authoring_check.py", "AUTHORING_OK"),
    ("agents", ["hooks.py"],
     "criteria/agents_check.py", "AGENTS_OK"),
    ("launcher", ["launcher.py"],
     "criteria/launcher_check.py", "LAUNCHER_OK"),
    ("surface", ["assess.py", "heldout.py", "reuse.py", "cli.py", "__main__.py"],
     "criteria/surface_check.py", "SURFACE_OK"),
]


def build(into: str, only: str | None = None) -> list[tuple[str, str]]:
    if os.path.exists(into):
        shutil.rmtree(into)
    os.makedirs(into)

    carried: list[str] = []
    commands: list[tuple[str, str]] = []
    for name, adds, check, verdict in LAYERS:
        carried_here = list(carried)      # snapshot before this layer adds
        carried += adds
        if only and name != only:
            continue

        room = os.path.join(into, name)
        os.makedirs(os.path.join(room, "reticuli"))
        os.makedirs(os.path.join(room, "checks"))
        for module in carried_here + adds:
            shutil.copyfile(os.path.join(ROOT, "src", "reticuli", module),
                            os.path.join(room, "reticuli", module))
        shutil.copyfile(os.path.join(ROOT, check),
                        os.path.join(room, "checks", os.path.basename(check)))

        # THE FLAT SHAPE: this layer's own modules are generated (withheld on
        # rebuild); every lower module and the check are pinned inputs (present).
        generated = [f"reticuli/{m}" for m in adds]
        inputs = ([f"reticuli/{m}" for m in carried_here]
                  + [f"checks/{os.path.basename(check)}"])
        result = pack.pack(
            room, name,
            generated=generated,
            inputs=inputs,
            gate=f"python3 checks/{os.path.basename(check)}",
            gate_output=verdict,
        )
        out = os.path.join(into, f"{name}-rebuilt")
        cmd = (f"PYTHONPATH=src RETICULI_AGENT_TURNS=120 "
               f'RETICULI_PRICE="1.25,10" RETICULI_USAGE="{into}/{name}.usage.json" '
               f"python3 -m reticuli rebuild {room} --producer openai -o {out}")
        commands.append((name, cmd))
        print(f"{name:<10} root {result['root'][:16]}…  "
              f"({len(generated)} to regrow, {len(inputs) - 1} supplied)")
    return commands


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build flat per-layer rebuild claims")
    ap.add_argument("--into", required=True, help="scratch dir for the claims")
    ap.add_argument("--only", help="build just one layer (e.g. kernel, surface)")
    a = ap.parse_args(argv)
    cmds = build(a.into, a.only)
    print("\n# Run these in a real terminal (see research/harness/README.md):")
    for name, cmd in cmds:
        print(f"\n# --- {name} ---\n{cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
