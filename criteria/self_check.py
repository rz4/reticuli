"""The repository seals itself: six layered claims, and the roots are a lockfile.

`scripts/selfclaim.py` builds the chain — each layer carrying everything below it
as component outputs, gated by that layer's own acceptance check. This check
runs that build and holds it to three claims:

  * every layer seals and verifies fresh;
  * the outermost layer's DEEP audit re-earns every layer beneath it, on the
    bytes the outer claim ships (not on each layer's own sealed copy);
  * the six roots are exactly the values pinned below.

The third is the interesting one. These roots are a hash over each layer's
recipe, its check's bytes, and its verdict's bytes — nothing about the host, the
interpreter, or the clock. So they are a lockfile over this repository's own
behavior: change a layer's implementation and they hold; change what a layer is
CHECKED for and they move, loudly, here.

    python3 criteria/self_check.py        (from the repository root)
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import selfclaim
from reticuli import kernel, registry

# The lockfile. Recompute with: python3 scripts/selfclaim.py
PINNED = {
    # The kernel root moved once, deliberately: the v2.1 revision pinned seven
    # measured under-specifications. Its predecessor, d64cc301…, is kept proven
    # at examples/kernel-2.0/. The five layers above it moved when their
    # suites stopped writing a verdict outside a claim — a change to what each
    # layer is checked for, which is exactly what this lockfile exists to
    # notice. Surface moved again when `assess` joined it: a new verb means a
    # new module in the layer and a new entry in its check. And again when
    # `heldout.py` joined it — a module in a layer is a produce step in that
    # layer's recipe, and the recipe text is inside the root, so composition
    # moves a root even though every module's BYTES stay generated. The same
    # revision edited `render.py` in the authoring layer and moved nothing,
    # which is the other half of the same fact.
    #
    # 2026-09-16: the five moved again when the recipe file was renamed
    # claim.toml -> reticuli.toml. The FILENAME is not in the root preimage, so
    # the rename alone moved nothing -- every example root is byte-identical
    # across it. What moved these is that each suite guarded writing its verdict
    # on `isfile("claim.toml")`, meaning "am I running as a claim's gate?", and
    # had to learn the second name. A criterion changed, so the roots it defines
    # changed. The kernel stayed at 4b90feef because its suite never asked.
    #
    # 2026-09-16, later: exchange and everything above it moved when the layer
    # grew record.py (spec/record.md's authoring side) and its suite grew the
    # record batteries -- a new module is a produce step in the layer's recipe,
    # and a wider criterion is a stronger claim. The kernel, one layer below,
    # did not move; consuming a record as a crosscheck leg is its side and
    # waits for the v2.2 revision.
    "kernel":    "4b90feef318d171a842dd285c589c8f2e350f0e32627d62fa99e64a67fcfc382",
    "exchange":  "25a285c023952bd9c9e9836f8ea0caf7c5eb2eb45fb816a7c36ef82722595e6c",
    "authoring": "63237fd5b2f2cbb727d0b953bc0b78d066589f75ce15e9f4890a88f4238b4b19",
    "agents":    "96ad9b75cedf4b020ff3ec9509e1ada3bf14bd692a72e219487f558b32ab22fe",
    "launcher":  "c19ff3a9760866abb035e3b1972cf5791924a81ed73eaa4343d7d7443cc56b03",
    "surface":   "e57e05652fc7ba8abbe05eea601c5cfcdec0f27ed8991490779857e4fbac087d",
}


def battery() -> None:
    work = tempfile.mkdtemp(prefix="selfclaim-")
    try:
        roots = selfclaim.build(os.path.join(work, "chain"), quiet=True)

        assert list(roots) == [layer for layer, *_ in selfclaim.LAYERS], \
            "the chain has every layer, in order"

        for layer in roots:
            claim = os.path.join(work, "chain", layer)
            assert kernel.verify(claim)["ok"], f"{layer} verifies fresh"

        # The kernel layer is not merely *like* the sealed kernel claim: built
        # from src/ by a different path, it lands on the same root the blind
        # rebuild earned and `examples/kernel/` holds. Identity is the claim, not the code.
        # Cross-check the chain's base layer against the sealed claim itself,
        # not just against the literal in PINNED. Conditional because
        # examples/kernel/ is deliberately NOT pinned into the repository's root
        # claim -- pinning it would hand a working kernel to a rebuilding
        # producer -- so it is absent when this suite runs inside an audit
        # workspace. PINNED still holds the root there; this adds an independent
        # artifact to compare against wherever one exists.
        sealed = os.path.join(ROOT, "examples", "kernel")
        if os.path.isfile(os.path.join(sealed, kernel.MANIFEST)):
            assert roots["kernel"] == kernel.read_manifest(sealed)["root"], \
                "the chain's base layer IS the sealed kernel claim"

        # A deep audit judges each layer's check against the bytes the OUTER
        # claim ships, so an inner layer cannot pass on its own sealed copy
        # while shipping something else.
        deep = registry.audit_deep(os.path.join(work, "chain", "surface"))
        assert deep["ok"], f"the whole chain re-earns: {deep.get('verdict')}"
        assert len(deep["layers"]) == len(selfclaim.LAYERS) - 1, "every layer beneath is judged"
        assert all(r["ok"] for r in deep["layers"]), \
            f"every layer earned: {[(r['name'], r.get('status')) for r in deep['layers']]}"

        drift = {k: (PINNED[k], v) for k, v in roots.items() if PINNED.get(k) != v}
        assert not drift, (
            "the self-claim roots moved — a layer's CHECK or its verdict changed, "
            f"not just its implementation: {drift}. If intended, re-pin from "
            "`python3 scripts/selfclaim.py`.")

        print(f"self-ok ({len(roots)} layers sealed, {len(deep['layers'])} re-earned deep)")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    battery()
