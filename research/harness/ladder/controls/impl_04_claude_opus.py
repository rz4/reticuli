"""A small key = value configuration reader.

One assignment per line. The key is everything before the first `=`, the
value is the rest of the line; both have surrounding spaces removed. Blank
lines are ignored, so the empty document gives the empty dictionary.
"""


def parse(text: str) -> dict:
    """Read `text` as key = value lines and return them as a dictionary."""
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"line is not an assignment: {line!r}")
        result[key.strip()] = value.strip()
    return result
