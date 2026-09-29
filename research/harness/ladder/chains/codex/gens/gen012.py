"""Read sectioned key/value text into a dictionary."""

import re


_SEPARATOR = re.compile(r"[=:]")
_INTEGER = re.compile(r"-?\d+")


def _meaningful_lines(text):
    """Yield trimmed lines after joining backslash-newline continuations."""
    for raw in text.replace("\\\n", "").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            yield line


def parse(text):
    """Keep the first value for each case-insensitive, section-qualified key."""
    values = {}
    section = ""

    for line in _meaningful_lines(text):
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        separator = _SEPARATOR.search(line)
        if not separator:
            continue

        name = line[:separator.start()].strip().lower()
        key = f"{section}.{name}" if section else name
        if key in values:
            continue

        value = line[separator.end():].strip()
        values[key] = int(value) if _INTEGER.fullmatch(value) else value

    return values
