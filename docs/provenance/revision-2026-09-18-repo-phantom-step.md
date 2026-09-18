# Revision: the repository root drops a phantom produce step

The repository claim moved on 2026-09-18, `5c81c5b5…` → `3ad6e0cc…`. One
change, strictly corrective: `reticuli.toml` no longer declares a produce
step for `src/reticuli/inspect.py`.

## What moved out of the boundary

`inspect` was retired as a verb some time ago — its strict jail became
`audit`'s default, its report folded into audit's. The module
`src/reticuli/inspect.py` was deleted with it. The recipe, though, still
carried a `produce` step naming that file, so the top-level claim kept
instructing a producer to generate a module that no longer exists and that
the gate neither builds nor checks. A blind M3 reading this recipe would be
told to write a phantom.

The step's `output`, `kind`, and `class` live in the root preimage — format
3 strips only producer guidance, not the step's shape — so the phantom was
baked into `5c81c5b5…`. Removing it necessarily moves the root, and it
should: the recipe now names exactly the files an implementation must
produce, and no more.

## Direction and blast radius

This is a corrective move, not a hardening. Removing a nonexistent output
cannot make any previously conforming implementation fail; the equivalence
class is unchanged in substance, only described honestly. The going rate for
a rebuild does not rise.

The six layer roots did not move. `inspect` had already left the layers —
its removal there is recorded in `self_check.py`'s history — and lingered
only in the top-level recipe, which the layers do not share. `python3
gate.py` re-earned `repo-ok` at the new root with every suite green,
`self_check.py` included, which is the proof the layer roots held.

## What this click is, and is not

This is an internal ratchet click. It is recorded here as a resealed old→new
pair with the gate re-earned on this machine — the accept bar we hold for an
internal correction. It is deliberately *not* cryptographically signed: an
attestation is a keyholder's act, reserved for the completion ceremony and
for external transitions once the call is open. No proof is claimed across
the moved root beyond this local re-earn. The room export tracks the new
root.
