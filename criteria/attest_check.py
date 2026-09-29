"""Kernel-attest conformance gate — the record, the one parseable file.

A record's canonical bytes are the identity serialization verbatim (sorted keys,
default separators, non-ASCII escaped), so a record travels between kernels; its
digest is the sha256 of those bytes. The member set is closed — a malformed or
extended document is refused in band. Writes ATTEST_OK.

    python3 criteria/attest_check.py        (from the repository root)
"""
import hashlib
import json
import os
import sys

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import attest, core

DOC = {
    "record": 1,
    "name": "example",
    "root": "0" * 64,
    "build_digest": "1" * 64,
    "gates": [{"output": "V", "status": "ok", "sandbox": "none"}],
    "environment": {"platform": "linux", "machine": "x86_64", "runtime": "cpython-3"},
    "when": "2026-01-01T00:00:00Z",
}




# ==== seam block for attest_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- _kernel/attest.py: 12 seam names (7 value, 2 kind, 3 callable) ---
_SEAM__kernel_attest_VALUES = {
    '_RECORD_ENVIRONMENT': frozenset({'platform', 'runtime', 'machine'}),
    '_RECORD_GATE': frozenset({'status', 'sandbox', 'output'}),
    '_RECORD_MEMBERS': frozenset({'when', 'cost', 'gates', 'producer', 'environment', 'name', 'root', 'record', 'build_digest', 'tool'}),
    '_RECORD_PRODUCER': frozenset({'blind', 'model', 'cutoff', 'vendor'}),
    '_RECORD_REQUIRED': frozenset({'build_digest', 'when', 'environment', 'record', 'name', 'root', 'gates'}),
    '_RECORD_SANDBOXES': frozenset({'none', 'seatbelt', 'inherited', 'bubblewrap'}),
    '_RECORD_STATUSES': frozenset({'timeout', 'ok', 'environment', 'failed', 'mismatch'}),
}
_SEAM__kernel_attest_KINDS = {'_RECORD_HEX': 'Pattern', '_RECORD_WHEN': 'Pattern'}
_SEAM__kernel_attest_CALLABLES = ('record_digest', 'record_read', 'record_signer')

def _seam() -> None:
    from reticuli._kernel import attest as _m__kernel_attest
    for _n, _v in _SEAM__kernel_attest_VALUES.items():
        assert getattr(_m__kernel_attest, _n) == _v, f'_kernel/attest.py seam {_n} changed'
    for _n in _SEAM__kernel_attest_KINDS:
        assert hasattr(_m__kernel_attest, _n), f'_kernel/attest.py must export {_n}'
    for _n in _SEAM__kernel_attest_CALLABLES:
        assert callable(getattr(_m__kernel_attest, _n, None)), f'_kernel/attest.py must export callable {_n}'


def battery() -> None:
    _seam()
    # a well-formed record validates, and its canonical bytes are the identity
    # serialization verbatim, deterministic, with its digest the sha256 of them
    attest.record_validate(DOC)
    canon = attest.record_canonical(DOC)
    assert canon == json.dumps(DOC, sort_keys=True).encode("utf-8"), \
        "canonical bytes are sorted-key JSON, default separators"
    assert attest.record_canonical(DOC) == canon, "canonical bytes are deterministic"
    assert attest.record_digest(DOC) == hashlib.sha256(canon).hexdigest(), \
        "the digest is the sha256 of the canonical bytes"

    # the member set is closed and required members are enforced, in band
    for bad in (
        "not a dict",
        {**DOC, "surprise": 1},                 # unknown member
        {k: v for k, v in DOC.items() if k != "root"},   # missing member
        {**DOC, "root": "nothex"},              # bad hex
        {**DOC, "record": 99},                  # a version from the future
    ):
        try:
            attest.record_validate(bad)
        except core.ClaimError:
            pass
        else:
            raise AssertionError(f"a malformed record must refuse: {bad!r:.60}")


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("ATTEST_OK", "w", encoding="utf-8") as f:
            f.write("attest-ok\n")
    print("attest-ok")
