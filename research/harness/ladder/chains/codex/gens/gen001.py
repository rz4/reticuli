"""Parse a small sectioned key-value format."""

import re


_SEPARATOR = re.compile(r"[=:]")
_INTEGER = re.compile(r"-?\d+")


def parse(text):
    entries = {}
    section = ""

    for raw_line in text.replace("\\\n", "").split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        separator = _SEPARATOR.search(line)
        if separator is None:
            continue

        name = line[:separator.start()].strip().lower()
        key = f"{section}.{name}" if section else name
        if key in entries:
            continue

        value = line[separator.end():].strip()
        entries[key] = int(value) if _INTEGER.fullmatch(value) else value

    return entries
