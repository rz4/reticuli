# The probe runs the member's own code, or refuses

2026-10-30. **Zeta's** root moves `b0e235d2…` → `237ce0b6e1b860b0...` (the
companion claim's own identity; the primary holds at `f2d49443…`, untouched).
An internal click: the pinned edits are a new criterion
`zeta/criteria/probe_check.py` and its line in `zeta/reticuli.toml`'s inputs.
Keyholder-authorized directly ("harden the probe").

## Why

The grade-2 probe of the closure trials
(`research/harness/closure/grade2-the-crown-jewel.md`) fell into the
import-resolution trap three ways and reported the **shipped** kernel's
behaviour as a trial's. The root cause: zeta's probe loaded a member under its
registry package name and trusted it, but a reconstruction that imports its
internals absolutely — `from reticuli._kernel import run`, as `r24-claude`
does — resolves those internals from whatever `reticuli` is reachable, and an
editable install answers from the shipped tree. The old guard checked
`kernel.__file__` sat under the member tree; it did, while the code that ran
did not. An instrument meant to certify replacement was reporting the thing it
was measuring against.

## What changed

**The member is staged as `reticuli` and run under `-I -S`.** The member's
package directory is symlinked in under the canonical name, and the driver
runs isolated *and* without site, so the editable `.pth` is never processed
and no ambient `reticuli` can answer. A reconstruction's absolute
`from reticuli._kernel import ...` now resolves to its OWN tree, and a
relative `from ._kernel import ...` does too. That staging is the fix —
verified: before it, probing `r24-claude`'s `cost` on a negative-value ledger
returned the shipped reading `{tokens: 10}`; after it, r24's own code answers
`{tokens: 10, usd: -5}`, the genuine divergence correctly attributed to the
member.

**A code-containment backstop.** Even staged, the driver resolves the probed
function through any decorator wrapping to the file its code actually lives in,
and refuses (`misresolved`, `ForeignCode`) unless that file is under the
member's declared tree. It cannot catch a one-line facade that *delegates* to
foreign code — the delegator's own code is legitimately under the tree — which
is precisely why the staging, not this check, is the real fix: with no ambient
`reticuli` reachable, there is no foreign code to delegate to. The backstop
earns its place against the other escape, a package whose code is symlinked in
from outside the declared tree, which it refuses.

**A pinned criterion with three controls.** `probe_check.py` builds fixture
members and asserts: a correctly-staged member answers with its OWN code even
though an ambient `reticuli` could have answered (the resolution control, and
the check confirms the ambient install is importable or the control would be
vacuous); a member whose probed function is really `json.dumps` — foreign code
in the standard library — is refused as `ForeignCode`, not run; and a call the
member does not define is `absent`. The negative control bites: without the
containment check, the foreign function runs and returns a value; without the
staging, the resolution control's member answers from the shipped tree.

## What it does not close

A facade that reimplements its logic inline is running its own code, which is
legitimate — the lesson there is for the reader, not the guard, and lives in
the reconstruct-codebase skill's probe-trap list: do not *predict* a member's
behaviour from a module its facade does not call. And this hardens the
`python-package` driver; the `process` and `substitution` drivers answer
different questions and were not in scope.

## Re-earned

```
zeta/criteria/probe_check.py   probe-ok (3 controls)
zeta/gate.py                   zeta-ok, 9 suites, at zeta root 237ce0b6
ret verify zeta                ok, 237ce0b6
ret verify .  (primary)        fresh, f2d49443 — untouched
python3 gate.py (primary)      repo-ok
pytest tests/                  223 passed (test_zeta's probe suite included)
live sweeps                    reticuli singleton, deployment 78/78 agreement
                               through real alternate interpreters, staged -S
```
