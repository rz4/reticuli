# Components

Responsibility map. One line per module; each links to its full source
with commentary in [the annotated implementation](book/index.md).

## Kernel (`reticuli._kernel`)

| Module | Responsibility |
|---|---|
| [`core`](book/reticuli/reticuli._kernel.core.md) | vocabularies and constants: verdict values, cost units and ladder, confinement levels, timeouts, the environment allowlist |
| [`recipe`](book/reticuli/reticuli._kernel.recipe.md) | parse and validate `reticuli.toml`: declared inputs, produce steps, gates |
| [`identity`](book/reticuli/reticuli._kernel.identity.md) | the root: hash the pinned material; the build digest over generated outputs |
| [`build`](book/reticuli/reticuli._kernel.build.md) | rooms: materialization, containment checks, rebuild, producer invocation, the ledger |
| [`run`](book/reticuli/reticuli._kernel.run.md) | execution: environment scrub, sandbox backends and tiers, timeouts, process-group kill, furnishing, cost totalling |
| [`attest`](book/reticuli/reticuli._kernel.attest.md) | the record format: validation, canonical bytes, record digest, signing |
| [`crosscheck`](book/reticuli/reticuli._kernel.crosscheck.md) | the three-machine test: leg comparison, cost band, mutation floor, three-valued verdict |
| [`seal`](book/reticuli/reticuli._kernel.seal.md) | seal a claim; write and read the manifest; verify |

## Surface (`reticuli`)

| Module | Responsibility |
|---|---|
| [`kernel`](book/reticuli/reticuli.kernel.md) | the public API over the kernel layers |
| [`pack`](book/reticuli/reticuli.pack.md) | create a claim from a project |
| [`record`](book/reticuli/reticuli.record.md) | record authoring |
| [`assess`](book/reticuli/reticuli.assess.md) | descriptive measurement of a claim's verification strength |
| [`heldout`](book/reticuli/reticuli.heldout.md) | held-out case evaluation for assess |
| [`reuse`](book/reticuli/reticuli.reuse.md) | the verdict cache and its fingerprint |
| [`registry`](book/reticuli/reticuli.registry.md), [`transfer`](book/reticuli/reticuli.transfer.md) | composed claims: dependencies, deep audit, export/import |
| [`authoring`](book/reticuli/reticuli.authoring.md), [`launcher`](book/reticuli/reticuli.launcher.md), [`hooks`](book/reticuli/reticuli.hooks.md) | workspace lifecycle |
| [`render`](book/reticuli/reticuli.render.md), [`reference`](book/reticuli/reticuli.reference.md) | human-readable rendering; the independent second identity implementation |
| [`_cli.*`](book/reticuli/reticuli._cli.md) | the `ret` command line, decomposed by role |
| [`producers.*`](book/reticuli/reticuli.producers.md) | bundled producer adapters (outside the equivalence class; substitutable) |

## Zeta (`zeta.lib`)

| Module | Responsibility |
|---|---|
| [`population`](book/zeta/zeta.lib.population.md) | member registries, root-relative; deployment and foreign populations |
| [`probe`](book/zeta/zeta.lib.probe.md) | drive one member in a subprocess; outcome and behavior key |
| [`split`](book/zeta/zeta.lib.split.md) | partition a population; disposition, lane, rank |
| [`reduce`](book/zeta/zeta.lib.reduce.md) | collapse probes to phenomena; witness selection |
| [`kinds`](book/zeta/zeta.lib.kinds.md) | the evidential ladder; transfer provenance requirements |
| [`mutants`](book/zeta/zeta.lib.mutants.md) | the broken-variant battery, each with a declared expectation |
| [`coverage`](book/zeta/zeta.lib.coverage.md) | judge mutants against the criteria; baseline and positive control |
| [`entry`](book/zeta/zeta.lib.entry.md) | package findings as self-contained, replayable claims |
| [`ledger`](book/zeta/zeta.lib.ledger.md) | the promotion record; unbroken root chain |
| [`selection`](book/zeta/zeta.lib.selection.md) | declared axes, Pareto frontier, no winner |
| [`sources.*`](book/zeta/zeta.lib.sources.md) | pressure generators: specification-derived, foreign-language, transferred silences |
| [`agents.*`](book/zeta/zeta.agents.md) | standing automation: the root watcher; agent-generated pressure |
