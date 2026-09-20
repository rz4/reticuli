# The kernel-core claim

*A demonstration artifact — the innermost layer of reticuli, sealed as a claim.*

This is reticuli's **identity core** sealed as a standalone claim: the constants,
the path and bytes boundaries, recipe parsing, the canonical root and
build-digest, and seal/verify — everything the kernel needs before it ever runs a
gate. It is the bottom of the self-hosting tower, carved out of the kernel in the
2026-09-19 decomposition so the kernel itself can be rebuilt as a chain of
sub-claims.

- **root** `35bba64f…`
- **generated** `reticuli/__init__.py`, `reticuli/_kernel/__init__.py`,
  `reticuli/_kernel/inner.py` — the implementation, free within the claim.
- **pinned** `checks/kernel_inner_check.py` — the acceptance suite (golden root
  and build-digest vectors, seal/verify, the boundaries). This is a *criterion*,
  so a rebuilding producer may read it; no implementation is pinned, so the room
  stays blind.

```
PYTHONPATH=../../src python3 -m reticuli verify .   # do the bytes match the root?
PYTHONPATH=../../src python3 -m reticuli audit .    # re-earn the verdict, cold
```

`criteria/kernel_parity.py` in the repository holds `criteria/kernel_inner_check.py`
to the copy here, so the criterion this repository publishes cannot drift from the
one this claim was sealed against.
