"""Parse sectioned key/value text into a flat dictionary."""

import re


def parse(text):
    """Return the first value found for each case-insensitive qualified name."""
    result = {}
    section = ""

    for raw_line in text.replace("\\\n", "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        split_at = next(
            (index for index, character in enumerate(line) if character in "=:"),
            None,
        )
        if split_at is None:
            continue

        name = line[:split_at].strip().lower()
        qualified_name = f"{section}.{name}" if section else name
        if qualified_name in result:
            continue

        value = line[split_at + 1 :].strip()
        result[qualified_name] = int(value) if re.fullmatch(r"-?\d+", value) else value

    return result
