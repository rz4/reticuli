"""The record reader's surface, pinned where the population was silent.

*A criterion. Its bytes are inside the repository root.*

`spec/record.md` already carries the lesson this file enforces:

    This paragraph exists because it was missing. On 2026-10-14 four
    implementations that had all earned the same root were asked to
    canonicalize a document that was not a JSON object: two produced bytes
    and a digest, two refused. The root could not say which was correct,
    because no criterion tested it.

The prose was written. The criterion was not, so the same surface stayed
untested and the same thing happened again.

On 2026-11-05 `zeta` swept this reader across a four-member population --
the authored tree plus three second-generation reconstructions, each regrown
from the `f419e409` blind boundary by a regrown tool -- on six pressures.
Five came back as agreements and one as a split
(`zeta/queue/descendants/`, entries `465a93b1`, `8946accb`, `b3bfb3c8`,
`b424773d`, `fc45849a`, and the split `629cc5c6`).

The five agreements are pinned here because an agreement nothing tests is a
silence waiting for a reconstruction to fill differently. Pinning them
evicts nobody: every current member already behaves this way.

THE SPLIT IS RULED HERE TOO, and in the direction the reconstructions took.
On `record_validate` of a well-formed v2 record the three children returned
the validated document and the authored tree alone returned None; widening
the measurement to both first-generation fathers, which the registry had
already retired and so were not in the sweep, makes it five reconstructions
to one (measured 2026-11-06 across all six implementations). The reader
family is otherwise uniform -- `record_canonical` returns bytes,
`record_digest` returns a digest, `record_read` returns the document -- and a
validator that returns nothing is the only member of it that cannot be
chained. Returning the document breaks no caller, because no caller can
consume None.
"""
import json
import os
import sys

# Resolved RELATIVE to the working directory, as every other criterion does.
# The substituted gate runs in a room whose src/ holds the implementation
# under test, so an absolute path derived from __file__ would quietly test
# the shipped tree instead -- which is how the first draft of this file
# reported two reconstructions passing a check they fail.
SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)

from reticuli._kernel import attest

#: a well-formed version-2 record, the shape every entry point must accept
WELL_FORMED = {
    "build_digest": "a" * 64,
    "claim": {},
    "environment": {"machine": "arm64", "platform": "darwin",
                    "runtime": "3.14"},
    "gates": [{"output": "EXAMPLE_OK", "sandbox": "seatbelt", "status": "ok"}],
    "name": "example",
    "record": 2,
    "root": "a" * 64,
    "when": "2026-10-14T00:00:00Z",
}

#: documents that are not records, which every entry point must refuse
NOT_A_RECORD = ([1, 2], "a string", 7, None, True)


def _refuses(fn, doc) -> bool:
    try:
        fn(doc)
    except Exception:                      # noqa: BLE001 -- any refusal counts
        return True
    return False


def battery() -> None:
    # ---- the ruling: record_validate returns the document it validated ----
    got = attest.record_validate(dict(WELL_FORMED))
    assert isinstance(got, dict), (
        "record_validate must return the validated document, not "
        f"{type(got).__name__}. The reader family is uniform -- canonical "
        "returns bytes, digest returns a digest, read returns the document "
        "-- and five independent reconstructions returned the document here "
        "while the authored tree returned None (zeta, 2026-11-05).")
    assert got == WELL_FORMED, \
        "record_validate must return the document unchanged, not a copy it edited"

    # ---- the contractions: validation is a precondition of the FORMAT ----
    # spec/record.md: "Every entry point that consumes a document refuses
    # what a reader refuses, and that includes canonicalizing and digesting."
    for doc in NOT_A_RECORD:
        for name in ("record_validate", "record_canonical", "record_digest"):
            fn = getattr(attest, name)
            assert _refuses(fn, doc), (
                f"{name} accepted {doc!r}, which is not a record. A digest is "
                "how a record is cited; an implementation that will digest a "
                "non-record manufactures a citable value standing for "
                "something this format does not admit.")

    # ---- the contractions: a well-formed v2 record is accepted by all ----
    canonical = attest.record_canonical(dict(WELL_FORMED))
    assert isinstance(canonical, bytes) and canonical, \
        "record_canonical must return the canonical bytes of a valid record"
    assert json.loads(canonical.decode("utf-8")) == WELL_FORMED, \
        "the canonical bytes must round-trip to the same document"

    digest = attest.record_digest(dict(WELL_FORMED))
    assert isinstance(digest, str) and len(digest) == 64, \
        "record_digest must return a 64-character hex digest"
    assert digest == attest.record_digest(dict(WELL_FORMED)), \
        "record_digest must be deterministic"

    # ---- the second ruling: [record] is not a table this reader accepts ----
    # The filename legacy IS an obligation (`claim.toml` stays readable, and
    # the kernel carries LEGACY_RECIPE for it); the TABLE legacy never was.
    # They are not symmetric: the filename is outside the root preimage, the
    # table is inside it, so a reader accepting both spellings would compute
    # one root for two different documents.
    #
    # This division is NOT one the sweep found -- no pressure in
    # `zeta/queue/descendants/` probes the recipe reader, which is its own
    # gap. It was found by hand and then measured 2026-11-06 across all six
    # implementations. Two of the five reconstructions read an annotation
    # beside the filename rule and implemented the symmetry anyway, and WHICH
    # two is the finding: the division is clean by producer. Both
    # codex-produced trees accept `[record]`; none of the three
    # claude-produced trees do, and neither does the authored tree.
    # A 2-of-5 minority would be a weak signal for pinning. A minority that
    # is exactly one producer's output is not a minority at all -- it is one
    # reading of ambiguous prose, held by however many trees that producer
    # happens to have made. Sampling it more would not have broken the tie,
    # which is why the prose is being fixed and the obligation made testable
    # here rather than left inferable from a comment.
    import tempfile
    from reticuli._kernel import recipe as _recipe
    legacy = tempfile.mkdtemp(prefix="legacy-record-")
    with open(os.path.join(legacy, "reticuli.toml"), "w") as f:
        f.write('[record]\nname = "legacy"\nformat = 4\n\n'
                '[[step]]\nkind = "gate"\noutput = "OK"\n'
                'class = "validated"\nrun = "printf ok > OK"\n')
    with open(os.path.join(legacy, "OK"), "w") as f:
        f.write("ok")
    try:
        _recipe.load_recipe(legacy)
    except Exception:
        pass
    else:
        raise AssertionError(
            "a recipe whose only table is [record] was accepted. [claim] is "
            "the only spelling; the table name is inside the root preimage, "
            "so reading both would give one root for two documents.")

    with open("RECORD_SURFACE_OK", "w") as f:
        f.write("record-surface-ok\n")
    print("record-surface-ok")


if __name__ == "__main__":
    battery()
