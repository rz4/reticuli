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

## Supported versions

Until the first tagged release, only `main` and the latest tag are supported.
The compatibility promise for released formats is in
[`docs/compatibility.md`](docs/compatibility.md).
