# reticuli

Reticuli identifies software by a SHA-256 hash — the **root** — computed
over its acceptance criteria, specification, and build recipe. The
implementation is excluded from the hash: any implementation that passes
the acceptance gate is a member of the class the root names. Verdicts are
re-earned, never inherited, so verifying a claim requires trusting no one.

## Install

```console
$ git clone https://github.com/rz4/reticuli && cd reticuli
$ pip install .
$ ret --help
```

## First commands

Against the shipped example (its producer is `make`; no model, no network):

```console
$ cd examples/make
$ ret verify .          # is this the claim it names?   exit 0
$ ret audit .           # do its promises hold here?    re-runs the gate, sandboxed
$ ret rebuild . --producer make --into /tmp/M3
rebuilt  0996e1a5bead...
```

[The quickstart](quickstart.md) walks this end to end with every command's
real captured output — including the refusals: a tampered pinned byte, a
damaged implementation, and what each instrument says about them. After
that page you can verify, audit, rebuild, and record claims; everything
further is depth, not prerequisites.

## Where things are

The documentation runs general to specific, and every level is
self-sufficient — stop when you can do what you came for. The sidebar is
the map: the [quickstart](quickstart.md), then [the process](process.md) (the
lifecycle and the three-machine test), then the task sections in
increasing depth — [using claims](receiving.md),
[producing with agents](agents.md),
[evolving the specification](zeta.md) — then
[internals](mechanisms.md) and [reference](cli.md), and at the bottom of
the ladder [the annotated implementation](book/index.md): every module,
full source with its commentary, generated from the tree.

The pinned inputs themselves (`criteria/`, `spec/`, zeta's criteria) are
deliberately not rendered in this site. They are the identity; read the
bytes in the repository.
