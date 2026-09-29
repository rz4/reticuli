"""A small key = value configuration parser.

The format is one assignment per line:

    key = value

Surrounding whitespace around the key and the value is not part of either.
Blank lines carry no assignment and are skipped, so the empty document is
the empty dictionary. Later assignments to the same key win.
"""


def parse(text):
    """Read a key = value configuration text and return its dictionary."""
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"line is not an assignment: {line!r}")
        result[key.strip()] = value.strip()
    return result
