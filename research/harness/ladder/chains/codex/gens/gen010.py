"""Read sectioned key/value text into a dictionary."""

import re


_INTEGER = re.compile(r"-?\d+\Z")
_ASSIGNMENT = re.compile(r"([^=:]*)[=:](.*)")


def _content_lines(text):
    """Yield nonblank lines that are not comments."""
    for raw_line in text.replace("\\\n", "").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            yield line


def _convert_value(raw):
    value = raw.strip()
    return int(value) if _INTEGER.fullmatch(value) else value


def parse(text):
    """Return the first value found for each case-insensitive qualified name."""
    entries = {}
    section = ""

    for line in _content_lines(text):
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        assignment = _ASSIGNMENT.fullmatch(line)
        if assignment is None:
            continue

        name, raw_value = assignment.groups()
        name = name.strip().lower()
        qualified_name = f"{section}.{name}" if section else name
        if qualified_name not in entries:
            entries[qualified_name] = _convert_value(raw_value)

    return entries
