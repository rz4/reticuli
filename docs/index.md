# reticuli

Software is normally named by where it came from: a repository, a tag, a
commit. Reticuli names it by what it has to do. The name is a SHA-256 over
the acceptance criteria, the specification, and the build recipe. The
implementation is excluded from that hash, so every implementation passing
the acceptance gate is a member of the class the name identifies, and
changing one byte of a criterion gives a different name.

That separates two questions people usually run together.

<div class="grid cards" markdown>

-   **Is this the thing I was given?**

    A hash comparison, in milliseconds, executing nothing. `ret verify`
    answers it. Identity.

-   **Does it still earn its verdict here?**

    Re-running every gate cold, in a sandbox, on your machine, trusting no
    stored result. `ret audit` answers it. Membership.

</div>

Verdicts are re-earned rather than inherited, which is what lets you verify
a claim while trusting no one — not the author, not the producer, and not
the machine it was made on.

## If you are deciding whether to trust this

Three pages, in this order, and you will know where you stand.

1. **[What a claim proves, and what it does not](threat-model.md)** is the
   honest boundary, and it is short on purpose. A claim establishes that an
   artifact satisfies these criteria plus a measurement of how strong the
   criteria are. It does not establish that the artifact is correct, safe,
   or free of anything, and a backdoored implementation that passes the
   tests is admitted by design.
2. **[The quickstart](quickstart.md)** runs the whole loop against a shipped
   example in about ten minutes, with no API key and no model. Every block
   on that page is a real captured invocation, including the refusals.
3. **[The process](process.md)** is the mechanism underneath: six stages,
   the three-machine test, and the rule that only a human signature can
   change an obligation.

!!! warning "Pre-release, and the format has already moved"

    Five claim formats exist and the kernel's own claim has changed identity
    twice, both times deliberately and both recorded. Do not build something
    on this that cannot tolerate a root changing. The stability promise that
    *does* stand as of v2.0.0 is in [compatibility](compatibility.md).

## Install

```console
$ git clone https://github.com/rz4/reticuli && cd reticuli
$ pip install .
$ ret --help
```

Standard library only, on macOS or Linux, since gates run under
`sandbox-exec` or `bwrap`. Then, against the shipped example, whose producer
is `make`, so no model and no network are involved:

```console
$ cd examples/make
$ ret verify .          # is this the claim it names?   exit 0
$ ret audit .           # do its promises hold here?    re-runs the gate, sandboxed
$ ret rebuild . --producer make --into /tmp/M3
rebuilt  0996e1a5bead...
```

## Checking it without taking our word for it

The identity computation is specified in
[`spec/identity.md`](https://github.com/rz4/reticuli/blob/main/spec/identity.md)
precisely enough to reimplement, and the repository ships a second
implementation of it (`reticuli.reference`) kept deliberately independent of
the kernel, so the two have to agree on every root.

You do not have to take the specification's word for your reimplementation
either.
[`spec/vectors/`](https://github.com/rz4/reticuli/blob/main/spec/vectors/README.md)
holds conformance vectors — tiny claims with their expected roots and build
digests — and a runner that points any implementation, in any language, at
them. Reproduce every expected value and you conform; miss one and the vector
names which rule you got wrong. Passing the set is necessary and not
sufficient, and `spec/vectors/README.md` names the cases it does not cover.

## Where everything is

The documentation runs general to specific, and every level is
self-sufficient, so stop when you can do what you came for.

| Section | For |
|---|---|
| **Start here** | deciding whether this is for you, and running it once |
| **Using claims** | receiving someone's claim, authoring your own, wiring CI |
| **Producing with agents** | regrowing implementations, writing criteria that carry software |
| **Evolving the specification** | how an obligation changes, and what that costs |
| **Internals** and **Reference** | rooms, sandboxes, the CLI contract, compatibility |
| **The annotated implementation** | every module, full source with commentary, generated from the tree |

The pinned inputs themselves — `criteria/`, `spec/`, and zeta's criteria —
are deliberately not rendered on this site. They are the identity, so read
the bytes in the repository.
