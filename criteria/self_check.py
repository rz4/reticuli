"""The repository seals itself: twenty layered claims, and the roots are a lockfile.

`scripts/selfclaim.py` builds the chain — each layer carrying everything below it
as component outputs, gated by that layer's own acceptance check. This check
runs that build and holds it to three claims:

  * every layer seals and verifies fresh;
  * the outermost layer's DEEP audit re-earns every layer beneath it, on the
    bytes the outer claim ships (not on each layer's own sealed copy);
  * the twenty roots are exactly the values pinned below.

The third is the interesting one. These roots are a hash over each layer's
recipe, its check's bytes, and its verdict's bytes — nothing about the host, the
interpreter, or the clock. So they are a lockfile over this repository's own
behavior: change a layer's implementation and they hold; change what a layer is
CHECKED for and they move, loudly, here.

THE BOOTSTRAP. The above proves the tool-under-test can pack, seal, and audit
claims of itself. `bootstrap()` closes the other half of the fixpoint: it drives
the tool-under-test THROUGH ITS OWN COMMAND LINE to rebuild a claim from a blind
room with a producer, and confirms the redo lands the target root and
crosschecks. Together they say the property that makes reticuli a quine — a
regrown reticuli can itself regrow — holding for whatever implementation is
present, because the subprocess runs `python3 -m reticuli` against src/, not this
process's imports. The producer here is deterministic (no model, no network), so
what is pinned is the harness, not any producer: the fixpoint is producer-free.

    python3 criteria/self_check.py        (from the repository root)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import selfclaim
from reticuli import kernel, registry

# The lockfile. Recompute with: python3 scripts/selfclaim.py
#
# 2026-10-06, THE MIGRATION (keyholder-signed; the chain-migration
# proposal): every layer is format 3 now, so producer guidance — including
# pack's own supplied-step wording — is outside every root below. Nineteen
# roots moved at once, deliberately and exactly once; core, format 3 since
# the basin revision, held. The r6 trial is the witness for why: a
# conforming foreign pack minted a chain-wide drift because format-1
# layers hashed its incidental wording as identity. From here, ANY
# conforming pack mints these roots.
PINNED = {
    # The kernel root moved once, deliberately: the v2.1 revision pinned seven
    # measured under-specifications, superseding d64cc301…. The five layers
    # above it moved when their
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
    #
    # 2026-09-16, the v2.2 revision: the kernel moved alone -- e650b524… --
    # when its suite pinned three more behaviors (no symlink or `..`
    # component in a declared path; records as crosscheck legs, one
    # predicate, two transports; a complete audit report on a claim whose
    # gate is itself a kernel, finding 12). The five layers above held:
    # their criteria did not change, and a layer's root covers its own
    # criterion, not its component's.
    #
    # 2026-09-17: exchange and surface moved, and only they. exchange_check
    # gained the blind export (the rebuilder's room: generated bytes stay
    # home, identity travels whole); surface_check gained `ret record` and
    # `export --blind` at the CLI. The four other layers' criteria did not
    # change, so their roots did not either -- two edits, two moved lines.
    #
    # 2026-09-17, later: surface moved alone when its suite pinned the
    # authoring on-ramp -- `pack --pytest` and `pack --environment` at the
    # grammar, with the refusal when neither gate form is given. The pytest
    # end-to-end lives in tests/, because criteria are stdlib-only and
    # pytest is not stdlib.
    #
    # 2026-09-17, the v2.3 revision: the kernel moved alone -- 82a81357… --
    # when its suite pinned the recipe's two names (finding 13: twins under
    # claim.toml and reticuli.toml share one root, and both names read),
    # the declared envelope with the THREE-VALUED VERDICT (accept, reject,
    # incomplete: a declared-but-unmeasured condition can never accept),
    # and the declared environment (the room furnished from hash-named
    # artifacts, with an offline hand-rolled wheel as the fixture).
    #
    # 2026-09-17, the command regrammar: surface moved alone -- first to
    # 40b94f38… when its suite pinned the fourteen-verb grammar (one concept
    # per verb, grouped help, older spellings as unlisted aliases), the
    # three output levels (terse default, -v, the {command, ok, status,
    # root, data} envelope), the 0/1/2 exit codes, two-level help, and the
    # folds: pack as the one authoring boundary (zero-flag over a declared
    # recipe), init carrying agent wiring, status as the one view, and
    # crosscheck materializing a real byte-copy M2 for a pair. Then to
    # dca69ba5… when a leaf-by-leaf walk of every verb x outcome pinned the
    # rest: the observed/declared/evidence triad in status (draft counts,
    # the --all table, dashes for untraced files), refusals with reasons
    # where raw tracebacks had hidden (a deleted traced file, a missing
    # import archive), invalid values exiting 2, status --all exiting by
    # what it demonstrated, and a closing glyph ban over every output the
    # battery sees. The five layers beneath kept their roots: the CLI is
    # contact, not depth.
    #
    # 2026-09-17, the maturity pass: surface moved alone -- 12749cb3… --
    # when its suite pinned the written style contract: the silence rule (a
    # passing check says nothing; makers print only the unknowable; views
    # speak), every diagnostic on stderr with class-first wording and hint
    # lines, a broken verify NAMING the moved files from the sealed parts
    # residue, color as ls does it (auto by tty, always/never overrides, the
    # label word returning wherever color is off), full hashes under -v,
    # --version, `-` as the standard stream for export/import/record, and
    # completion generated from the parser itself.
    #
    # 2026-09-17, maturity II: surface moved alone -- 3022eacf… -- when its
    # suite pinned the unknown-command answer (name the mistake, suggest the
    # near miss, exit 2), the one-voice refusal (`ret: <verb>: <fact>` from
    # every layer), the environment help topic, and the DECIDING set closing
    # the authoring triad: assess leaves root-stamped measurements as store
    # residue, and status --all renders them -- only while the root still
    # matches -- replacing its "strength unknown" line exactly then.
    #
    # 2026-09-18, the cost story: surface moved alone -- f7e65c08… -- when
    # its suite pinned the shipped producers answering to their names
    # (--producer openai[:model], the matched vendor key forwarded on the
    # user's naming, a missing SDK or credential refused in one line
    # BEFORE any money moves, a raw command passing through verbatim) and
    # the discovery bill: hooks remember the harness transcript as session
    # meta, and pack prices C1 from its usage entries over the session's
    # own window -- tokens always, usd only when the harness reported one,
    # because a price table would drift. Testimony, stamped as such.
    #
    # 2026-09-18, the import shape: surface moved alone -- 3d68a512… --
    # when its suite pinned coverage seeing the canonical Python flow
    # (`python3 check.py` where check.py says `from primes import ...`
    # covers primes.py through one level of import) and executed scripts
    # reading as deciders, never as gate outputs. Found live: the first
    # user to run the tutorial against a real Python project hit both in
    # one screenshot.
    #
    # 2026-09-18, the pure view: surface moved alone -- 99fc4d61… -- and
    # for the first time by SUBTRACTION: inspect.py left the layer.
    # status became the pure view (reads and reports, never executes, all
    # forms instant, every view ending with the confidence ladder's
    # `next`), audit inherited inspect's strict-jail posture as the CLI
    # default and now leaves a dated receipt as store residue, and the
    # receiving flow became `ret audit theirclaim` -- what it honestly
    # always was. A verb was retired because every distinction it held
    # found a truer home; the suite pins the ladder's rungs advancing,
    # the receipt's date, the strict default by capture, and the ledger.
    #
    # 2026-09-18, discovery leaves the band: surface moved alone --
    # 4d4de16c… -- after the FIRST REAL THREE-MACHINE PROOF (a user's
    # primes claim, gpt-5 as M3, one root, every gate earned, mutation
    # 0.93) was rejected on "cost band": the authoring session's 154k
    # discovery tokens had fed the band against a 7.4k redo. The gap is
    # the measurement, not a violation. Scope-stamped ledger events now
    # total under cost["discovery"] -- reported by status and the
    # crosscheck, excluded from the band's units, filtered from records
    # (whose cost vocabulary is closed by spec). The suite pins a
    # 154k-token session bill crosschecking clean beside a one-call redo.
    #
    # 2026-09-18, both drawers: surface moved alone -- 0bc4cc84… -- when
    # the first user to SIGN a claim read `signed none` back: status
    # counted only the attestation drawer, and the signing ceremony's
    # authorization lives in the other one. The suite now pins a claim
    # that is both attested and signed counting two statements.
    # 2026-09-18, the v2.4 revision: the kernel moved alone -- fac55f89… --
    # when its suite adopted format 3 (guidance leaves the root; request and
    # guidance strip identically; format-1 pairs keep different roots) and
    # made the cost band HARD ONLY WHEN DECLARED (an undeclared out-of-band
    # ratio is reported, never a verdict -- the counterexample the first real
    # three-machine proof supplied). The recipe migrated request->guidance
    # and declares format = 3. The proof stays open: re-earning it against
    # this stronger suite is the paid rebuild the keyholder gates.
    # 2026-09-19, the self-rebuild pass: surface moved alone -- bde24987… --
    # when its suite pinned two behaviors a gpt-5 rebuild showed a conforming
    # implementation is free to drop, because the surface gate never exercised
    # them: the --json REFUSAL envelope (ok:false on stdout so `| jq` never
    # chokes on the first "is this a claim?" refusal) and `run`'s exit-code
    # PASSTHROUGH (the child's code returned unchanged, so a red run cannot go
    # green). Both were mutation-proven against the prior suite; the rebuild
    # confirmed the minimality -- a producer writes only what the gate checks.
    # 2026-09-19, later: surface moved alone -- 1e865511… -- when the same pass
    # folded the three looser surface-schema items the audit had left as policy:
    # the per-verb --json `data` key sets (so a rebuild cannot rename `deciding`
    # or drop `discovery`), the envelope `status` vocabulary per verb (fresh,
    # earned, measured, a claim-state word), and the exit-2 seam (an invalid
    # invocation stays a stderr line with no envelope, distinct from the exit-1
    # refusal that does speak one). The machine surface below the envelope is
    # now pinned, not just its five top-level fields.
    # 2026-09-19, the incremental build: exchange moved alone -- eef4a89c… --
    # when exchange_check pinned that a plain (non-recursive) rebuild of a
    # composed claim REUSES its sealed component and regrows only the top layer,
    # rather than asking the producer to reproduce a layer already sealed. This
    # is the layered build for large software; the prior coverage let a
    # cooperative producer mask a rebuild that silently regenerated the stack.
    # 2026-09-19, the kernel decomposition (pilot): the kernel split into TWO
    # sub-claims -- kernel-core (the identity machinery: constants, the path and
    # bytes boundaries, recipe, the canonical root and build-digest, seal/verify;
    # judged by kernel_inner_check.py) and the outer kernel (execution, audit,
    # rebuild, records, crosscheck; kernel.py, a facade re-exporting the core).
    # Every layer's root moved because each recipe now enumerates the _kernel
    # modules it carries. This makes the kernel itself rebuildable as a chain,
    # the first cut toward decomposing the whole tool for large-scale rebuild.
    # 2026-09-19, the 8-way split (stage 1): the kernel-core sub-claim itself
    # subdivided into FOUR layers on the clean inner DAG -- core (the boundaries
    # and vocabulary), recipe, identity (the canonical serialization), seal --
    # each a small module with its own suite (core/recipe/identity/seal_check).
    # Smaller layers regrow more cheaply, which is the economy the layered build
    # is for. Every root moved again (each recipe enumerates the split modules).
    # examples/kernel was retired during the churn; it will be re-sealed as the
    # settled core once the outer half (run/build/attest/crosscheck) lands.
    # 2026-09-19, the 8-way split (stage 2, complete): the outer kernel split
    # into run (confined gate execution + ledger), build (materialize, audit,
    # rebuild, the signed phase), attest (the record format), and crosscheck
    # (the three-machine test, vacuity, mutation). kernel.py is now a pure
    # facade over all eight _kernel modules. The kernel is a chain of EIGHT
    # sub-claims, each small enough for a producer to regrow; the repository is
    # thirteen layers. The whole point: the reuse primitive regrows only the
    # small changed layer, which is the economy the layered build is for.
    # 2026-09-21, the seam contract (stage 1: core): the 2026-09-21 assembled
    # rebuild regrew 18 of 19 layers to their exact roots but the stitched tool
    # would not import -- a regrown core dropped the private names other layers
    # import from it (`from ._kernel.core import _JAILED`). core_check now pins
    # core's EXPORT contract, the 41 names the kernel above it imports (value
    # for the protocol/on-disk/env constants, kind for the tuning ones,
    # callable for the helpers). Only core's root moves; each upper layer commits
    # to its own check, unchanged. First of the 159-symbol seam worklist.
    # 2026-10-03, the surface-silence map's first pins: core_check pins the
    # KINDS vocabulary's CONTENT (five conforming implementations had five
    # values while only the type was pinned). core moves with its suite.
    "core":      "685224c92b1f1f2c5d26ce506f43857c6d32cf4213ba04fa6d9e81bcf951c2de",
    # 2026-09-21, the seam contract (stage 2: the kernel). Each of these checks
    # now pins its layer's export contract -- the names the layers above import
    # from it (value for host-independent constants, kind for host/tuning ones,
    # callable for helpers). recipe, identity, seal, run, build, attest, and
    # crosscheck each move only their own root; core moved in stage 1. Part of
    # the 159-symbol seam worklist the assembled rebuild ranked by module.
    "recipe":    "257d17a9be10fa45e97b03e1f8677964cad4555e2f6e6750a3dbb9391a38f6f8",
    "identity":  "3c38ee48156013bb6a95b8197665a31fe5fd267ec51447237e8c35e75fe2abd6",
    "seal":      "107c7948d6b5bbb46870bf50c0dbee0dece6dc01a149dce661d96493844411f1",
    # 2026-10-04, the final bundle: run_check pins the declared timeout's
    # direction (the declaration IS the ceiling, raisable past any
    # implementation default). run moves with its suite.
    # 2026-10-05, the sandbox-closure bundle (keyholder-signed): the jail's
    # FLOOR is pinned — inside the gate quarantine a gate may sink to /dev,
    # spawn a subprocess, and read the host, while the network and foreign
    # writes stay denied. The r4 regrown kernel's deny-default jail blocked
    # /dev/null and refused true criteria as `failed`.
    # 2026-10-06, the recipe-first bundle: the floor gains its uname plank —
    # the first jail grown under the floor pin passed all five probes and
    # still denied os.uname(), refusing true criteria in fourteen seconds.
    "run":       "b6e42c9b1795adb67215a3bb7aa5b60223e76d4dd2aeae4221cfd43b0ea7ac47",
    # 2026-10-05, the authoring-and-sandbox bundle (keyholder-signed): the
    # sandbox signal is pinned — an audit's gate rows and a rebuild's result
    # must NAME their jail (seatbelt/bubblewrap/inherited/none; an absent key
    # is nonconforming). The first cross-judging run found both regrown
    # kernels earning verdicts while saying nothing about confinement.
    # 2026-10-05, the sandbox-closure bundle (keyholder-signed): the producer
    # runs FREE — scrubbed, never kernel-jailed; a socket-binding producer
    # must succeed where the same probe as a gate is refused. The r4 regrown
    # kernel jailed its producers and could not drive a generation-2 rebuild.
    # (The pin's own first draft asserted this inside an inherited jail,
    # where the freedom is not the kernel's to grant — the chain's nesting
    # refused it; the probe now yields under `inherited`.)
    "build":     "297d7e60dea15f17b257fae97084d5c7609387f64f446381a5a76063577dbc2c",
    "attest":    "8f6ce426618f3a05789dc4df0fdaccc801b751a4812ae93bf1f733d61b409286",
    # 2026-09-28, the room-matches-the-name revision: crosscheck and exchange
    # moved, and only they. The kernel suite pinned three behaviors from the
    # cross-family reading (a gate cannot read guidance the root excludes; a
    # rebuild's producer cannot touch pinned bytes; declared obligations
    # cross the record transport, with a version-1 M1 incomplete), and
    # exchange_check pinned record format 2 (the required `claim` member
    # carrying tolerance/envelope/mutation_floor). Two criteria changed, two
    # moved lines.
    # 2026-09-29, clicks A and J from the succession's gate-closure finding.
    # kernel_check (click J) pins that a producer which earns the gate in its
    # room lands despite the residue it leaves — a regrown kernel refused
    # every real producer, reading gate output and bytecode caches as
    # rewritten pinned bytes. crosscheck moves with its suite.
    # 2026-10-03, click F lands: kernel_check pins the three names the new
    # closure criterion caught on its first run (MANIFEST, RECIPE, ledger —
    # consumed by pinned criteria, exercised until now by nothing but the
    # model prior). crosscheck moves with its suite once more.
    # 2026-10-04, the final bundle: kernel_check pins the room's environment
    # boundary both ways (nothing unhanded arrives; producer_env always
    # does; blind sees no hint, guided sees the recipe's words), on a
    # fixture with a nested check. crosscheck moves with its suite.
    # 2026-10-06, the recipe-first bundle: the sandbox signal survives the
    # public surface — kernel.rebuild and kernel.audit carry the quarantine
    # key at the layer callers reach, however the inside is arranged (the
    # r5 wrapper lawfully reimplemented rebuild and dropped it).
    "crosscheck": "2d393b11a88e92f46fcf18b39b7c0e63cbabe630c8a6630e7f319ad25761bf14",
    # 2026-09-21, the seam contract (stage 3: mid + CLI). exchange (_util's
    # public helpers + attest's ATTEST) and authoring (render's short/table/tree/
    # paint/…) pin the names their consumers import; the CLI checks below do the
    # same for the _cli modules. Completes the 159-symbol seam worklist.
    # 2026-09-22, seam contract (stage 4: full public surface for the two
    # providers whose facade-reached exports the import-graph seam missed). A
    # regrown consumer imported STORE/trace_append/ledger_add straight from
    # _util and TRACE from authoring; current code reaches these via the kernel
    # facade, so stage 3 had not pinned them. exchange and authoring now pin
    # their whole public surface, closing the assembled tree's last 4 breaks.
    # 2026-09-28: record format 2 -- see the note above the crosscheck root.
    # 2026-10-05, the sandbox-closure bundle (keyholder-signed): the deep
    # audit's TRANSITIVE CLOSURE is pinned on a three-claim chain — every
    # ancestor judged, and a broken grandparent fails the composed verdict.
    # The r4 regrown audit_deep recursed one level and reported a deep chain
    # healthy after checking its first link.
    "exchange":  "910dace936dd785644f55471a76c825102d5a5d6197786ebbf8d64c2614013c2",
    # 2026-09-29, click A: authoring_check pins the pack surface the pinned
    # scripts/selfclaim.py consumes -- the keyword spelling, and the
    # component/envelope/claim_format features -- which two independently
    # regrown packs satisfied every prior case yet could not run. authoring
    # moves with its suite.
    # 2026-09-30, click A follow-up: the component fixture's path literal was
    # a bare relative path in a pinned file, which the self-containment
    # scanner rightly flags as dangling in a rebuild room; built at runtime
    # instead. authoring moves once more, the only layer affected.
    # 2026-10-03, the surface-silence map's first pins: authoring_check
    # pins pack's residual keyword surface (mutation_floor, requires, by,
    # inputs_manifest, environment's refusal) — the named next seam after
    # click A's convergence. authoring moves with its suite.
    # 2026-10-05, the authoring-and-sandbox bundle (keyholder-signed): a
    # fresh claim is born at format 3 (guidance is not identity — three
    # kernels packed one claim and minted two names, the parent's default
    # guidance line being the divergent byte), guidance edits are
    # root-neutral, and claim_format=1 writes the keyless era-1 recipe so
    # every pinned era-1 root re-mints byte-identically.
    # …and the pin took three drafts, each refused by a different standing
    # instrument: the closure criterion ate the first (it consumed kernel
    # helpers no check exercises); the self-contained scanner ate the second
    # (a nested path literal inside the guidance hint, caught on CI across
    # six platforms and in the r4 judge the same hour). The landed test
    # rewrites the raw recipe textually, stands only on exercised surface,
    # and quotes only a flat filename.
    # 2026-10-06, the recipe-first bundle: the warm ritual is recipe-first —
    # a fixture whose check writes its verdict only inside a claim (the
    # repository checks' own guard) must seal, so a pack that gates before
    # writing the recipe cannot conform. The r5 pack starved the whole
    # chain's verdicts this way and the identity gate refused the tree.
    "authoring": "075f581a0aff1066f9d8ad5f959b252a1ba50e7aad5951d7e7c8d6770fbf6abf",
    "agents":    "9f2bf630e38e455766f5f86ea785c1ba3f8211cd32913057a32ca530b59b7fbf",
    "launcher":  "0503a7a50567c42066f6a5477c02be9010ebbf3111475a20af319aa4b607a2df",
    # 2026-09-20, surface decomposition (module split): cli.py (2574 lines, the
    # kernel monolith's twin) split into a src/reticuli/_cli/ subpackage of
    # seven role modules, cli.py a pure facade.
    # 2026-09-20, surface decomposition (sub-claims): the surface layer itself
    # split into SIX sub-claims so each piece regrows independently -- measure
    # (assess+heldout+reuse), cli-base (output+views), cli-render (report+
    # statusview), cli-handlers, cli-parser, and surface (dispatch+facade+
    # __main__). Each _cli role module and the measure modules now have their
    # own focused suite (base/render/handlers/parser/measure_check); surface_check
    # stays the comprehensive top gate for the dispatch layer. The repository is
    # now EIGHTEEN layers; every oversized module is a small, regrowable claim.
    # 2026-10-04, the final bundle: measure_check pins the verdict cache's
    # honesty (reused never earned; the trust it leaned on named; nothing
    # cached means everything redone). measure moves with its suite.
    "measure":    "1706c7cfd0e8b2d01a0b015d5cdc24d5de73eb7581e629e578cde7a02f7ffaa8",
    "cli-base":   "55bc0c9060bb52eff0d620178555da8fa8c277132224366ebe9ad8b0f2e78219",
    "cli-render": "9e4db31923a15a867ee4a5b0bd2a8c43a0ba229f644df07a06e21a8554d85641",
    "cli-handlers": "d52a79360554ecf5ed1ba953dd33324a4ba0a8bc03f6ceeb40556592873c61c7",
    # 2026-09-20, dispatch decomposition: cli.py's dispatch split so the last
    # holdout (the verb-switch hub, judged by the comprehensive surface_check)
    # could regrow. The verb handlers moved to _cli/verbs.py (the cli-verbs
    # sub-claim, judged by verbs_check); main() is now a thin routing TABLE plus
    # the shared refusal/signal boundary. surface (dispatch + facade + __main__)
    # is thin and reuses the sealed handlers below. Nineteen layers now.
    # 2026-09-22, verb retirement: seal/hooks/tree/claims retired (folded into
    # pack --accept / init / status --tree / status --claims), hook hidden as
    # plumbing. 22 verbs -> 18.
    # 2026-09-22, sign-family fold: attest retired -> record --key --as (in-claim
    # attestation) / record --check; sign (human ceremony) unchanged. attest.py
    # module untouched, so exchange holds; only the three CLI-surface checks moved
    # (parser_check/verbs_check/surface_check). 18 verbs -> 17.
    "cli-parser": "3b2d1c65e4b1376f4eaccaec1c34723f3c78c6ac0acbb1edc3dc85115641f63c",
    "cli-verbs":  "310e84ebff296a93f4a947735f422e36ceb4ebd3da51b3909aee2c452cc36e76",
    # 2026-10-04, the final bundle: surface_check pins the verdict
    # vocabulary (a failed gate is `failed`; `broken` is identity damage,
    # the other verb's word). surface moves with its suite.
    "surface":    "6e2829ee9000b1455b3db2f4d8bda820ac07fb317810474d91aeb9fd8ef3c4ae",
    # 2026-10-04, the final bundle: the twentieth layer — reference.py,
    # judged by vectors_check in a repository-shaped room; the chain now
    # covers the repository claim's whole generated surface.
    # 2026-10-04, later: CI — the first other machine this layer met —
    # caught its root differing between macOS and Linux: the vectors were
    # enumerated in os.walk's readdir order, which is the host's, and the
    # input list is inside the root. The builder now sorts the full
    # paths; this value is the order-independent one, and a lockfile that
    # holds across machines is the lockfile doing what it says.
    # 2026-10-04, hours after: the gate caught the next defect in the same
    # layer — the first design staged every module as a pinned INPUT, so a
    # one-line edit to an implementation file moved this root, violating
    # the sentence at the top of this lockfile. The modules are now
    # GENERATED steps, outside the root, exactly as every other layer
    # holds them; this value covers only vectors_check, the conformance
    # vectors, and the recipe — and holds when src/ changes.
    "reference":  "2fafdd87092aa1b8f75c1a2579ad4daa913d5b0ca3381a4dcb214fa42ab3e186",
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
            assert roots["core"] == kernel.read_manifest(sealed)["root"], \
                "the chain's base layer IS the sealed core claim"

        # A deep audit judges each layer's check against the bytes the OUTER
        # claim ships, so an inner layer cannot pass on its own sealed copy
        # while shipping something else.
        deep = registry.audit_deep(os.path.join(work, "chain", "surface"))
        assert deep["ok"], f"the whole chain re-earns: {deep.get('verdict')}"
        # surface is the outermost CHAINED layer; reference (2026-10-04) is
        # the standalone twentieth claim — it pins the modules it judges as
        # inputs rather than carrying them as a component, so it stands
        # beside the chain, not on top of it, and is verified above like
        # every layer rather than re-earned through surface's deep audit.
        chained = [name for name, *_ in selfclaim.LAYERS if name != "reference"]
        assert len(deep["layers"]) == len(chained) - 1, \
            "every chained layer beneath surface is judged"
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


def _ret(work, *argv):
    """Drive the tool-under-test through its own entrypoint, as a stranger
    would: `python3 -m reticuli …` with src/ on the path, never this
    process's imports. That is what makes this a bootstrap and not a
    re-test of already-imported functions."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "reticuli", *argv],
                          capture_output=True, text=True, cwd=work, env=env,
                          check=False)


