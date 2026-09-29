"""Parse sectioned key/value text into a single dictionary."""

import re


NUMBER = re.compile(r"-?\d+\Z")


def parse(text):
    """Return the first value found for each case-insensitive qualified key."""
    result = {}
    section = ""

    for raw_line in text.replace("\\\n", "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        boundary = next((i for i, char in enumerate(line) if char in "=:"), None)
        if boundary is None:
            continue

        name = line[:boundary].strip().lower()
        qualified_name = f"{section}.{name}" if section else name
        if qualified_name in result:
            continue

        value = line[boundary + 1 :].strip()
        result[qualified_name] = int(value) if NUMBER.fullmatch(value) else value

    return result
