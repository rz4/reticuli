# The repository as a claim about itself

This is the self-hosting example: `reticuli` sealed as six layered claims,
each gated by its own acceptance check, each carrying everything below it.

It is built on demand rather than committed —

```
$ python3 scripts/selfclaim.py
kernel     4b90feef318d171a842dd285c589c8f2e350f0e32627d62fa99e64a67fcfc382  (2 generated, 1 pinned)
exchange   052be1cd14c59fb10ca3a0699be0a30dbf6f711d85cb8297041fcd1d1a2ff3aa  (6 generated, 1 pinned, on kernel)
authoring  6a7bf3bfe74686a0140330c87c23b7c68db35da3330b7af784960a2f702d062d  (10 generated, 1 pinned, on exchange)
agents     6af4bfe78bbb765e802dd7a245a9d069d8aa8c584b14a06367a8918c922adb22  (11 generated, 1 pinned, on authoring)
launcher   f0cc4971085714d40b8cc2db1b4c43c649809deeeb73d466e0b4e9721c5d028b  (12 generated, 1 pinned, on agents)
surface    a9aeb35df9aa5303120dda76a2e8e90eb7284e9ae777f2794acba0f35930f75c  (14 generated, 1 pinned, on launcher)
verify: all 6 layers fresh
```

— because the interesting artifact is not the bytes. Committing the chain
would mean six nested copies of the package in git; the roots above can be
recomputed by anyone from a clean checkout, and `criteria/self_check.py` holds
them to exactly these values.

## What it demonstrates

**Composition.** Each layer declares the modules below it as generated output
supplied `from` its component. A deep audit of the outermost layer re-earns
every layer beneath, judged against the bytes the *outer* claim ships rather
than each layer's own sealed copy:

```
$ ret audit .selfclaim/surface
verdict = "earned"
layers  = "5/5 earned"
  launcher   f0cc49710857…  earned   12 from this claim
  agents     6af4bfe78bbb…  earned   11 from this claim
  authoring  6a7bf3bfe746…  earned   10 from this claim
  exchange   052be1cd14c5…  earned    6 from this claim
  kernel     4b90feef318d…  earned    2 from this claim
```

**The base layer is the kernel claim.** Built here from `src/` by a different
path entirely, the kernel layer lands on `4b90feef…` — the same root `examples/kernel/`
holds. Not a coincidence: identical criteria produce an identical name,
because the name was never about the code.

**The roots are a lockfile over behavior, not over source.** Change an
implementation and they hold; change what a layer is *checked for* and they
move. Both directions are verified in `criteria/self_check.py`:

| edit | result |
|---|---|
| append a comment to `src/reticuli/hooks.py` (generated) | `self-ok` — roots unchanged |
| append a comment to `criteria/agents_check.py` (pinned) | fails, naming `agents` and both roots |

## One honest subtlety

**Roots do not nest.** A layer's root is a hash over *its own* recipe, check,
and verdict — not over its component's root. So editing the agents check moves
the `agents` root and leaves `launcher` and `surface` unmoved, even though they
sit above it. That is deliberate: an outer claim's identity states what *it* is
checked for.

The chain's integrity therefore does not come from nested identity. It comes
from two other places: the component links recorded on each manifest (which
name the exact component root a layer was built over), and the deep audit
above, which re-runs every inner check against the shipped bytes. Where
identity genuinely does chain is in **authorization** — `sign_node(root,
digest, component_signatures)` folds a component's signatures into the node
being signed, so a signature over the outer layer commits to the inner ones.

## Running it

```
python3 scripts/selfclaim.py            # build the chain into .selfclaim/ (gitignored)
python3 criteria/self_check.py          # build it, audit it deep, hold the roots
ret audit .selfclaim/surface          # the deep audit above
ret status --tree .selfclaim/surface  # the chain, as a graph
```

The build takes a few seconds and runs all six acceptance checks — every
layer's gate is earned warm before its claim is sealed, because `pack` refuses
to seal a verdict it has not just watched be earned.
