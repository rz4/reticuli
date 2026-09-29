"""Read sectioned key/value text into a flat mapping."""

import re


_SEPARATOR = re.compile(r"[=:]")
_INTEGER = re.compile(r"-?\d+")


def parse(text):
    """Keep the first value for each case-insensitive, section-qualified key."""
    entries = {}
    prefix = ""

    for source_line in text.replace("\\\n", "").splitlines():
        line = source_line.strip()
        if not line or line[0] == "#":
            continue

        if line[0] == "[" and line[-1] == "]":
            prefix = line[1:-1].strip().lower()
            continue

        separator = _SEPARATOR.search(line)
        if separator is None:
            continue

        key = line[: separator.start()].strip().lower()
        if prefix:
            key = f"{prefix}.{key}"
        if key in entries:
            continue

        value = line[separator.end() :].strip()
        entries[key] = int(value) if _INTEGER.fullmatch(value) else value

    return entries
