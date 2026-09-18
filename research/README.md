# Research

This wing holds the experimental record: what was tried, what it cost, and
what it showed. None of it is needed to *use* reticuli — a new operator can
stop at `README.md` and `docs/`. It is here so that the lineage is
reconstructable without mining git history.

The rule that separates this wing from the rest: **`spec/` says what is true,
`docs/design-rationale/` says why it is designed that way, and `research/`
says what was tried on the way there.**

## The open call

[`open-call.md`](open-call.md) is the standing public invitation: regrow
reticuli from its frozen boundary alone, bring any producer, and let this
repository's own machinery re-earn your verdicts. The call is open once its
record is signed and sits at `open-call/reticuli.record.json`.

## Provenance

[`provenance/`](provenance/) is the dated ledger. It records, in the order it
happened:

- **revisions** (`revision-*.md`) — each time the boundary moved, and why the
  root moved with it;
- **rebuilds** (`rebuild-*.md`) and **attempts** (`attempt-*.md`) — independent
  reconstructions from the boundary, including paid ones that did not land: a
  failed attempt's ledger, without its bytes, is evidence of either a hole in
  the suite or a limit of the producer;
- **crosschecks** (`crosscheck-*.md`) — one root surviving across machines;
- **bootstrap** and **signing** — the self-hosting fixpoint and the ceremony
  that closes a claim.

A reader following a verdict back to its origin walks this directory. A
producer deciding whether to attempt the call reads it for the going rate.

## Audits

[`audits/`](audits/) holds read-the-repo-as-a-stranger reviews: dated passes
that check whether each kind of newcomer — new user, agent developer, script
author, packager, security reviewer, future maintainer — can accomplish their
goal from the docs alone, and what gaps that surfaced. They drive doc and
maturity work; they are records, not contracts.
