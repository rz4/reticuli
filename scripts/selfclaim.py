"""Seal this repository as a layered chain of claims — self-hosting, on demand.

    python3 scripts/selfclaim.py [--into DIR] [--quiet]

Six claims, inner to outer. Each one carries everything below it as component
outputs (generated code supplied `from` the layer beneath) and layers its own
modules on top, gated by that layer's acceptance check:

    kernel      reticuli/{__init__,kernel}.py              identity and verdicts
    exchange    + _util, registry, transfer, attest,       claims meet claims
                  record
    authoring   + render, authoring, feedback, pack        sessions become claims
    agents      + hooks                                    the agent handshake
    launcher    + launcher                                 run latent software
    surface     + cli, __main__                            the human handshake

Nothing is generated that the layer's own gate does not judge, and each gate is
run WARM before its claim is sealed (`pack` refuses to seal an unearned
verdict). The result is deterministic: re-running reproduces every root, so the
roots below act as a lockfile over the repository's own behavior.

The chain is built on demand into a scratch directory rather than committed.
Committing it would mean six nested copies of the package in git, and the
interesting artifact is not the bytes — it is the roots, which anyone can
recompute from a clean checkout by running this script.
"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import kernel, pack

# (layer, modules it adds, the check that judges it, the verdict that check writes)
LAYERS = [
    ("kernel-core", ["__init__.py", "_kernel/__init__.py", "_kernel/inner.py"],
     "criteria/kernel_inner_check.py", "KERNEL_CORE_OK"),
    ("kernel", ["kernel.py"],
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
    ("surface", ["assess.py", "heldout.py", "reuse.py",
                 "cli.py", "__main__.py"],
     "criteria/surface_check.py", "SURFACE_OK"),
]


def build(into: str, quiet: bool = False) -> dict:
    if os.path.exists(into):
        shutil.rmtree(into)
    os.makedirs(into)

    roots: dict[str, str] = {}
    carried: list[str] = []          # every module supplied by the layers below
    previous: str | None = None

    for name, adds, check, verdict in LAYERS:
        room = os.path.join(into, name)
        os.makedirs(os.path.join(room, "reticuli"))
        os.makedirs(os.path.join(room, "checks"))

        for module in carried + adds:
            dst = os.path.join(room, "reticuli", module)
            os.makedirs(os.path.dirname(dst), exist_ok=True)   # nested: _kernel/
            shutil.copyfile(os.path.join(ROOT, "src", "reticuli", module), dst)
        shutil.copyfile(os.path.join(ROOT, check),
                        os.path.join(room, "checks", os.path.basename(check)))

        component = None
        if previous is not None:
            component = {"name": os.path.basename(previous), "claim": previous,
                         "outputs": [f"reticuli/{m}" for m in carried]}

        result = pack.pack(
            room, name,
            generated=["reticuli/*.py", "reticuli/_kernel/*.py"],
            inputs=["checks/*.py"],
            gate=f"python3 checks/{os.path.basename(check)}",
            gate_output=verdict,
            component=component,
            # The kernel-core layer IS the sealed claim at examples/kernel (the
            # identity foundation, carved out of the kernel), so it carries the
            # declared ceiling; self_check's root-equality assertion is the
            # drift catcher if these two ever disagree.
            envelope={"usd": 40.0} if name == "kernel-core" else None,
            # kernel-core IS examples/kernel, format 3 (guidance leaves the
            # root). Every layer above it, the outer kernel included, stays
            # format 1 until deliberately migrated.
            claim_format=3 if name == "kernel-core" else None,
        )
        # `pack` copies the IMMEDIATE component into this claim's store, so a
        # claim travels with its dependency. Resolution is one level deep and
        # stops at the claim's own store, so a six-deep chain would report the
        # grandparents "unresolved". Name the whole ancestry here — links, not
        # copies, since these layers already sit side by side in one workspace.
        store = os.path.join(room, kernel.STORE, "sealed")
        os.makedirs(store, exist_ok=True)
        for ancestor, _, _, _ in LAYERS[:LAYERS.index((name, adds, check, verdict))]:
            link = os.path.join(store, ancestor)
            if not os.path.exists(link):
                os.symlink(os.path.join(into, ancestor), link)

        roots[name] = result["root"]
        if not quiet:
            print(f"{name:<10} {result['root']}  "
                  f"({result['generated']} generated, {result['inputs']} pinned"
                  f"{', on ' + result['component'] if result['component'] else ''})")

        carried = carried + adds
        previous = room

    for name, _, _, _ in LAYERS:
        assert kernel.verify(os.path.join(into, name))["ok"], f"{name} must verify fresh"
    if not quiet:
        print(f"verify: all {len(roots)} layers fresh")
    return roots


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="seal this repository as a chain of claims")
    ap.add_argument("--into", default=os.path.join(ROOT, ".selfclaim"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    build(a.into, a.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
