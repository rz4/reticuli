# Proposal — the producer keeps the caller's HOME

*Staged 2026-10-06, from closure trial 1 second attempt (r6). A
contract decision for the keyholder; nothing here moves a root until
signed. Third member of the producer-environment family, after
free-the-producer (no jail) — freedom turned out to have two halves,
and the pins so far bought only one.*

## The finding

The r6 tree runs producers unjailed with the network reachable — the
free-the-producer pin held; its requests REACH api.openai.com — and
every real producer still dies with 401 Unauthorized, because the r6
scrub hands producers a scratch HOME (its gates' scrub, reused), and
the codex CLI's credential lives in `~/.codex`. Two witnesses in one
run: the judge's gen-2 rebuild and the condition-4 CLI trial, both
failing on the same request id shape. The socket-bind probe the pin
landed with needs no credential, so a scratch-HOME kernel passes it
and is sterile anyway: it can reconstruct with toy producers and
nothing that authenticates.

## Why the contract should say "the caller's HOME"

The producer is the CALLER's oracle: the caller chose it, and its
credentials are the caller's own, living where the caller's tools keep
them. The scrub doctrine ("nothing arrives that the caller did not
place here") is about the GATE, which must never see inherited
secrets; the producer is the opposite boundary — it works FOR the
caller, with the caller's standing, and its output faces the jailed
gate regardless. Scrubbing the producer's HOME protects nobody and
disables every authenticated producer — model CLIs, ssh-based tools,
anything with a keychain.

## What must be pinned if accepted

`build_check`'s producer-freedom block gains the second half: the
rebuild's producer observes the caller's HOME (the check bakes its own
`os.environ["HOME"]` into a producer command that compares and
refuses). Kept apart from the gate assertions, which continue to pin
the OPPOSITE (gates get a scratch HOME — nothing inherited). One
criteria edit — a root move — hence the signature gate.

## The pattern, named

free-the-producer pinned the jail half; this pins the environment
half. Each was found by a different generation choosing a different
wrong default, and neither was derivable in advance — the probe only
ever covers the witnesses seen. The producer-environment contract is
being discovered the same way the jail floor is: one plank per draw.

## Status

Signed by the keyholder 2026-10-06 ("I sign them continue to r7") and
landed the same day as one bundle with its two siblings (see the
provenance record revision-2026-10-06-the-migration-bundle.md).
