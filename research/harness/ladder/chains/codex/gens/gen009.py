"""Parse a small sectioned key/value document."""

import re


def _value(text):
    stripped = text.strip()
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return stripped


def parse(text):
    """Collect the first value for each case-insensitive qualified key."""
    result = {}
    section = ""

    for source_line in text.replace("\\\n", "").splitlines():
        line = source_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        separator = next((i for i, char in enumerate(line) if char in "=:"), None)
        if separator is None:
            continue

        name = line[:separator].strip().lower()
        key = f"{section}.{name}" if section else name
        if key not in result:
            result[key] = _value(line[separator + 1:])

    return result
