"""Parse a simple sectioned collection of key/value pairs."""

import re


def parse(text):
    """Return the first value for each case-insensitive, section-qualified key."""
    result = {}
    section = ""

    for raw_line in text.replace("\\\n", "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        separator = re.search(r"[=:]", line)
        if separator is None:
            continue

        key = line[:separator.start()].strip().lower()
        qualified_key = f"{section}.{key}" if section else key
        if qualified_key in result:
            continue

        value = line[separator.end():].strip()
        result[qualified_key] = int(value) if re.fullmatch(r"-?\d+", value) else value

    return result
