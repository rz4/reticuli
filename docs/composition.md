# Composing claims

*Informational — an operational guide. The normative contract is in [`spec/`](https://github.com/rz4/reticuli/tree/main/spec/).*

A claim can depend on another claim. The dependency is recorded by root, so
the dependent names a specific identity rather than a directory that might
change under it.

Every command on this page was run against the shipped `examples/make`
before being written down.

## The two steps

Pulling registers the dependency and copies its outputs into your workspace.
Packing then declares it as a component.

```console
$ ret pull ../dep                 # register and materialize the dependency
$ ret pack . --name wcuser \
      --generated wordcount \
      --input cases.txt check2.sh \
      --gate 'sh check2.sh' --output CONSUMER_OK \
      --component ../dep
packed  d2ca273dbcfd...
```

Then the composite holds end to end:

```console
$ ret verify .                    # exit 0
$ ret audit .                     # exit 0
$ ret audit . -v | grep layers
layers = "1/1 earned"
```

`ret status . --tree` draws the dependency graph, and `ret audit --shallow`
judges this claim alone, skipping the component chain.

## Four things that will catch you

**The component's output must also appear in `--generated`.** Pulling puts
`wordcount` in your directory, but until you name it, `pack` refuses with
`component outputs not among generated files: ['wordcount']`. The dependency
supplies the bytes; your recipe still has to say the file is generated rather
than pinned.

**`--input` takes several values; repeating the flag silently keeps only the
last.** Write `--input cases.txt check2.sh`. Writing `--input cases.txt
--input check2.sh` seals a claim whose recipe pins only `check2.sh`, and it
will verify perfectly and then fail its first cold audit with
`cases.txt: No such file or directory`. `pack` prints a note naming any file
left in no class — read it.

**Pull materializes into your top-level directory, so names can collide.**
The dependency's verdict file and outputs land beside your own. If both
claims write `OK`, rename yours; the example above uses `CONSUMER_OK`.

**Pull drops the executable bit.** A binary that arrives through `pull` is
`rw-r--r--`, so a gate that runs it needs a `chmod +x` first. This is the
same defect as the one
[export and import have](how-do-i.md#regrow-something), at a second site.

## What happens when the dependency's root moves

Nothing, automatically. Your claim keeps its own root and keeps verifying and
auditing against the frozen copy it took at pull time. A pull copies **by
value**: the drawer copy and the manifest link freeze the component as it
stood, and the component's name is the mutable pointer while its root is the
immutable value the link records.

To find out, re-walk deliberately. Run `ret pull` with no arguments from the
directory whose subdirectories are the claims:

```console
$ cd ..            # the directory holding both dep/ and consumer/
$ ret pull
```

Two outcomes, and both are informative:

- The dependency's new bytes still satisfy your gate. The walk re-pulls them,
  re-earns your gate warm, and advances the component root recorded in your
  manifest. **Your own root does not move** — supplied files are generated,
  and so sit outside it.
- The new bytes break your gate. The walk stops at the first refusing layer
  and names it. Your claim's root still does not move, and `verify` still
  reports `fresh`. The composition genuinely broke, and the refusal says
  where.

That second case is the one worth understanding, because it is the whole
argument for composing by root rather than by directory: a dependency cannot
change what your claim promises without someone running the walk and seeing
the refusal.

!!! warning "A refused walk can leave the drawer ahead of the link"

    After a refusal, the inner drawer copy may have already advanced to the
    dependency's new root while the outer link still records the old one.
    `ret status --tree` then reports the layer as `(missing from the
    registry)` and `ret audit` reports it `unresolved`. The tools surface
    the inconsistency rather than hiding it, but the state is real: re-pull
    the dependency explicitly, or restore it to the root your link names.

## Passing a gate is not being substitutable

The thing composition exists to make visible. An implementation that passes
its own criteria can still be one a consumer cannot live with, because the
criteria were silent about something the consumer relied on.

This repository measured it: six blind rebuilds of a parser, from two model
families, all passed the parser's gate, all differed by bytes, and all six
broke the consumer identically. Tightening the parser's criteria by two lines
fixed all six. The write-up is in
[`findings/substitution.md`](https://github.com/rz4/reticuli/blob/main/findings/substitution.md).

The practical consequence: audit the consumer, not just the dependency. A
green gate on a component says nothing about whether swapping it is safe.

## Related

`[claim] assembles` is the format-5 recipe key for a claim whose gates judge
the composition of other claims' shipped outputs, with each member held to
its declared root. See [compatibility](compatibility.md) for what format 5
adds; the rules are in `spec/claim-format.md`.
