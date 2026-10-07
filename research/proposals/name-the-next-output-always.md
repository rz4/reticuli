# Proposal — the producer is always told which output to write

*Staged 2026-10-06, from closure trial 1 fourth attempt (r8) — the
trial that re-earned REPO_OK and then could not drive a producer. A
contract decision for the keyholder; nothing here moves a root until
signed. Fourth plank of the producer-environment contract, after the
jail (free-the-producer) and HOME (the-producer-keeps-its-home).*

## The finding

The r8 tree's `_produce` sets `RETICULI_OUTPUT` **only when the claim
has exactly one generated output**, and sets it to the output's
RELATIVE path:

    env[core._ENV_OUTPUTS] = json.dumps(outputs)
    if len(outputs) == 1:
        env[core._ENV_OUTPUT] = outputs[0]

The original sets it whenever there is a target — the first output not
yet present, else the first output — as an ABSOLUTE path. So on any
claim with two or more generated outputs the r8 kernel hands a
producer no target, and the bundled producers (which read
`os.environ["RETICULI_OUTPUT"]`) die with a KeyError before reaching
the model. Measured twice in one run: the judge's generation-2 core
rebuild (three outputs) and the condition-4 CLI trial on the same
claim.

Every pinned producer fixture in the boundary happens to have exactly
ONE generated output — `kernel_check`'s two producer probes,
`launcher_check`'s, `exchange_check`'s dispatcher (which matches on
the path's tail, so a relative value passes it too). `core_check`
pins the variable's SPELLING. Nothing pins that it is set at all, or
that it is absolute. A kernel can therefore satisfy the entire
boundary and be unable to drive any real producer on any real
multi-output claim — which is every layer of this repository's own
chain.

## What must be pinned if accepted

`build_check`'s producer block gains a MULTI-OUTPUT probe: a claim
with two generated outputs, rebuilt by a producer that asserts
`RETICULI_OUTPUT` is set, is absolute, and names one of the claim's
pending outputs (and that `RETICULI_OUTPUTS` lists them all). One
fixture, three assertions — a criteria edit, so a root move, hence the
signature gate.

## The pattern, now four deep

jail → HOME → next-output, each found by a different generation
choosing a different defensible shortcut, none derivable in advance,
each invisible because the probes only ever covered the witnesses
seen. The producer-environment contract is being discovered exactly
the way the jail floor was: one plank per draw. Worth noting for the
write-up — this is the clearest measured example of the method's own
cost model, where a pin's coverage is exactly as wide as the fixture
that carries it.

## Status

Signed by the keyholder 2026-10-06 ("I sign off start the next r") and
landed the same night as one bundle with its sibling (see the
provenance record revision-2026-10-06-the-named-target-bundle.md).
