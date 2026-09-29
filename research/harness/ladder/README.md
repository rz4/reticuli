# The generation ladder

*Research tooling — not normative, not pinned.*

The question: when an agent rewrites a working module generation after
generation, and the only enforced floor is the claim's gate, what happens to
the behavior the gate is silent about?

## The subject

`claims/L` is a sealed config-parser claim (`confparse`). Its check `C_0`
pins the happy path only. Generation 0 (`claims/L/parser.py`) makes eight
deliberate, **undocumented** choices on the surface the check never
exercises — the intent bits (`probes.py`):

| bit | generation 0 | the families' prior (measured) |
|---|---|---|
| coercion | integer-looking values become `int` | stay strings |
| duplicates | first occurrence wins | last wins |
| colon_sep | `key: value` accepted | `=` only |
| key_case | keys lowercased | case preserved |
| bad_line | separator-less lines skipped | mostly `ValueError` |
| inline_hash | `#` mid-line is literal | literal (coincides) |
| continuation | trailing `\` joins lines | not supported |
| section | `[db]` prefixes keys | not supported |

## The three conditions

- **Blind** (`--controls`): the shipped producers regrow `parser.py` from
  the check alone — the stage-2 protocol. This samples the prior: what a
  model believes a config parser is, restricted to the gate.
- **Faithful chain** (`--chain codex|claude`): each generation, the
  producer is handed the previous implementation over the claim's
  format-3 guidance channel — which the root excludes, so every
  generation re-earns the SAME root — and asked to rewrite it "in your
  own style". Nothing about behavior preservation is said.
- **Minimize chain** (`--chain codex-min|claude-min`): same, but the ask
  is "as short and simple as you can while the project's check still
  passes" — ordinary engineering pressure, with the gate named as the
  floor.

Every accepted generation passed the gate in the kernel's sandbox and
re-earned the subject's root; the kernel refuses a producer that touches
pinned bytes. The identity never moves. Only the unpinned surface is in
play — which is the point.

## Running it

    python3 run_ladder.py --chain claude --gens 16
    python3 run_ladder.py --controls
    python3 run_ladder.py --fingerprints     # measure + write fingerprints.json
    python3 run_ladder.py --report

Resumable: a chain continues from its highest generation on disk; a quota
signal stops cleanly. `chains/*/gens/` and `controls/` hold the
implementations (committed — they are the data); `fingerprints.json` holds
the measurements.

## What it found (run 2026-09-29)

See `research/provenance/` for the full record. In brief: the blind
condition loses seven of eight bits immediately and near-unanimously across
both families; the faithful chains preserve eight of eight, generation
after generation; the minimize chains collapse to the blind attractor in a
single generation. Unpinned intent is carried by the visible artifact, not
by the boundary — and it survives exactly until an instruction gives the
model a reason to spend it. Under optimization pressure the gate stops
being a floor and becomes the whole definition of "what must keep
working": everything unverified is treated as disposable. The repair is
the protocol's usual one — a bit a consumer relies on is a bit the check
must pin.