def bootstrap() -> None:
    """The fixpoint's second half: a regrown reticuli can itself regrow.

    Seal a small claim, strip it to a blind room, and drive the
    tool-under-test's OWN command line to rebuild it from that room with a
    deterministic producer. The redo must land the sealed root and the
    crosscheck must not reject. This exercises the assembled rebuild
    pathway — CLI, producer invocation, cold gate, seal, crosscheck — as a
    tool, so a rebuilt reticuli that regrows claims of itself (battery
    above) is also shown able to REBUILD one through its surface. The
    producer is a fixed script: the harness is what is pinned, not it.
    """
    work = tempfile.mkdtemp(prefix="bootstrap-")
    try:
        m1 = os.path.join(work, "claim")
        os.makedirs(m1)
        with open(os.path.join(m1, "reticuli.toml"), "w", encoding="utf-8") as f:
            f.write('[claim]\nname = "seed"\ninputs = ["check.py"]\n\n'
                    '[[step]]\nkind = "produce"\noutput = "impl.txt"\n'
                    'class = "generated"\nguidance = "write the greeting"\n\n'
                    '[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\n'
                    'run = "grep -qx hello impl.txt && printf v > V"\n')
        with open(os.path.join(m1, "check.py"), "w", encoding="utf-8") as f:
            f.write("# the claim: impl.txt must say hello\n")
        with open(os.path.join(m1, "impl.txt"), "w", encoding="utf-8") as f:
            f.write("hello\n")
        subprocess.run("grep -qx hello impl.txt && printf v > V",
                       shell=True, cwd=m1, check=True)

        sealed = _ret(work, "pack", m1)   # the tool seals its own claim...
        assert sealed.returncode == 0, f"the tool seals the seed claim: {sealed.stderr[-300:]}"
        target = kernel.read_manifest(m1)["root"]

        # ...exports a blind room (no implementation)...
        room = os.path.join(work, "room")
        exp = _ret(work, "export", m1, "-o", os.path.join(work, "seed.tar"), "--blind")
        assert exp.returncode == 0, f"the tool exports a blind room: {exp.stderr[-300:]}"
        imp = _ret(work, "import", os.path.join(work, "seed.tar"), room)
        assert imp.returncode == 0, f"the room imports and verifies: {imp.stderr[-300:]}"
        assert not os.path.exists(os.path.join(room, "impl.txt")), \
            "the room withholds the implementation"

        # ...and REBUILDS it from the room with a deterministic producer,
        # through its own CLI. The redo must land the same root.
        m3 = os.path.join(work, "m3")
        reb = _ret(work, "rebuild", room, "--producer",
                   "printf 'hello\\n' > impl.txt", "-o", m3)
        assert reb.returncode == 0, f"the tool rebuilds from the room: {reb.stderr[-300:]}"
        v = _ret(work, "verify", m3, "--json")
        assert v.returncode == 0 and json.loads(v.stdout)["data"]["root"] == target, \
            "the regrown claim lands the sealed root — the fixpoint holds"

        # the tool crosschecks its own M1 against the redo it grew: not reject
        xc = _ret(work, "crosscheck", m1, m3, "--json")
        verdict = json.loads(xc.stdout)["status"]
        assert verdict in ("accept", "incomplete"), \
            f"a rebuilt claim crosschecks (accept or incomplete, not reject): {verdict}"
        print(f"bootstrap-ok (the tool rebuilt a claim to its own root via its CLI; "
              f"verdict={verdict})")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    battery()
    bootstrap()
