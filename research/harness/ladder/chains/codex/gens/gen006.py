"""Read key-value pairs from a document with optional sections."""

import re


_DELIMITER = re.compile(r"[=:]")
_INTEGER = re.compile(r"-?\d+")


def _meaningful_lines(text):
    for source_line in text.replace("\\\n", "").splitlines():
        line = source_line.strip()
        if line and not line.startswith("#"):
            yield line


def parse(text):
    """Return the first value found for each case-insensitive key."""
    values = {}
    section = ""

    for line in _meaningful_lines(text):
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        parts = _DELIMITER.split(line, maxsplit=1)
        if len(parts) != 2:
            continue

        name, raw_value = parts
        name = name.strip().lower()
        full_name = f"{section}.{name}" if section else name
        if full_name in values:
            continue

        value = raw_value.strip()
        values[full_name] = int(value) if _INTEGER.fullmatch(value) else value

    return values
