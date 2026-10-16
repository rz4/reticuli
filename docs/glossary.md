# Glossary

Terms are listed in the order a newcomer tends to meet them, not
alphabetically; each entry links onward to the page that treats it fully.

**Claim** — a directory asserting that some software satisfies stated
criteria: pinned acceptance checks, specification, and recipe, plus a
generated implementation. The unit that is named, transferred, verified,
and rebuilt. See [The process](process.md).

**Root** — the SHA-256 over a claim's pinned material. The software's
identity. The implementation is excluded from it by construction, so
regenerating the implementation preserves identity and editing a criterion
changes it.

**Pinned / generated / unpinned** — the three standings a file can have.
*Pinned* material is inside the root and changes only under signature.
*Generated* material (the implementation) is outside the root and judged
only by the gates. *Unpinned* material (tests, documentation, research)
affects confidence and context, never identity. The distinction drives
[pull-request review](github.md#reviewing-pull-requests-when-agents-write-code).

**Gate** — the recipe's acceptance command. Passing it in a clean room is
what admits an implementation to the class the root names.

**Room** — an isolated directory holding only a claim's declared inputs,
with the process environment scrubbed. Producers work in rooms; audits
re-earn verdicts in rooms; nothing undeclared reaches either.

**Producer** — any program that can regenerate a claim's implementation
from its pinned inputs. A compiler qualifies; in practice it is usually a
coding agent. See [Working with agents](agents.md).

**Verify** — recompute the root and compare. Cheap; answers "is this the
claim it says it is?"

**Audit** — re-earn every gate cold, in a fresh room, from declared inputs
only. Answers "do its promises still hold here, for me?"

**Crosscheck / the three-machine test** — the full validity instrument:
one root at origin (M1), after transfer (M2), and after a blind rebuild
(M3), every gate re-earned, cost within a declared band. See
[the three-machine test](process.md#the-three-machine-test).

**Verdict** — three-valued: accepted, rejected, or *incomplete*. A
declared condition that was not measured is incomplete, and incomplete
never accepts.

**Record** — a signed, canonicalized statement of one machine's results:
identity recomputed, gates earned, environment, measured cost. The one
file format intended for third parties. CI uploads one per machine per
run.

**Population** — the set of implementations that have passed the current
root's gate: independent reconstructions, the same bytes across host
environments, and externally authored controls. Membership is relative to
a root and is never inherited across a root move.

**Zeta** — the exploratory instrument: probes populations for behavioral
differences, classifies findings, and queues them. It holds no authority;
the primary claim's criteria forbid depending on it.

**Finding / lanes** — a verified behavioral difference, classified by the
cost of adopting it: a *contraction* (all members already agree; pinning
evicts no one), an *eviction* (members disagree; pinning excludes someone),
or a *repair* (independent evidence says all members are wrong).

**Queue** — where findings wait, each packaged to reproduce independently.
Nothing leaves the queue except by signature.

**Signature** — human authorization, the only operation that changes
obligations. A signature amends pinned material, which moves the root and
retires the standing population.
