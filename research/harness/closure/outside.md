# The outside re-earn — condition 5 of the closure bar

*The bar (docs/transitions.md) requires that at least one of the three
qualifying trials is re-earned on a machine and operator OUTSIDE the
generation environment. This is the protocol. The operator needs: a
machine the author has never administered, python >= 3.11, ssh-keygen,
git, roughly 10–40 minutes of wall clock (minutes for a codex-tree leg), and no trust in us.*

## What you are checking

This repository's identity is a hash over its acceptance criteria —
the implementation is deliberately outside it. A machine-written
implementation (the "trial tree", committed under
`research/harness/succession/lineages-<TAG>/`) is claimed to be a
member of that identity: substitute its 37 modules for `src/reticuli/`
and the repository's own gate re-earns. You are re-earning that
verdict yourself, on hardware and under an account we cannot have
staged.

## The steps

    git clone https://github.com/rz4/reticuli
    cd reticuli
    git checkout <COMMIT>          # the frozen root's commit, named in
                                   # the ledger row for the trial
    python3 -m venv .venv && .venv/bin/pip install -e . -q

    # 1. the repository verifies: the root is what the ledger says
    .venv/bin/ret verify .

    # 2. the outside re-earn (the long step, ~1 h):
    .venv/bin/python research/harness/closure/outside_reearn.py \
        --lineage <FAMILY> --run <TAG>

    # 3. seal and sign what you saw (uses your ssh key):
    .venv/bin/ret record . -o outside-reearn-record.json
    .venv/bin/ret record . --key ~/.ssh/id_ed25519 --as "<you>" \
        -o outside-reearn-record.json

Send back `outside-reearn-record.json` and
`research/harness/closure/outside_reearn_<FAMILY>_<TAG>.json` (the
script writes it), plus your public key through any channel you
already trust. We verify the signature; the ledger row gains its
"outside" tick with your name on it.

Optional stronger leg, if you have a codex or claude CLI configured
with YOUR OWN account: add `--recursive` to step 2 and the script also
drives the trial tree, through its own command line, to rebuild a
claim from a blind room with your producer — the recursive step,
re-earned outside.

## What a refusal means

If step 1 fails, the clone does not match the published root — stop,
tell us, trust nothing. If step 2 fails, you have found either a
host-contract gap (the record will show an `environment` or
`quarantine` word worth sending us) or a genuine refusal — both are
findings, and a finding from an outside machine is worth more to this
project than a pass. Send the JSON either way.

## Notes for the operator

- Linux is welcome: install `bubblewrap` if you can, so gates run
  jailed; without it the record honestly says `quarantine = "none"`.
- Nothing here needs our credentials, keys, or accounts. The
  non-optional path needs no model access at all.
- Expect the re-earn to be CPU-bound for ~45–70 minutes; the declared
  ceiling is an hour per gate run on the repository claim.

## Current values (2026-10-11 — the final set)

    COMMIT   530cdd9        # contains all three sealed trials
    ROOT     900b6594d4ade4d51f1331054437fa311f5f7a73153a722781d4fb701192cc0f

The three qualifying trials, any ONE of which satisfies condition 5:

    FAMILY=codex   TAG=r23    # codex-authored
    FAMILY=claude  TAG=r24    # claude-authored
    FAMILY=codex   TAG=g2     # the grandchild: codex-authored,
                              # orchestrated end-to-end by r24's
                              # regrown kernel (the strongest leg)

Each trial also exists as a SEALED CLAIM whose identity you can verify
anywhere in seconds (pure hash arithmetic, no execution):

    .venv/bin/ret verify research/harness/closure/trialclaims/r23-codex
    .venv/bin/ret verify research/harness/closure/trialclaims/r24-claude
    .venv/bin/ret verify research/harness/closure/trialclaims/g2-codex

(The sealed claims' GATES shell into the generating checkout by
recorded path, so re-earning their verdicts on your machine goes
through outside_reearn.py above — same judgments, your hardware —
rather than ret audit on the claim directory.)

## The pull-request road (streamlined; the email road stays open)

Instead of sending files, stake the receipt in public:

    # after outside_reearn.py and the signed record (steps above):
    mkdir -p research/harness/closure/receipts/<your-handle>
    cp outside_reearn_<FAMILY>_<TAG>.json record.json record.json.sig \
       ~/.ssh/id_ed25519.pub \
       research/harness/closure/receipts/<your-handle>/
    git checkout -b outside-reearn-<your-handle>
    git add research/harness/closure/receipts/<your-handle>
    git commit -m "Outside re-earn receipt: <FAMILY> <TAG>"
    # push to your fork, open a pull request

The `receipt` workflow verifies your signature against the public key
in your own bundle, the root against the published one, and the
verdicts — mechanically, in public, re-runnable by anyone with
ssh-keygen. The keyholder's MERGE is the acceptance: condition 5's
countersignature, timestamped on a ledger neither party administers.

Division of labor, stated honestly: GitHub's CI already re-earns the
gate on six platform/Python combinations at every push — the outside
MACHINE half of condition 5 is continuously satisfied. What no workflow
of ours can supply is the outside OPERATOR: you, typing the commands on
hardware and an account the authors never touched, free to deviate and
inspect, your key staking your name. That is the half this protocol
exists for, and the one step that must never be streamlined into a
button of ours. (Optional corroboration: enable Actions on your fork so
the re-earn also runs under YOUR account on GitHub's machines.)
