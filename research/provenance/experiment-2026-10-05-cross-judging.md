# Experiment — the descendants judge, and the parent flinches first

*2026-10-05. First cross-judging run: the original and both r3 regrown
trees judging one claim battery, authoring one claim, and each
orchestrating a blind rebuild. Harness and full matrix:
`research/harness/crossjudge/`. Root `3e7dc827…` throughout.*

## The question

Succession showed descendants satisfy the parent's criteria. This run
asks the stronger thing: can they do the parent's JOB — accept good
claims, refuse broken ones for the right reason, and drive the
production of another conforming descendant?

## Answers

**They judge.** 18/18 verdicts on the six-claim battery land where the
contract puts them, for all three tools: good and variant accepted;
tampered input and edited recipe refused as identity damage; tampered
generated output and a forged verdict file survive verify (the root
never covered them) and fall to audit's re-earning. The forged-verdict
case matters most: all three re-earn rather than trust a verdict file
already present. No descendant can be fooled by the lie the design
most worries about.

**They reproduce.** Each tool rebuilt the good claim blind to a sealed
child at the parent's root, and every child passed audit under both
other tools — a 3×2 cross-acceptance with zero refusals.

**The parent flinches first.** The one divergence in fresh authoring is
the ORIGINAL's: its `pack` writes default producer guidance
(`request = "regenerate … to pass the gate"`) into format-1 claims,
where guidance is identity. Both descendants — independently — omit it
and agree with each other, because no criterion pins guidance text, and
by the project's own doctrine none should. Three kernels, two names,
and the odd one out is the parent. Staged:
`research/proposals/author-at-format-3.md`.

**The sandbox signal is silent.** The original's rebuild reports
`quarantine: seatbelt`; both descendants report nothing. No criterion
makes a kernel say what jail a verdict was earned in — which is exactly
the provenance a trust-transfer acceptor needs. Staged:
`research/proposals/pin-the-sandbox-signal.md`.

**Era-faithful drift, on schedule.** The r3 trees say `error`/`earned`
where the current vocabulary pin says `failed`/`broken` — they predate
the pin. predictions_r4.md (P1) commits to the r4 generation closing
this; this run is the baseline it will be scored against.

## The method note

The harness first drove the tools by CLI flags and measured instead
that flag spellings are unpinned (`-C`, `--into` exist only in the
original; codex spells it `-o`). It now drives the library surface the
criteria exercise. That false start is itself the map: the pinned
surface is verbs, handlers, and the kernel API; flags and the `--json`
schema are unpinned seams, now on the register.

## Reading

The deepest result is the direction of the asymmetry. The descendants
are not degraded copies that leak where the parent is sound — on every
seam this run touched, the descendants sit INSIDE the criteria and the
parent carries the one behavior the criteria do not cover. Blind
regrowth under a gate is a purifier: what comes out is the contract,
the whole contract, and nothing else. The ratchet's next clicks are
therefore decisions about the contract (author at format 3; pin the
sandbox signal), not repairs to the descendants.
