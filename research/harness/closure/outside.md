# The outside re-earn — a 30-minute protocol for one stranger

## Purpose

This repository's identity is a hash over its acceptance criteria; the
implementation is deliberately outside it. We claim that machine-written
implementations are true members of that identity: substitute their
modules for ours and the repository's own gate passes again. Every piece
of evidence for that claim was produced on our machines, by us. **Your
job is to reproduce the central verdict on hardware and under an account
we have never touched, and to sign what you saw.** Your run is the one
piece of evidence we cannot fake.

You need: a machine we never administered, python ≥ 3.11, git,
ssh-keygen, no trust in us, and about 30 minutes.

## Method

**Step 1 — get the frozen code.**

    git clone https://github.com/rz4/reticuli
    cd reticuli
    python3 -m venv .venv && .venv/bin/pip install -e . -q

(No commit pin needed: step 2 checks the ROOT, and the root — not any
git hash — is the identity you are verifying. If main has moved past
root `900b6594d4ad…` by the time you run this, use
`git checkout 128bef5`, a commit sealed at that root.)

**Step 2 — check the identity.** Confirms the code you hold hashes to
the published root (`900b6594d4ad…`).

    .venv/bin/ret verify .

Expected: **no output, exit code 0** (a passing check says nothing;
`echo $?` to see the 0). Any drift prints loudly and you stop here.

**Step 3 — the re-earn.** This substitutes all 37 modules of a
machine-written implementation into the repository's claim and runs the
repository's own full gate against it, sandboxed, on your machine.

    .venv/bin/python research/harness/closure/outside_reearn.py \
        --lineage codex --run g2

(`--run g2` is the strongest trial — the "grandchild" implementation.
`--lineage codex --run r23` or `--lineage claude --run r24` are the
other two; any one suffices.)

Expected (about 2 minutes for g2 or r23, up to ~30 for r24):

    verify: ok=True root=900b6594d4ade4d5…
    substituted gate: ok=True (…s, quarantine=…)
    RE-EARNED -> research/harness/closure/outside_reearn_codex_g2.json

**Step 4 — sign what you saw.** Writes an execution record of the
repository as it stands on your machine and signs it with YOUR key.

    .venv/bin/ret record . -o record.json --key ~/.ssh/id_ed25519

Expected: `record.json` and `record.json.sig` appear.

**Step 5 — submit the receipt as a pull request.**

    mkdir -p research/harness/closure/receipts/<your-handle>
    cp research/harness/closure/outside_reearn_codex_g2.json \
       record.json record.json.sig ~/.ssh/id_ed25519.pub \
       research/harness/closure/receipts/<your-handle>/
    git checkout -b outside-reearn-<your-handle>
    git add research/harness/closure/receipts/<your-handle>
    git commit -m "Outside re-earn receipt: codex g2"
    git push <your-fork> outside-reearn-<your-handle>
    # open the pull request on GitHub

(No GitHub account, or air-gapped? Email the same four files plus your
public key through any channel you trust. The PR road is the
streamlined one, not the only one.)

## Expected result

On your pull request, the `receipt` workflow verifies — mechanically, in
public — that your signature checks against the public key in your own
bundle, that your receipt names the published root, and that the
verdicts are true. (Anyone can re-run that check with one `ssh-keygen -Y
verify`; our CI is convenience, your signature is the substance.) The
keyholder then merges: that merge is the public acceptance of your
receipt, and the project's closure ledger gains its final tick, citing
your PR and your name.

What your run proves that nothing else can: GitHub's CI already re-runs
our gate on machines we don't own — but it runs *our* workflow, so it is
our act. You are the first *operator* outside the loop: you typed the
commands, you could have deviated or inspected anything, and your key
stakes your name on what you saw. That is the experiment's last
unfalsifiable-by-us data point. Thank you.

---
*Optional extras, not required: enable Actions on your fork so the
re-earn also runs under your account on GitHub's machines
(corroboration); or, if you have your own codex/claude CLI account, add
`--recursive` to step 3 and the machine-written tool will also rebuild a
claim from a blind room with your producer — the recursive step,
re-earned outside.*
