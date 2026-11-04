# Capturing work: init → work → pack

*Informational — an operational guide. The normative contract is in [`spec/`](https://github.com/rz4/reticuli/tree/main/spec/).*

Most of this repository is about verifying a claim someone already sealed.
This page is about the other end: turning a stretch of real work, by a human,
an agent, a script, or all three, into a claim in the first place, without
making the work bend around reticuli.

The shape is Git's:

```
cd project
ret init            # this workspace is now watched
...arbitrary work...
ret pack --accept <verdict> -o <claim>
```

`ret init` does not begin a session, it marks a workspace. Like `git init`,
it means that work done here may become a claim, not that one editing session
has started. You can close the shell, come back next week, run a different
tool, and the same trace keeps filling. The boundary is the directory rather
than the process.

## What gets observed

Reticuli watches the work three ways, and records each observation along with
where it came from, which is its evidence.

- **Agent hooks.** `ret init` auto-wires the Claude Code harness through a
  `.claude/` directory, so each prompt, file write, file read, and command it
  runs is appended to the trace. The wiring adapts to how reticuli is
  installed, so it is never pointed at a command that is not there.
- **Any other harness, via `ret init --agent generic`.** Point your harness
  at `ret hook`, feeding one JSON event per call on stdin:

  ```json
  {"event": "write" | "read" | "bash" | "prompt",
   "path" | "cmd" | "text": "...", "cwd": "<workspace>"}
  ```

  That is the whole contract, and anything that can emit it integrates
  without a special case in reticuli.
- **`ret run <command>`.** An explicit, human-authored execution boundary
  that runs the command and captures its file effects through a
  before-and-after content scan of the workspace, so files a script or
  subprocess creates or modifies are captured even though no editor hook saw
  them. It stays silent, and only the child's own streams appear.

Reads by a subprocess cannot be derived from a content diff, so they stay
unobserved, and `pack` says so rather than guessing.

## What `pack` does with it

`ret pack --accept <verdict> -o <claim>` proposes a recipe from the trace.
Observed writes become generated outputs, the command that writes the
accepted verdict becomes the gate, and read and command-named files become
pinned inputs. It then re-earns every gate cold in a clean workspace and
seals only if the pinned verdicts reproduce. The trace has no authority at
all: a wrong proposal simply fails to certify, and nothing false can ride
into a claim.

Because observation is never complete, `pack` is honest about its gaps and
still seals. Alongside the packed root it reports what it could not
establish:

```
packed  4e7c…
  warnings
    observed a write to scratch.py, now gone from disk; it is not in the claim
    1 input(s) inferred from command text, not an observed read: check.py
    producer cost not established (no harness transcript in the session window)
```

These make the authoring vocabulary visible: a file the hooks observed, what
pack declared it, what re-earned cold and is sealed, an input inferred from
command text rather than an observed read, and a present file the trace never
touched, left unobserved. A warning does not withhold the claim, since the
cold re-earn already did the deciding. It tells you where to look before you
trust it, or which role to pin explicitly with `--claim <file>` or
`--generated <file>`.

## Where the trace lives

Everything captured is local residue and never part of a claim's identity.
The trace is `.reticuli/draft.jsonl`, which `ret init` gitignores. Capturing
more, or capturing badly, can never change a root. It can only change what
`pack` proposes, which you review and which the cold re-earn certifies.

See also [`docs/producers.md`](producers.md), on writing a producer for the
rebuild side, and [`docs/receiving.md`](receiving.md), on what to do with a
claim someone hands you.
