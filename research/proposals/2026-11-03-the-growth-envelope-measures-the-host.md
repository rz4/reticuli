# The growth envelope measures the host, not the algorithm

> **LANDED 2026-11-03**, batched with the outside-review fixes so the
> ceremony was paid once. Root `b188d96b → 8e4e6372`; `exchange`
> `3b4125d6 → 55b77d5b`. Implemented as min-of-k (k=5) with an explicit
> resolution floor, below which the measurement is SKIPPED and said to be
> skipped rather than guessed. Validated against this document's own
> acceptance criterion: the envelope holds under deliberate eight-way CPU
> contention. Account:
> `research/provenance/revision-2026-11-03-the-outside-review-batch.md`.

2026-11-03. Staged, not landed. Fixing it edits a pinned criterion, so it
moves the root and costs a re-signature; the CI failures it causes are
intermittent and were not today's outage, so it is written up rather than
taken in the same breath.

## The criterion

`criteria/exchange_check.py`, the growth envelope (2026-10-10,
keyholder-signed). Two operations are bounded as growth rates by comparing a
16-layer chain against an 8-layer one:

```python
t0 = _time.perf_counter(); registry.pull(top8, pw8)
p8 = max(_time.perf_counter() - t0, 0.05)
t0 = _time.perf_counter(); registry.pull(top16, pw16)
p16 = _time.perf_counter() - t0
assert p16 / p8 <= 8.0, \
    f"pull grows, never unfolds: t16/t8 = {p16 / p8:.1f}"
```

The intent is sound and well argued in its own comment: same-host ratios
cancel machine speed and measure the algorithm, the observed band is ×2.0–3.5,
and ×8 is a deliberate ceiling laid on the axis where an exponential would
gate the recursion. Nothing is wrong with the *idea*.

## The defect

**The ratio is only meaningful when both measurements sit well above timing
noise, and they do not.** `pull` over an 8-layer chain of one-line claims is
a handful of filesystem copies — fast enough that the code carries a `max(…,
0.05)` floor, which is an admission that `p8` can be unmeasurably small. Once
`p8` is pinned at the 0.05 s floor, the assertion reduces to
`p16 <= 0.4 s`: an absolute wall-clock bound on a shared runner, wearing a
ratio's clothing. A contended macOS runner blows through it while the
algorithm is unchanged.

Observed failures, all macOS, all this family:

| when | assertion | value |
|---|---|---|
| PR #20 | `pull grows, never unfolds` | `t16/t8 = 9.1` |
| PR #24 | `pull grows, never unfolds` | `t16/t8 = 9.0` |

Both passed on re-run with no code change, which is the signature of a
measurement defect rather than a regression. And note the bound already
carries 2.3× headroom over the observed band — widening it further would not
help, because the quantity being measured is not the one the assertion names.

This is the session's recurring lesson pointed at a third surface: after the
criterion that only ran the author's configuration, and the criterion that
pinned the wrong answer outright, here is a criterion that pins a property of
the **host** while claiming to pin a property of the **claim**. A conforming
implementation on a busy machine is refused; the same implementation on an
idle one is admitted. That is not an equivalence class.

## The proposed fix

Keep the envelope — it guards something real — and make the measurement
answer the question it is asked:

1. **Get above the noise floor.** Repeat each operation until accumulated
   time is large enough to measure (or scale the chains until it is), and
   delete the `max(…, 0.05)` floor, which exists only to paper over the
   problem. If a floor is still needed, the measurement is still too small.
2. **Reject contention with min-of-k.** Take the *minimum* of k repetitions
   rather than a single sample. The minimum estimates the uncontended cost,
   which is the algorithmic quantity; a scheduler spike can only ever inflate
   a sample, never deflate one, so the minimum is the robust estimator here.
3. **Refuse rather than guess when the host will not cooperate.** If even
   the minimum of k is below the measurable threshold, report the gate as
   `environment` — untested on this host — never as a pass and never as a
   failure. That is the same three-valued discipline the verdict vocabulary
   already uses everywhere else, and it is the honest answer for a timing
   claim on a machine that cannot time.

### Acceptance

- The envelope passes on an idle host and on a deliberately loaded one
  (run it under competing CPU load and confirm it still reports the
  algorithmic ratio, not the contention).
- Removing the noise floor does not change the verdict on an idle host.
- An artificially unmeasurable case classifies as `environment`, not as a
  pass.
- A genuinely exponential `pull` — a seeded one-copy-per-path regression —
  is still caught.

## Cost

`criteria/exchange_check.py` is pinned, so this moves the root: reseal, cold
gate, recorded pair, room refresh, and a keyholder re-signature. Worth
batching with the next identity-bearing change. Until then the mitigation is
the one landed today — a `concurrency` group so pushes do not contend for
macOS runners — plus re-running the job, which has always cleared it.
