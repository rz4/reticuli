# The reticuli manual

Reticuli identifies software by what it has to do. The name — the **root** —
is a SHA-256 over the acceptance criteria, the specification, and the build
recipe. The implementation is excluded from that hash, so every
implementation passing the acceptance gate is a member of the class the root
names, and changing one byte of a criterion gives a different name.

This manual teaches how to use it. If you want the evidence for what it has
been measured to do, that lives in
[`findings/`](https://github.com/rz4/reticuli/tree/main/findings) in the
repository, next to the data those claims are about.

## Install

```console
$ git clone https://github.com/rz4/reticuli && cd reticuli
$ pip install .
$ ret --help
```

Standard library only, on macOS or Linux, since gates run under
`sandbox-exec` or `bwrap`.

## Start here

[**The quickstart**](quickstart.md) runs the whole loop against a shipped
example in about ten minutes, with no API key and no model. Every block on
that page is a real captured invocation, including the refusals: a tampered
pinned byte, a damaged implementation, and what each instrument says about
them.

After it, [how a claim works](process.md) is the mechanism underneath — six
stages, the three-machine test, and the rule that only a human signature can
change an obligation. The [glossary](glossary.md) is there when a word is
doing more work than it looks like.

## Then pick what you are doing

<div class="grid cards" markdown>

-   **Making a claim**

    You have code and tests and want the tests to become the name.

    [Make a claim](make-a-claim.md) · [Capturing work](capturing.md) ·
    [Writing criteria](criteria.md)

-   **Receiving a claim**

    Someone handed you a directory and said their code works.

    [Receiving a claim](receiving.md) ·
    [What a claim proves](threat-model.md) · [GitHub and CI](github.md)

-   **Rebuilding with agents**

    Regrowing an implementation from the criteria alone.

    [Working with agents](agents.md) · [Writing a producer](producers.md)

-   **Changing a claim**

    The criteria were wrong, or too weak, and have to move.

    [Transitions](transitions.md) · [Releasing](releasing.md) ·
    [Zeta internals](zeta.md)

</div>

In a hurry, [**How do I…?**](how-do-i.md) routes the common jobs straight to
the right page and command.

## Two verbs, and why they are not one

The distinction the whole tool is built around, worth getting straight before
anything else:

| | `ret verify` | `ret audit` |
|---|---|---|
| asks | is this the thing I was given? | does it still earn its verdict here? |
| does | recomputes the root and compares | re-runs every gate, cold, in a sandbox |
| costs | milliseconds, executes nothing | minutes |
| answers about | identity | membership |

A claim can verify perfectly and fail to audit, and a passing gate on a claim
whose identity is broken earns nothing at all. Verdicts are re-earned rather
than inherited, which is what lets you check a claim while trusting no one —
not the author, not the producer, and not the machine it was made on.

!!! warning "Pre-release, and the format has already moved"

    Five claim formats exist, and the kernel's own claim has changed identity
    twice, both times deliberately and both recorded. Do not build something
    on this that cannot tolerate a root changing. The stability promise that
    *does* stand as of v2.0.0 is in [compatibility](compatibility.md).

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

The pinned inputs themselves — `criteria/`, `spec/`, and zeta's criteria —
are deliberately not rendered on this site. They are the identity, so read
the bytes in the repository.
