"""Parse a simple, optionally sectioned key-value document."""

import re


INTEGER = re.compile(r"-?\d+")


def parse(text):
    entries = {}
    section = ""

    for raw_line in text.replace("\\\n", "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        split_at = next((i for i, char in enumerate(line) if char in "=:"), None)
        if split_at is None:
            continue

        name = line[:split_at].strip().lower()
        key = f"{section}.{name}" if section else name
        if key in entries:
            continue

        value = line[split_at + 1 :].strip()
        entries[key] = int(value) if INTEGER.fullmatch(value) else value

    return entries
