"""The repository seals itself: six layered claims, and the roots are a lockfile.

`tools/selfclaim.py` builds the chain — each layer carrying everything below it
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

    python3 checks/self_check.py        (from the repository root)
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import selfclaim
from reticuli import kernel, registry

# The lockfile. Recompute with: python3 tools/selfclaim.py
PINNED = {
    # Moved once, deliberately: the v2.1 revision pinned seven measured
    # under-specifications, changing what the kernel is CHECKED for. The
    # predecessor, d64cc301…, is kept proven at provenance/birth/.
    "kernel":    "4b90feef318d171a842dd285c589c8f2e350f0e32627d62fa99e64a67fcfc382",
    "exchange":  "052be1cd14c59fb10ca3a0699be0a30dbf6f711d85cb8297041fcd1d1a2ff3aa",
    "authoring": "6a7bf3bfe74686a0140330c87c23b7c68db35da3330b7af784960a2f702d062d",
    "agents":    "6af4bfe78bbb765e802dd7a245a9d069d8aa8c584b14a06367a8918c922adb22",
    "launcher":  "f0cc4971085714d40b8cc2db1b4c43c649809deeeb73d466e0b4e9721c5d028b",
    "surface":   "a9aeb35df9aa5303120dda76a2e8e90eb7284e9ae777f2794acba0f35930f75c",
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
        # rebuild earned and `seed/` holds. Identity is the claim, not the code.
        assert roots["kernel"] == kernel.read_manifest(os.path.join(ROOT, "seed"))["root"], \
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
            "`python3 tools/selfclaim.py`.")

        print(f"self-ok ({len(roots)} layers sealed, {len(deep['layers'])} re-earned deep)")
        with open(os.path.join(ROOT, "SELF_OK"), "w", encoding="utf-8") as f:
            f.write("self-ok\n")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    battery()
