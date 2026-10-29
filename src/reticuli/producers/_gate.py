"""Running the room's gate for a producer -- through the jail, not around it.

A producer iterates: write a file, run the gate, read the failure, write
again. The command it runs comes out of the claim's own recipe, and `ret
rebuild` is pointed at claims the operator did not write. So the loop that
helps a model converge was also the loop that executed a stranger's shell
command with the caller's entire standing: real `HOME`, real network, and --
because `rebuild` holds a vendor credential for the length of the session --
that credential sitting in the environment it inherited. The kernel's own
gate runs were jailed the whole time; this path simply was not one of them,
and it is the path that runs FIRST.

Routed through `run_gate` instead, which is where the kernel says every gate
belongs: scrubbed environment, wall-clock ceiling, whatever jail the host
has. Two things follow, and the second is not about security at all.

1. A hostile recipe no longer reaches the operator's files or their keys
   through the one verb aimed at other people's claims. One exception, and
   it is the operator's to choose: under `RETICULI_GATE_MATRIX` the second
   leg deliberately asks for the no-sandbox condition and therefore runs the
   gate unconfined. The environment is still scrubbed on that leg, so no
   credential travels; the filesystem is not.
2. The producer now develops against THE SAME CONDITIONS THE VERDICT WILL BE
   EARNED UNDER. This repository has already paid for the other arrangement:
   a gate piping into `diff -u expected -` passed locally and on Linux CI and
   failed under macOS seatbelt, because BSD `diff` spools non-seekable stdin
   to the system temp dir. Unjailed, a producer writes that gate, sees green,
   and the claim dies at the cold audit -- after the session is over, where
   no model can act on it. Jailed, it fails in the room, in band, while the
   model is still holding the context to fix it.

Shared by every adapter for the reason `_inputs.py` is: the same four lines
of `subprocess.run(gate_cmd, shell=True)` existed in each one, so the same
defect existed in each one, and fixing a single adapter would have left the
rest to rediscover it.

Nothing here touches identity. Producers are outside the claim by design
(`reticuli.toml`); this changes how a producer is hosted, never what the
root admits.
"""
import os

from .._kernel import run as _run
from .._kernel.core import ClaimError

#: The matrix legs, in the order a producer should read them. A conforming
#: claim must hold BOTH where a jail applies and where one does not -- a
#: producer only ever sees the host it runs on, so a single-condition pass is
#: environment-scoped conformance: real, but narrower than the claim.
#:
#: The second leg asks `sandbox_backend()` to report `inherited`, which is how
#: a host with no usable jail behaves. That leg therefore runs the gate
#: UNCONFINED -- deliberately, because the condition it exists to test is
#: "this claim on a host without a sandbox". It is opt-in behind
#: RETICULI_GATE_MATRIX, so the operator chooses it; what it never does is
#: hand the gate an inherited credential, because `run_gate` scrubs the
#: environment whatever the backend turns out to be.
MATRIX = (("jailed", False), ("sandbox-inherited", True))

TAIL = 4000
TAIL_MATRIX = 2000


#: The nesting signal. `sandbox_backend()` reads it to decide whether a jail
#: is already in force, so SETTING it is how the matrix asks for the
#: no-sandbox leg without reaching past `run_gate` to get it.
#:
#: CLEARING it is never right, and doing so was a real defect in the first
#: version of this file. `_JAILED` is in the kernel's `_KEEP_ENV`, so a
#: producer launched from inside a jail -- which is exactly what the
#: self-hosting chain does, and what `criteria/build_check.py` documents as
#: the outer-confinement case -- inherits the signal legitimately. Popping it
#: made `run_gate` try to apply a sandbox inside a sandbox, which fails with
#: `sandbox_apply: Operation not permitted` and exit 71. Every `run_gate`
#: tool call would have returned that, so the model would burn all forty
#: turns and the layer would be recorded as a capability failure: a harness
#: bug wearing the costume of a model that cannot code. "Sandboxes do not
#: nest" is the kernel's rule and this module must not vote on it.
JAILED = "RETICULI_JAILED"


def _one(command: str, recipe, inherited: bool) -> dict:
    """One gate run through the kernel.

    `inherited=False` touches the environment not at all: whatever nesting
    state the producer legitimately inherited is the state the gate is judged
    under, and `sandbox_backend()` decides. `inherited=True` is the matrix's
    no-sandbox leg and sets the signal for the duration, restoring it exactly
    as found -- absent stays absent -- because a session runs many gates and
    a leaked signal would un-jail every one that followed.
    """
    if not inherited:
        return _run.run_gate(command, ".", recipe)
    had, saved = JAILED in os.environ, os.environ.get(JAILED)
    # The value is a backend NAME, not a flag: `criteria/kernel_check.py`
    # pins that, and a nested claim runner reads it back expecting one.
    os.environ[JAILED] = saved if had else "inherited"
    try:
        return _run.run_gate(command, ".", recipe)
    finally:
        if had:
            os.environ[JAILED] = saved
        else:
            os.environ.pop(JAILED, None)


def run(command: str, recipe=None, matrix: bool = False) -> str:
    """The `run_gate` tool's reply: an exit code and the tail of the output.

    The string shape is the producer protocol and is deliberately unchanged
    -- `exit=<n>` then output -- so no prompt and no adapter has to learn a
    new format to get the jail.
    """
    if not command or not command.strip():
        return "exit=1\nthis claim declares no gate command"
    # A refusal from the kernel is reported IN BAND, like a malformed tool
    # call: the adapters' standing policy is that a recoverable problem is
    # the model's to correct, not this program's to die of. An unrunnable
    # sandbox binary used to surface as a traceback that killed the attempt
    # and recorded a harness fault as a capability fault.
    try:
        if not matrix:
            r = _one(command, recipe, inherited=False)
            tail = (r.get("stdout", "") + r.get("stderr", ""))[-TAIL:]
            note = "" if r.get("status") != "timeout" else (
                f"\n[the gate exceeded its {r.get('timeout')}s ceiling]")
            return f"exit={r.get('returncode')}\n{tail}{note}"
        worst, parts = 0, []
        for label, inherited in MATRIX:
            r = _one(command, recipe, inherited=inherited)
            code = r.get("returncode")
            worst = worst or (code or 0)
            body = (r.get("stdout", "") + r.get("stderr", ""))[-TAIL_MATRIX:]
            parts.append(f"[{label} jail={r.get('quarantine')}] "
                         f"exit={code}\n{body}")
        return f"exit={worst}\n" + "\n".join(parts)
    except ClaimError as exc:
        return f"exit=1\nthe harness could not run the gate: {exc}"
