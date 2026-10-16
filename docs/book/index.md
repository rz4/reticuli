# The implementation, annotated

Every module of the primary claim and of the exploratory instrument, presented in full: complete source in reading order, with the explanatory material the code already carries — module introductions, field-level notes, rationale recorded at the point of decision — set alongside the code it concerns.

These pages were generated against root `3302eb8a8f7e` and are regenerated with the implementation (`python3 docs/weave.py`); they are a rendering of the current bytes, not a document maintained about them.

Intentionally not rendered: the pinned inputs. The acceptance criteria and specifications of both systems (`criteria/`, `spec/`, and zeta's own) are the identity itself and should be read directly from the repository; likewise the queue, each of whose entries is a sealed, independently verifiable claim.

## The primary claim: kernel and surface (src/reticuli)

- [`reticuli`](reticuli/reticuli.md) — Reticuli — claims that travel.
- [`reticuli.__main__`](reticuli/reticuli.__main__.md) — (no docstring)
- [`reticuli._cli`](reticuli/reticuli._cli.md) — The command line, decomposed into role layers (output..dispatch).
- [`reticuli._cli.dispatch`](reticuli/reticuli._cli.dispatch.md) — ret command line — the dispatch layer: the thin routing table and the shared refusal/signal boundary. The verb handlers live in _cli/verbs.py; this looks one up and calls it, and turns a raised ClaimError into the --json refusal envelope or a stderr line.
- [`reticuli._cli.handlers`](reticuli/reticuli._cli.handlers.md) — ret command line — the handlers layer: session setup, the traced run, producer preflight, the version line.
- [`reticuli._cli.output`](reticuli/reticuli._cli.output.md) — ret command line — the output layer: the output contract — silence, -v, the --json envelope, errors, progress.
- [`reticuli._cli.parser`](reticuli/reticuli._cli.parser.md) — ret command line — the parser layer: the argv grammar, the verb map, man-page help, and completion.
- [`reticuli._cli.report`](reticuli/reticuli._cli.report.md) — ret command line — the report layer: the terse and -v renderers for the action verbs.
- [`reticuli._cli.statusview`](reticuli/reticuli._cli.statusview.md) — ret command line — the statusview layer: the status / draft / tree / claims render family.
- [`reticuli._cli.verbs`](reticuli/reticuli._cli.verbs.md) — ret command line — the verbs layer: the verb handlers and the composite
- [`reticuli._cli.views`](reticuli/reticuli._cli.views.md) — ret command line — the views layer: read recorded claim state into plain dicts; verdict words; the next ladder.
- [`reticuli._kernel`](reticuli/reticuli._kernel.md) — The kernel, decomposed into layered sub-claims (pilot: inner + outer).
- [`reticuli._kernel.attest`](reticuli/reticuli._kernel.attest.md) — The kernel's attest layer: the record format — the one interchange file third parties may parse.
- [`reticuli._kernel.build`](reticuli/reticuli._kernel.build.md) — The kernel's build layer: materialize a blind room, produce into it, re-earn every verdict, and the signed phase.
- [`reticuli._kernel.core`](reticuli/reticuli._kernel.core.md) — The kernel's core layer: constants, the path and bytes boundaries, atomic IO, the refusal vocabulary.
- [`reticuli._kernel.crosscheck`](reticuli/reticuli._kernel.crosscheck.md) — The kernel's crosscheck layer: the three-machine test, the vacuity boundary, and mutation.
- [`reticuli._kernel.identity`](reticuli/reticuli._kernel.identity.md) — The kernel's identity layer: the canonical root and build-digest serialization.
- [`reticuli._kernel.recipe`](reticuli/reticuli._kernel.recipe.md) — The kernel's recipe layer: parse and validate an untrusted recipe.
- [`reticuli._kernel.run`](reticuli/reticuli._kernel.run.md) — The kernel's run layer: confined, timed, scrubbed gate execution, furnishing, and the cost ledger.
- [`reticuli._kernel.seal`](reticuli/reticuli._kernel.seal.md) — The kernel's seal layer: freeze identity onto the manifest, and verify the bytes still hash to it.
- [`reticuli._util`](reticuli/reticuli._util.md) — Small helpers the layers above the kernel share.
- [`reticuli.assess`](reticuli/reticuli.assess.md) — Assess: how much verification does a claim actually carry?
- [`reticuli.attest`](reticuli/reticuli.attest.md) — Attestation: a build that speaks for itself to others.
- [`reticuli.authoring`](reticuli/reticuli.authoring.md) — Authoring: propose a claim from a session's trace, then certify it cold.
- [`reticuli.cli`](reticuli/reticuli.cli.md) — ret — the command line. Fourteen verbs, one concept each:
- [`reticuli.corpus`](reticuli/reticuli.corpus.md) — The reference corpus: assess measurements, accumulated so one claim can be
- [`reticuli.feedback`](reticuli/reticuli.feedback.md) — The feedback loop: in a draft session, what's observed, what would be
- [`reticuli.heldout`](reticuli/reticuli.heldout.md) — Held-out evaluation: do the tests generalise, or do they only enumerate?
- [`reticuli.hooks`](reticuli/reticuli.hooks.md) — The agent handshake: a coding agent's hook events become the session trace.
- [`reticuli.kernel`](reticuli/reticuli.kernel.md) — The kernel layer: a claim's identity, its seal, and the verdicts it earns.
- [`reticuli.launcher`](reticuli/reticuli.launcher.md) — The launcher: run software that exists only latently in a claim.
- [`reticuli.pack`](reticuli/reticuli.pack.md) — Pack a project into a self-claim.
- [`reticuli.producers`](reticuli/reticuli.producers.md) — Producers: programs that regenerate a claim's generated outputs.
- [`reticuli.producers.anthropic`](reticuli/reticuli.producers.anthropic.md) — An agentic Anthropic producer for v2 claims — the other cross-vendor rebuilder.
- [`reticuli.producers.claude`](reticuli/reticuli.producers.claude.md) — A local Claude-Code producer for v2 claims — a second, un-metered family.
- [`reticuli.producers.codex`](reticuli/reticuli.producers.codex.md) — A local Codex-CLI producer for v2 claims — the un-metered rebuilder.
- [`reticuli.producers.openai`](reticuli/reticuli.producers.openai.md) — An agentic OpenAI producer for v2 claims — the cross-vendor rebuilder.
- [`reticuli.record`](reticuli/reticuli.record.md) — Records, the authoring side: emit, write, and sign one machine's results.
- [`reticuli.reference`](reticuli/reticuli.reference.md) — Reference sealer: a second, independent implementation of spec/identity.md.
- [`reticuli.registry`](reticuli/reticuli.registry.md) — Composition — claims become components.
- [`reticuli.render`](reticuli/reticuli.render.md) — The presentation layer, under one written contract: docs/cli-style.md.
- [`reticuli.reuse`](reticuli/reticuli.reuse.md) — Skipping work already done here, without ever trusting a stored verdict.
- [`reticuli.transfer`](reticuli/reticuli.transfer.md) — Portability: pack a claim into a deterministic tar, and unpack it back.

## Zeta: the exploratory instrument (zeta)

- [`zeta`](zeta/zeta.md) — Zeta -- reticuli's binary companion. Bound by a signature, nothing else.
- [`zeta.agents`](zeta/zeta.agents.md) — Agents: zeta's outer shell, standing to zeta as zeta stands to reticuli.
- [`zeta.agents.__main__`](zeta/zeta.agents.__main__.md) — Run the root watcher.
- [`zeta.agents.jq_target`](zeta/zeta.agents.jq_target.md) — The pilot's second target: the jq language, three foreign implementations.
- [`zeta.agents.pilot`](zeta/zeta.agents.pilot.md) — The two-agent pilot: a walker proposes, a verifier replays, numbers out.
- [`zeta.agents.pressure`](zeta/zeta.agents.pressure.md) — Agentic pressure, the pilot: can a model-driven walker find real silence?
- [`zeta.agents.reconcile`](zeta/zeta.agents.reconcile.md) — What the root watcher knows and does, as plain functions.
- [`zeta.agents.watcher`](zeta/zeta.agents.watcher.md) — The root watcher as an academy agent: a loop around reconcile.cycle.
- [`zeta.cli`](zeta/zeta.cli.md) — zeta -- put pressure on the class, queue what it finds, sign nothing.
- [`zeta.gate`](zeta/zeta.gate.md) — Zeta's own gate: every criterion, run against the library it ships.
- [`zeta.lib`](zeta/zeta.lib.md) — Zeta: the environment half of the pair.
- [`zeta.lib.coverage`](zeta/zeta.lib.coverage.md) — Which mutants the criteria already kill, and therefore which pressure is new.
- [`zeta.lib.entry`](zeta/zeta.lib.entry.md) — Mint a queue entry as its own claim, so it arrives already re-earned.
- [`zeta.lib.kinds`](zeta/zeta.lib.kinds.md) — How much a finding establishes, on a four-rung ladder.
- [`zeta.lib.ledger`](zeta/zeta.lib.ledger.md) — The promotion ledger: the chain from environmental pressure to identity.
- [`zeta.lib.mutants`](zeta/zeta.lib.mutants.md) — Deliberately broken members, used as controls so the ranker can rank.
- [`zeta.lib.population`](zeta/zeta.lib.population.md) — The standing population, keyed by the root each member earned against.
- [`zeta.lib.probe`](zeta/zeta.lib.probe.md) — Drive one population member in a subprocess and record what it did.
- [`zeta.lib.reduce`](zeta/zeta.lib.reduce.md) — Collapse many probes onto the phenomena they witness, and keep the simplest.
- [`zeta.lib.selection`](zeta/zeta.lib.selection.md) — Selection: find a better member, without touching the boundary.
- [`zeta.lib.sources`](zeta/zeta.lib.sources.md) — Pressure sources. Each yields pressures; none decides anything.
- [`zeta.lib.sources.jq_surface`](zeta/zeta.lib.sources.jq_surface.md) — Pressure on the jq language, put to three independent implementations.
- [`zeta.lib.sources.record_surface`](zeta/zeta.lib.sources.record_surface.md) — Pressure derived from the record specification's own validation sentence.
- [`zeta.lib.sources.transfer`](zeta/zeta.lib.sources.transfer.md) — Silences carried across from a foreign population, by shape and not content.
- [`zeta.lib.split`](zeta/zeta.lib.split.md) — Run one pressure over a population and classify what it found.
