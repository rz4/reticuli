"""Parse a sectioned collection of key-value entries."""

import re


_INTEGER = re.compile(r"-?\d+\Z")


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

        separators = (position for char in "=:" if (position := line.find(char)) >= 0)
        separator = min(separators, default=-1)
        if separator < 0:
            continue

        name = line[:separator].strip().lower()
        value = line[separator + 1 :].strip()
        key = f"{section}.{name}" if section else name
        if key not in entries:
            entries[key] = int(value) if _INTEGER.fullmatch(value) else value

    return entries
