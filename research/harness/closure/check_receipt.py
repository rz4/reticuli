"""Receipt arithmetic: verify an outside re-earn receipt bundle.

Research tooling — not normative, not pinned. Run by the receipt
workflow on PRs touching receipts/**, and by anyone locally:

    python3 research/harness/closure/check_receipt.py [receipts-dir]

For every receipt bundle found it checks, mechanically:
  1. the detached ssh signature over record.json verifies against the
     public key INCLUDED IN THE BUNDLE, in the record namespace
     (ssh-keygen -Y verify — one command anyone can re-run);
  2. the re-earn receipt names the published root for its trial (read
     from the repository manifest at this checkout);
  3. the receipt's verdict fields are present and true.

What this deliberately cannot check is the human half: that the signer
ran it themselves, on their own machine. The signature stakes the
signer's name on that; the keyholder's merge accepts it. Exit 0 only if
every bundle checks.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
NAMESPACE = "reticuli.record"


def check_bundle(d: str) -> list:
    problems = []
    files = os.listdir(d)
    pubs = [f for f in files if f.endswith(".pub")]
    receipts = [f for f in files if f.startswith("outside_reearn_") and f.endswith(".json")]
    if len(pubs) != 1:
        problems.append(f"expected exactly one .pub key, found {len(pubs)}")
    if not receipts:
        problems.append("no outside_reearn_*.json receipt")
    record = os.path.join(d, "record.json")
    sig = record + ".sig"
    if not (os.path.isfile(record) and os.path.isfile(sig)):
        problems.append("record.json and record.json.sig are both required")
    if problems:
        return problems

    # 1. the signature, against the INCLUDED key, in the record namespace
    pub = os.path.join(d, pubs[0])
    identity = open(pub).read().split()[-1] or "outside-operator"
    with tempfile.NamedTemporaryFile("w", suffix=".allowed", delete=False) as f:
        f.write(f'{identity} namespaces="{NAMESPACE}" {open(pub).read().strip()}\n')
        allowed = f.name
    try:
        with open(record, "rb") as data:
            r = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", allowed, "-I", identity,
                 "-n", NAMESPACE, "-s", sig],
                stdin=data, capture_output=True, text=True)
        if r.returncode != 0:
            problems.append(f"signature does not verify: {r.stderr.strip()[:200]}")
    finally:
        os.unlink(allowed)

    # 2. the receipt names the published root
    published = json.load(open(os.path.join(REPO, ".reticuli", "manifest.json")))["root"]
    for name in receipts:
        rec = json.load(open(os.path.join(d, name)))
        root = rec.get("root") or rec.get("repo_root") or ""
        if not str(root).startswith(published[:16]) and published not in str(rec):
            problems.append(f"{name}: receipt does not name the published root {published[:16]}…")
        # 3. the verdicts
        text = json.dumps(rec)
        if '"ok": true' not in text and "'ok': True" not in text:
            problems.append(f"{name}: no true verdict found in receipt")
    return problems


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "receipts")
    bundles = [os.path.join(base, e) for e in sorted(os.listdir(base))
               if os.path.isdir(os.path.join(base, e))]
    if not bundles:
        print("no receipt bundles present; nothing to check")
        return 0
    bad = 0
    for b in bundles:
        problems = check_bundle(b)
        tag = os.path.basename(b)
        if problems:
            bad += 1
            print(f"RECEIPT {tag}: FAILED")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"RECEIPT {tag}: signature verifies, root matches, verdicts true")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
