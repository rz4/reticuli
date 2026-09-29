"""A key-value line parser.

The text is a sequence of lines, one assignment per line:

    key = value

Surrounding whitespace around the key and the value is not part of
either. A value made entirely of digits is a number, and is returned as
an int rather than as text. When the same key is assigned more than
once, the last assignment is the one that survives. Blank lines carry no
assignment and are skipped, so empty text parses to an empty mapping.
"""


def parse(text):
    """Return the mapping described by ``text``."""
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"line is not an assignment: {line!r}")
        result[key.strip()] = _coerce(value.strip())
    return result


def _coerce(value):
    """Return ``value`` as an int when it is a number, else as text."""
    body = value[1:] if value[:1] in ("-", "+") else value
    if body.isdigit():
        return int(value)
    return value
