# The assembled rebuild: reticuli regrows cross-vendor, and the one seam its criteria do not pin

On 2026-09-21 the whole of reticuli was rebuilt from its criteria a second
time, now by a different vendor and off the metered API entirely, and the
result was assembled and audited against current reticuli. The tool regrows;
the assembled tool does not yet compose. This records both, and locates the
gap precisely.

## The un-metered producer

The earlier rebuilds drove the OpenAI API and stopped at a spend cap. This run
used a new producer, `src/reticuli/producers/codex.py` (committed at 30292ed),
which hands each room to the locally installed `codex` CLI instead of driving
an API tool loop. Codex authenticates from a signed-in plan, not a metered
key, so a rebuild draws on no API budget. The producer lives in the
deliberately unpinned `producers/` directory — substrate, not identity — so
adding it renamed nothing and moved no root. It keeps the shipped room
contract, and because a producer may be any command `rebuild` invokes, it was
invoked as a raw command, touching no pinned layer.

## Eighteen of nineteen layers regrow to their exact roots

Against the sealed nineteen-layer reuse base, codex regrew each layer's own
modules and every layer but one reached its exact pinned root:

    core recipe seal run  build attest crosscheck exchange authoring
    agents launcher measure cli-base cli-render cli-handlers cli-parser
    cli-verbs surface

all MATCH. The single holdout is `identity`, the byte-exact serialization
layer whose check pins golden preimage vectors. Two independent codex sessions
of about half an hour each finished without ever turning the gate green (no
usage-limit interruption in either). This reproduces, on a second vendor, the
gpt-5 finding that byte-exact serialization is the hard floor: it is the one
layer a single bounded agentic session does not reliably reconstruct. Every
other layer — including the comprehensive dispatch hub held to `surface_check`,
which the decomposition was built to make regrowable — came back to root.

One operational note: a full nineteen-layer sweep exhausts the plan's rolling
usage window, exactly as the API run exhausted its spend cap. Both meters bite;
the science is unaffected, the sweep simply spans two windows.

## The assembled tool does not compose — and that is the finding

Root-match per layer means same recipe, same inputs, same verdict. It does not
mean same code: the generated source is excluded from the root, and that is the
whole point — the equivalence class is meant to be wide. So each of the
eighteen regrown layers is genuinely different, and dramatically leaner, code:
`crosscheck` 797 lines to 195, `_cli/parser` 774 to 128, `heldout` 401 to 40,
`feedback` 222 to 7, `cli` 107 to 7. Each passes its own gate.

Stitching every layer's own regrown module into one package and importing it
fails immediately:

    dispatch -> kernel -> from ._kernel.core import _JAILED
    ImportError: cannot import name '_JAILED' from reticuli._kernel.core

The regrown `core.py` (55 lines, from 225) never defines `_JAILED`. Nothing
made it: `core_check` pins core's own gate-passing behavior — the hash
boundary, the path boundary, the atomic write — but not the private names other
layers import from it. Each regrown module invented the leanest internal API
its own check would accept, and the interface it exposes to its neighbors went
with the parts the check never looked at.

Scanning the real import graph and asking, for each regrown module, which of
the names its neighbors import are still defined, gives the size of the gap:
**159 unpinned seam symbols across twenty modules.** Ranked by module, the
worst are `_kernel/core.py` (41: `STORE`, `MANIFEST`, `RECIPE`, `_JAILED`,
`_KEEP_ENV`, `_now`, every `_ENV_*`, the cost and mutant constants),
`_kernel/crosscheck.py` (22: the mutation engine), `_kernel/run.py` (21:
`_run`, `sandbox`, `_scrub_env`, `furnish`), `_kernel/attest.py` (11: the
`_RECORD_*` field keys), and `_cli/report.py` (10: the per-verb renderers).
The full table is in the audit alongside this run.

## What it means for the criteria

The per-layer checks are vertical: each pins its layer's externally observable
behavior well enough that the layer regrows to its exact root. There is no
horizontal pinning of the interface each module exposes to its importers, so
the per-layer equivalence class is too wide to guarantee composition —
eighteen individually faithful layers assembled into a tool that cannot import.

This is the weak criterion the fidelity endgame set out to find, and it is now
exact: the cross-module API contract is unpinned. Driving a rebuild toward
functional fidelity means pinning that contract — either each layer's check
asserting the names, with their shapes, it exposes to importers, or one
dedicated seam check over the whole cross-module import surface. The 159
symbols are the worklist, ranked by module. Current reticuli already exports
every one of them, so each such tightening is a clean strengthening: the
current implementation stays green and only a leaner rebuild is now forced to
honor the seam.
