"""Read key-value entries from a text file with optional sections."""

import re


_INTEGER = re.compile(r"-?\d+\Z")
_SEPARATOR = re.compile(r"[=:]")


def _value(text):
    if _INTEGER.fullmatch(text):
        return int(text)
    return text


def parse(text):
    result = {}
    current_section = ""

    for source_line in text.replace("\\\n", "").splitlines():
        line = source_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip().lower()
            continue

        separator = _SEPARATOR.search(line)
        if separator is None:
            continue

        name = line[: separator.start()].strip().lower()
        key = ".".join((current_section, name)) if current_section else name
        if key not in result:
            result[key] = _value(line[separator.end() :].strip())

    return result
