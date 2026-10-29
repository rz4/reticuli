# Security

Reticuli is pre-release. Its security posture is described in full in
[`docs/threat-model.md`](docs/threat-model.md); this file is the reporting
channel and the scope.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
vulnerability reporting on this repository (the **Security** tab →
**Report a vulnerability**), which opens a private advisory visible only to
the maintainers.

Please include what you were running, the platform, and the smallest input
that reproduces the finding. You will get an acknowledgement; a fix or a
reasoned decline follows in the advisory thread.

## What is in scope

The things that would let a claim lie or a gate reach past its confinement:

- an identity collision or bypass — two materially different claims sharing a
  root, or a `verify` that passes on bytes that do not match the sealed root;
- a record that a reader would accept as genuine but that was not produced by
  the run it names, or a signature check that accepts an unsigned or
  wrong-key record;
- a gate escaping its sandbox — writing outside its workspace, reaching the
  network, or reading files that strict `audit` is meant to mask;
- **a path that runs a claim's gate command outside the jail.** `run_gate` is
  the one place a gate is supposed to execute, and any route around it is in
  scope even when the route is ours. Two were found and closed on 2026-10-29:
  the bundled SDK producers ran the recipe's gate with a bare
  `subprocess.run(shell=True)` carrying the caller's whole environment — so
  `ret rebuild` on a stranger's claim reached the operator's home and the
  vendor key that session was holding — and the launcher carried a second,
  drifted copy of the sandbox profile. If you find a third, it is a report;
- a rebuild or crosscheck reporting agreement where there is none.

## What is not a vulnerability

These are documented properties, not flaws — see the threat model:

- **A weak check admits weak code.** The root names an equivalence class as
  wide as its tests; a thin suite defines a wide class, backdoor and all.
  `examples/weak/` ships this on purpose. This is the tool working as
  specified, not a bug.
- **A gate is arbitrary code you chose to run.** The sandbox limits what a
  gate can do; it does not make running a stranger's gate safe by itself.
- **Reticuli does not prove correctness or producer independence.** It
  distinguishes byte reuse from a genuine rebuild and records declarations as
  declarations. Whether a producer ever saw the original is not something the
  tool can find.
- **A producer is not confined, and cannot be.** `rebuild` runs the producer
  itself outside the jail on purpose — it needs the network to reach a model
  and a credential to authenticate — and this is pinned as a requirement in
  `criteria/build_check.py`, not an oversight. What *is* confined, as of
  2026-10-29, is the gate the producer runs while it iterates. Two
  consequences remain yours to accept rather than ours to close: the
  `codex` and `claude` adapters hand the room to an agent CLI you have
  signed into, which brings its own sandbox (`--sandbox workspace-write`,
  `--dangerously-skip-permissions`) and not this one; and a recipe's
  `guidance` text reaches the model unescaped, so a hostile claim can
  address your producer directly. Treat `ret rebuild` on an untrusted claim
  the way you would treat running its build script — because for the
  duration of the producer session, that is what it is.

## Supported versions

Until the first tagged release, only `main` and the latest tag are supported.
The compatibility promise for released formats is in
[`docs/compatibility.md`](docs/compatibility.md).
