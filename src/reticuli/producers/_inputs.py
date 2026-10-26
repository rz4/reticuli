"""Which pinned inputs a producer should READ, and which are merely PRESENT.

The producer contract tells a model to read every pinned input in full. That
is right for a check file and catastrophic for data: a claim pinning a 3MB
MNIST subset and a 916KB checkpoint sent one producer into megabytes of
binary, where it spent 794,891 tokens and wrote no implementation at all
(claims/LOG.md R16 in the apeiron workspace).

Shared by every adapter on purpose. The same prompt line exists in each one,
so the same defect existed in each one, and a fix applied to a single
adapter would have left the others to rediscover it.

Nothing about identity changes here. Both kinds are pinned, both are inside
the root, both are present in the room. The only question is whether the
prompt asks the model to read the bytes.
"""
import os

#: Above this, a text input is being used as data rather than read as
#: specification. The largest criteria file in the APEIRON ladder is 18KB.
READABLE_BYTES = 256 * 1024


def is_readable(path: str) -> bool:
    """Is this input text a model should read, or data it should just use?"""
    try:
        with open(path, "rb") as handle:
            head = handle.read(8192)
        if b"\x00" in head:
            return False                  # binary: pickles, archives, idx
        head.decode("utf-8")
        return os.path.getsize(path) <= READABLE_BYTES
    except (OSError, UnicodeDecodeError):
        return False


def split(paths):
    """(criteria to read, data to leave alone), order preserved."""
    read, data = [], []
    for path in paths:
        (read if is_readable(path) else data).append(path)
    return read, data


def note(data_inputs) -> str:
    """The prompt line that keeps a producer out of the data."""
    if not data_inputs:
        return ""
    return (f"\n   These inputs are DATA, already present and used by the "
            f"gate. Do NOT read their bytes -- they are large and/or binary, "
            f"and reading them will exhaust your context without telling you "
            f"anything: {data_inputs}")
