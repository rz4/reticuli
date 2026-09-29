"""Read simple key/value documents with optional section headings."""

import re


_SEPARATOR = re.compile(r"[=:]")
_INTEGER = re.compile(r"-?\d+\Z")


def _parse_value(raw):
    value = raw.strip()
    return int(value) if _INTEGER.fullmatch(value) else value


def parse(text):
    """Return the first entry for each case-insensitive, section-qualified key."""
    entries = {}
    section = ""

    for raw_line in text.replace("\\\n", "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        parts = _SEPARATOR.split(line, maxsplit=1)
        if len(parts) == 1:
            continue

        name, raw_value = parts
        key = name.strip().lower()
        if section:
            key = f"{section}.{key}"

        if key not in entries:
            entries[key] = _parse_value(raw_value)

    return entries
