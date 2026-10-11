# Outside re-earn receipts — condition 5, as pull requests

A stranger who has re-earned a trial (see ../outside.md) submits their
receipt HERE, as a pull request, instead of email:

    receipts/<your-handle>/
        outside_reearn_<FAMILY>_<TAG>.json   # written by outside_reearn.py
        record.json                          # ret record . -o record.json
        record.json.sig                      # ret record's detached signature
        <your-key>.pub                       # the ssh public key that signed

The receipt-check workflow verifies, mechanically, on the PR: the
detached signature against YOUR included public key (anyone can re-run
it locally: ssh-keygen -Y verify in the record namespace), the root in
the receipt against the published root, and the verdict fields. What it
cannot and does not verify is the one thing only you supply: that YOU
ran it, on YOUR machine, under an account the authors never touched.
Your signature stakes that; the keyholder's MERGE is the
countersignature — acceptance of the receipt happens in public, on a
ledger neither party administers, and the closure ledger's "outside"
tick cites the merged PR.

The fully-offline path (email, air gap) remains open and equally valid;
this directory is the streamlined road, not the only one.
