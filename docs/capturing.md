# Capturing work: init → work → pack

*Informational — an operational guide. The normative contract is in [`spec/`](../spec/).*

Most of this repository is about *verifying* a claim someone already sealed.
This page is about the other end: turning a stretch of real work — by a human,
an agent, a script, or all three — into a claim in the first place, without
making the work bend around reticuli.

The shape is Git's:

```
cd project
ret init            # this workspace is now watched
...arbitrary work...
ret pack --accept <verdict> -o <claim>
```

`ret init` does not begin a session; it marks a **workspace**. Like `git init`,
it means "work done here may become a claim," not "start one editing session."
You can close the shell, come back next week, run a different tool, and the same
trace keeps filling. The boundary is the directory, not the process.

## What gets observed

Reticuli watches the work three ways, and records each observation with where it
came from (its *evidence*):

- **Agent hooks.** `ret init` auto-wires the Claude Code harness (a `.claude/`
  directory), so each prompt, file write, file read, and command it runs is
  appended to the trace. The wiring adapts to how reticuli is installed, so it
  is never pointed at a command that is not there.
- **Any other harness — `ret init --agent generic`.** Point your harness at
  `ret hook`, feeding one JSON event per call on stdin:

  ```json
  {"event": "write" | "read" | "bash" | "prompt",
   "path" | "cmd" | "text": "...", "cwd": "<workspace>"}
  ```

  That is the whole contract; anything that can emit it integrates without a
  special case in reticuli.
- **`ret run <command>`.** An explicit, human-authored execution boundary that
  runs the command and captures its **file effects** — a before/after content
  scan of the workspace, so files a script or subprocess creates or modifies are
  captured even though no editor hook saw them. It stays silent: only the
  child's own streams appear.

Reads by a subprocess cannot be derived from a content diff, so they stay
**unobserved** — and `pack` says so rather than guessing.

## What `pack` does with it

`ret pack --accept <verdict> -o <claim>` proposes a recipe from the trace —
observed writes become generated outputs, the command that writes the accepted
verdict becomes the gate, read and command-named files become pinned inputs —
then **re-earns every gate cold in a clean workspace** and seals only if the
pinned verdicts reproduce. The trace has zero authority: a wrong proposal simply
fails to certify; nothing false can ride into a claim.

Because observation is never complete, `pack` is **honest about its gaps** and
still seals. Alongside the packed root it reports what it could not establish:

```
packed  4e7c…
  warnings
    observed a write to scratch.py, now gone from disk; it is not in the claim
    1 input(s) inferred from command text, not an observed read: check.py
    producer cost not established (no harness transcript in the session window)
```

These are the authoring vocabulary made visible: a file the hooks *observed*;
what pack *declared* it; what re-earned cold and is *sealed*; an input *inferred*
from command text rather than an observed read; a present file the trace never
touched, left *unobserved*. A warning does not withhold the claim — the cold
re-earn already did the deciding — it tells you where to look before you trust
it, or which role to pin explicitly (`--claim <file>`, `--generated <file>`).

## Where the trace lives

Everything captured is **local residue**, never part of a claim's identity: the
trace is `.reticuli/draft.jsonl`, gitignored by `ret init`. Capturing more, or
capturing badly, can never change a root — only what `pack` proposes, which you
review and which the cold re-earn certifies.

See also [`docs/producers.md`](producers.md) (writing a producer for the rebuild
side) and [`docs/receiving.md`](receiving.md) (what to do with a claim someone
hands you).
