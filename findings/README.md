# Findings

What this project has measured, stated as findings rather than as working
notes. Each document carries the result, the method, and the limit; each sits
above a pile of raw material in [`research/`](../research/), which holds the
ledgers, the preregistrations, the provenance records and the data.

Results that went against the hypothesis are here on the same footing as the
ones that did not. Two of the three documents below contain a prediction this
project made and then falsified.

| | finding | status |
|---|---|---|
| [Self-hosting](self-hosting.md) | the tool regrew itself from its own frozen boundary three times, three generations deep, with ~0.12 text similarity between realizations | the arm is **open**: 0 of 3 at the current root, and no trial has ever been re-earned outside this environment |
| [The jq external target](jq.md) | three independent human implementations disagree on 28.5% of jq's own official test corpus; a blind rebuild passed 465 of 465 cases by being a lookup table | recall against the human divergence surface was 17.6% against a preregistered 30% — **falsified** |
| [Substitution](substitution.md) | six blind rebuilds from two model families all passed the parser's gate, all differed by bytes, and all six broke the consumer identically | mechanism demonstrated; base rate not measured |

## Why these are not on the documentation site

[The manual](https://rz4.github.io/reticuli/) teaches how to use reticuli.
These are claims about what it has been shown to do, and they belong next to
the code and the data they are claims about, where the links down into
`research/` resolve against the bytes a reader can check.
