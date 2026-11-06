# The outside re-earn

*A protocol for one person who is not us. About fifteen minutes, most of it
waiting for a clone. Nothing here needs trust in this project, which is the
point.*

## What we are asking

Reticuli identifies software by a hash over its acceptance criteria. The
implementation is deliberately outside that hash, so the claim is that *any*
implementation passing the criteria is the same software — including ones a
machine wrote. We have tested that claim a lot: implementations regrown by
two model families, three generations deep, all landing one identity.

Every one of those runs happened on our machines, under our accounts, by us.

That is the weakness. Our CI already re-runs the gate on hardware we do not
own, but it runs *our* workflow, so it is still our act. The verdict has
never been produced by someone who could have deviated, inspected anything,
or simply lied about the result and been believed.

**Your job is to re-earn the central verdict on a machine we have never
touched, and to sign what you saw.** It is the one piece of evidence we
cannot manufacture.

## What you need

A machine we did not administer, Python 3.11 or newer, git, and `ssh-keygen`.
No API key. No model access. No account with anyone. The work is a hash
check and a test run.

## The protocol

### 1. Get the code

```console
$ git clone https://github.com/rz4/reticuli
$ cd reticuli
$ python3 -m venv .venv && .venv/bin/pip install -e . -q
```

No commit pin is needed. Step 2 checks the root, and the root is the
identity you are verifying — not any git hash.

### 2. Check the identity

```console
$ .venv/bin/ret verify .
$ echo $?
0
```

This recomputes the hash over the criteria, the specification and the recipe,
and compares it with the sealed manifest. It should print nothing and exit 0,
because a passing check says nothing here.

The root you are verifying is the one recorded in
`.reticuli/manifest.json` in the clone you just made — this document
deliberately does not repeat it. It was written out twice before and was
wrong both times within a day, because the boundary moves and prose does
not. Read it from the manifest:

```console
$ python3 -c "import json;print(json.load(open('.reticuli/manifest.json'))['root'])"
```

If `verify` prints anything at all, stop: the code you are holding does not
hash to the root it carries, and that is worth telling us about.

### 3. Re-earn the verdict

```console
$ .venv/bin/python research/harness/closure/outside_reearn.py \
      --lineage claude --run r36
```

This substitutes all 37 modules of a machine-written implementation for the
ones that ship, and runs the repository's own full acceptance gate against
the result, sandboxed, on your machine. Expect about **80 seconds**:

```
verify: ok=True root=241a20668f19af1…
substituted gate: 37 modules from the claude-r36 tree
substituted gate: ok=True (77.2s, quarantine=seatbelt)
RE-EARNED -> research/harness/closure/outside_reearn_claude_r36.json
```

**Only `claude --run r36` re-earns at the current boundary.** The codex
trial `r34` is in the tree and does NOT: the 2026-11-06 transition pinned
that `[record]` is not a table a reader accepts, and r34 accepts it, so the
substituted gate refuses it by name. That is the eviction working, not a
broken trial, and r34 stays on disk as a control.

On a host without a sandbox the run still works and reports
`quarantine=none`. That is recorded rather than hidden, and it does not
invalidate anything.

### 4. Sign what you saw

```console
$ .venv/bin/ret record . -o record.json --key ~/.ssh/id_ed25519
```

This writes an execution record of the repository as it stands on your
machine and signs it with **your** key. We never see your private key, and
the signature is what makes the receipt yours rather than ours.

### 5. Send the receipt

```console
$ mkdir -p research/harness/closure/receipts/<your-handle>
$ cp research/harness/closure/outside_reearn_claude_r36.json \
     record.json record.json.sig ~/.ssh/id_ed25519.pub \
     research/harness/closure/receipts/<your-handle>/
$ git checkout -b outside-reearn-<your-handle>
$ git add research/harness/closure/receipts/<your-handle>
$ git commit -m "Outside re-earn receipt: claude r36"
$ git push <your-fork> outside-reearn-<your-handle>
```

Then open the pull request. No GitHub account, or an air-gapped machine?
Email the same four files through any channel you trust. The pull request is
the convenient road, not the only one.

## What happens next

A workflow on your pull request checks, in public, that your signature
verifies against the public key in your own bundle, that your receipt names
the published root, and that the verdicts are what they claim. Anyone can
re-run that check with a single `ssh-keygen -Y verify`; our CI is a
convenience and your signature is the substance.

When the keyholder merges it, the closure ledger gains the tick it has been
missing, citing your pull request and your name.

## What your run establishes, and what it does not

It establishes that the substituted gate passes on hardware and under an
account outside this project, witnessed by someone who could have reported
otherwise.

It does not establish that the code is correct, that the criteria are
well-chosen, or that the model which wrote the implementation never saw ours.
Those are different questions, and
[`docs/threat-model.md`](../../../docs/threat-model.md) is candid about all
three.

It is also not a rebuild. You are not asking a model to regenerate anything —
that work is already done and frozen in the tree you are judging. You are
checking that the judgment survives leaving our building.

## If it fails

Tell us, and keep the output. A failure here is more interesting than a pass:
it would mean the verdict depends on something about our environment that we
have not declared, which is exactly the defect this protocol exists to find.
Open an issue with the output of step 3, your platform, and your Python
version.
