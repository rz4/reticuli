# Design rationale

Why reticuli is built the way it is. These documents are not normative — the
contract lives in [`spec/`](../../spec/) and the stability promise in
[`docs/compatibility.md`](../compatibility.md). This is the reasoning behind
those decisions, kept separate so that a reader can tell an argument from a
rule.

- [`format3.md`](format3.md) — why producer guidance was moved out of the
  root: a hint helps a producer find an implementation but cannot decide
  whether one is accepted, so rewording it must not rename the claim.

More rationale is added here as decisions are made. When a design question is
still open, it belongs here or in an issue — never in a normative `spec/`
file, where a reader cannot tell a proposal from a promise.
