# The silence map

*Research tooling — not normative, not pinned.*

Independent blind reconstructions implement exactly what the checks
exercise and nothing more (the succession's finding) — so the places where
N gate-passing implementations **disagree** are a direct measurement of the
boundary's silence. This instrument takes that measurement: a generated
probe battery runs over every implementation of a claim, and the divergent
probes are clustered by *partition* (who splits from whom) and *delta kind*
(what kind of difference: value-type, key-case, error-vs-accept, key-set,
…). Each cluster is one unpinned decision, lit up by the model prior
itself. The ratchet, made active: sample the class and read the map,
instead of waiting for a consumer to break.

    python3 silence.py --subject kvparse      # stage-2 C_0 impls
    python3 silence.py --subject kvparse-c1   # post-ratchet C_1 impls
    python3 silence.py --subject confparse    # ladder blind controls

## Validated against known ground truth (2026-10-03)

- **kvparse (C_0)**: rediscovers the coercion silence of stage 2 from
  generated probes alone, correctly shows *no* duplicate-keys silence (all
  seven implementations converged on last-wins — the map shows
  non-convergence only), and finds **three silences stage 2 never saw**:
  malformed-line handling (180 probes: skip vs ValueError vs
  whole-line-as-key), leading-blank handling (one model errors on a
  leading newline), and comment lines.
- **confparse (ladder)**: resolves six distinct splits mapping onto the
  known intent bits — key-case, coercion, colon/malformed (two
  partitions), section/continuation, value-text — with the two
  prior-coincident bits correctly absent.
- **The ratchet, measured**: C_0 class 242 divergent probes / 4 silences →
  C_1 class 192 / 3, with the pinned silences (coercion) *gone from the
  map*. Pinning contracts the measured silence; the instrument reads the
  contraction.

`map_*.json` are the saved maps. Every remaining cluster is a candidate
pin, staged for the keyholder — most prominently the malformed-line
surface that both subjects leave open.
