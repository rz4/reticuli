# The seam blocks pin private names, which is not an acceptance boundary

2026-10-29. Staged for a keyholder ruling. **Not a contraction and not a
hardening — a proposed WIDENING**, which is why it is only staged. It would
move the root and it changes what the class admits, so it is exactly the
kind of decision the signature exists for. Raised by an outside reading of
the repository; no reconstruction forced it.

## The observation

Sixteen criteria files carry a machine-pasted `_seam()` block. The comment
above each one says *"Paste into the check; call `_seam()` from its
battery()/main."* A representative block, from
`criteria/run_check.py`:

```python
_SEAM__kernel_run_KINDS = {'_BWRAP_OK': 'NoneType'}
_SEAM__kernel_run_CALLABLES = ('_bwrap_usable', '_env_cache_dir', '_have',
    '_in_band', '_independence_line', '_kill_tree', '_ledger_path',
    '_quote_sb', '_run', '_sandbox_argv', '_scrub_env', '_tool_version',
    '_version_ok', '_version_tuple', 'cost', 'furnish', 'gate_timeout',
    'independence', 'ledger', 'preflight', 'run_gate', 'sandbox',
    'sandbox_backend')

def _seam() -> None:
    for _n in _SEAM__kernel_run_CALLABLES:
        assert callable(getattr(_m__kernel_run, _n, None)), \
            f'_kernel/run.py must export callable {_n}'
```

`criteria/crosscheck`-side blocks go further and pin private *values*
(`_INTERPRETERS`, `_OPERATORS`, `_SKIP_VALUE`) and a long list of private
helper names (`_docstring_spans`, `_draw_order`, `_edit`, `_label`,
`_machine`, `_mutant_order`, `_mutants`, `_named`, `_node_span`,
`_span_text`, `_splice`, `_structural_mutants`, `_token_mutants`).

These blocks are **pinned criteria**. A conforming independent kernel must
therefore reproduce *this repository's private naming*.

## Why that is the wrong kind of obligation

The whole design rests on one rule, stated as an iff in
`docs/design-rationale/format3.md`:

> A byte belongs to the identity of a claim if and only if changing that byte
> can change whether some realization is accepted.

A private helper's *name* cannot change whether a realization is accepted —
unless a criterion makes it so, which is what these blocks do. They are
self-fulfilling: the name matters because the check says it matters.
Guidance was removed from the root at format 3 and step order at format 4
on precisely this reasoning. A function name that no caller outside the
module can reach is the same category of fact.

It also contradicts the lesson the blind rebuilds actually taught, recorded
in `src/reticuli/_util.py`'s own docstring: the shared helpers live outside
`_kernel` privates *because* "the regrown kernel duly named them
differently or not at all." The project learned that private naming is not
transportable, wrote that down, and then pinned private naming.

And it has a visible cost in the implementation: `src/reticuli/kernel.py`
re-exports roughly seventy underscore-prefixed names from the eight kernel
modules for no reason other than to satisfy these blocks. A facade whose
shape is dictated by its test is the usual smell, one level up.

## What the blocks are really protecting

Steelmanning them, because they were not written for nothing. Two honest
jobs:

1. **A decomposition tripwire.** They fail loudly if a refactor quietly
   relocates a kernel responsibility — useful while the kernel was being
   split into eight modules.
2. **A cheap stand-in for behavioral coverage.** `_mutants`, `_splice` and
   friends are the mutation injector's internals; asserting they exist is a
   weak proxy for "the injector is still assembled from the pieces this
   suite expects."

Job 1 is real and is about *this* tree's maintenance, not about membership.
Job 2 is a proxy that should be replaced by the behavior it stands for — the
suite already measures mutation outcomes directly.

## The proposal

1. **Keep the public surface pinned.** `spec/kernel-api.md` is the contract
   and `kernel_check.py` is its enforceable form; every name in that table
   stays pinned, including `_hash_file`, which the spec lists deliberately.
2. **Drop the private-name and private-value assertions** from the sixteen
   `_seam()` blocks — the `_SEAM_*_CALLABLES` entries beginning with `_`,
   and the `_SEAM_*_VALUES` entries naming private constants.
3. **Replace job 1 with a layering assertion that is about structure rather
   than spelling**: the existing import-graph criteria already pin that a
   layer imports only layers below it. Strengthen those if the tripwire is
   wanted.
4. **Then delete the ~70 private re-exports** from `src/reticuli/kernel.py`,
   which exist only to satisfy (2).

Exception worth debating: `_REQ_OPS` and `_KEEP_ENV` are pinned *values*
with real semantics (the version-comparison operator set, and the exact
environment allowlist a gate may see). `_KEEP_ENV` in particular is already
pinned independently by `criteria/core_check.py` and
`criteria/obligations_check.py` as a *behavioral* obligation — a verdict
must ignore the granted environment — which is the right way to pin it. Keep
those; they are not naming, they are contract.

## Why this is a ruling and not a fix

Dropping a pin **widens** the equivalence class. Every widening is a
research decision with two consequences the project tracks deliberately:

- The `freedom-register.md` gains loci that are free again, and the honest
  entry for each is "free by recorded design", not "closed".
- It is an *adopted boundary change*, so by condition 7 the closure count
  resets — currently 0 of 3 at this root, so the marginal cost is low today.

It also cuts against the ratchet's usual direction, and the project's own
discipline says a widening needs as much evidence as a narrowing.

## The measurement (2026-10-29)

Run before staging this, so the proposal rests on a refusal rather than on
reasoning. No producer session was spent.

Take the shipped tree, copy it, and rename **one private helper
consistently** — `_quote_sb` → `_sb_quote` in the two files that mention it
(`_kernel/run.py` and the `kernel.py` facade). Nothing else changes. The
result is behaviorally identical by construction: the rename is closed over
every reference, and the kernel still selects the same backend and builds
the same seatbelt profile.

```
$ PYTHONPATH=src python3 -c "from reticuli._kernel import run; print(run.sandbox_wrap('/tmp')[0])"
seatbelt                                  # unchanged

$ python3 criteria/run_check.py
AssertionError: _kernel/run.py must export callable _quote_sb
```

**The criterion refuses a tree whose behavior is identical.** The refusal
names a private helper, and the only way for a producer to satisfy it is to
guess this repository's internal spelling — which a blind rebuild cannot do
and is not asked to do by any line of `spec/`.

That is the cost, measured: membership in the class currently depends on
private naming. The proposal now has the same footing as the pins in
`genome-map.md` — selected by a measurement — with the direction reversed.

Two things the measurement does **not** show, stated so the ruling is not
made on more than this: it does not show that any *real* reconstruction was
refused for this reason (none in the ledger was — the refusals recorded at
r26 and r33 were genuine behavioral defects), and it does not show that the
tripwire job (above) is worthless. It shows only that the pin can refuse a
conformant tree, which is what "narrows the class" means.
