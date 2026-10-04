# The clean-room pass: the stranger simulation, run before the stranger

*2026-10-03, cycle 13. The endgame's first physical item: eat the
environmental breaks a stranger would otherwise find. Harness: a fresh
`git clone` into a scratch directory, a fresh venv, and a scrubbed
environment (`env -i` with minimal PATH/HOME/TMPDIR, no RETICULI_*
variables, no vendor credentials) — then the full first-contact arc.*

## The result: green, end to end

    pip install .            clean — no undeclared Python dependencies
    ret --version            speaks
    ret verify .             the clone verifies at its manifest root
    init → run → pack →      the documented no-agent quickstart arc,
      verify → audit           on a toy claim, all green
    python3 gate.py          REPO_OK — the full gate, cold, in the clone,
                               under the scrubbed environment

The predicted embarrassing environmental breaks did not appear: the
earlier `requires` pin (`ssh-keygen`), the declared `gate_timeout`, and
the stdlib-only promise held in a room the development machine never
touched beyond the clone.

## The one papercut, found and fixed

The first run deviated from the documented flow the way a hurried
stranger would: the toy check wrote its own `OK` as a side effect, and
the observed gate command never named it. `ret pack` refused —
correctly — but the refusal (`'OK' is declared as an input to no gate`)
pointed at neither of the documented ways out, even though
`docs/quickstart.md` explicitly anticipates the no-agent reader. The
refusal now carries the hint: the gate command itself must create the
verdict (`"<your check> && printf ok > OK"`) — earned by the gate, not
written beside it. A generated-module change; the message text was
pinned nowhere; `authoring_check` and `surface_check` pass; the root is
unmoved. Re-run under the documented flow, the clean room passes
everything.

## What this retires

One of the three endgame items ahead of the ceremony. The standing
prediction for real contact ("first failure will be environmental,
within minutes") now has its rehearsal data: the environment held, the
documentation held, and the one friction point was a refusal that knew
the problem but not the remedy — the exact class of break to expect
more of from a real stranger, and the exact kind this pass exists to
pre-empt.
