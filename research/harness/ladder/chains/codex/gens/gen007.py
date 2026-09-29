"""Parse a document of key-value entries grouped into optional sections."""

import re


INTEGER = re.compile(r"-?\d+\Z")


def parse(text):
    """Return the first value for each key, ignoring case."""
    result = {}
    section = ""

    # A backslash followed by a newline joins the two physical lines.
    for original in text.replace("\\\n", "").splitlines():
        line = original.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        delimiter = next((i for i, char in enumerate(line) if char in "=:"), None)
        if delimiter is None:
            continue

        key = line[:delimiter].strip().lower()
        if section:
            key = f"{section}.{key}"
        if key in result:
            continue

        value = line[delimiter + 1 :].strip()
        result[key] = int(value) if INTEGER.fullmatch(value) else value

    return result
