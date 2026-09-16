# A claim whose producer is `make`

Root `b6649dca45f3a159798d4efc2be0735059175f506245309f4d097cd42068a616`.

**A producer does not have to be a language model.** A producer is any program
that regenerates a claim's generated outputs; here it is a compiler driven by
a Makefile. No API key, no network, no model — the same verification machinery
applied to an ordinary build.

```
pinned    Makefile, wordcount.c, check.sh, cases/input.txt, cases/expected.txt
generated wordcount          ← the compiled binary, outside the root
gate      sh check.sh        → OK
```

## The demonstration

Rebuild it in a clean workspace, twice, with different compiler settings:

```
$ ret rebuild examples/make --producer "make" --into /tmp/a
$ ret rebuild examples/make --producer "make CFLAGS=-O0" --into /tmp/b
```

The two binaries are genuinely different bytes:

```
binary -O2 : 37c9de06c8ac4e77…
binary -O0 : ed8a56b6e34a7b8e…
same bytes?: False
```

and both workspaces carry the identical root:

```
b6649dca45f3a159798d4efc2be0735059175f506245309f4d097cd42068a616
```

That is the whole idea, on a compiled artifact: **the identity is over what
was demanded and verified, not over what came out of the compiler.** Different
optimization levels, different compilers, different operating systems produce
different binaries that are all the same claim — while a one-byte change to
`cases/expected.txt` or to `check.sh` produces a different claim, immediately.

Reproducible-build projects work hard to make binaries bit-identical across
environments. This is the complementary move: stop requiring the bytes to
match, and pin the *criteria* instead, so that "did I get the same thing?"
becomes a hash comparison over the specification rather than over the output.

## The environment contract

```toml
requires = ["make", "cc"]
```

A host without a compiler cannot judge this claim. It does not report a
failure — it reports `environment`, which is a distinct verdict meaning *the
claim was not tested here*, never *the claim is wrong*.

## Try it

```
$ cd examples/make && make && sh check.sh && cat OK
ok

$ ret verify examples/make          # identity
$ ret audit  examples/make          # re-run the gate on the bytes present
```

The committed claim has no binary in it — `wordcount` is generated, so it is
absent until something produces it. That is normal: a claim can travel without
its implementation and regrow it on arrival.
