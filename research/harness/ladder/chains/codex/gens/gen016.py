"""Read a simple sectioned configuration into a flat dictionary."""

import re


_SEPARATOR = re.compile(r"[=:]")
_INTEGER = re.compile(r"-?\d+")


def _content_lines(text):
    """Yield nonempty, noncomment lines after joining continuations."""
    for physical_line in text.replace("\\\n", "").splitlines():
        line = physical_line.strip()
        if line and not line.startswith("#"):
            yield line


def parse(text):
    """Keep the first value for each lowercase, section-qualified name."""
    entries = {}
    section = ""

    for line in _content_lines(text):
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        separator = _SEPARATOR.search(line)
        if separator is None:
            continue

        name = line[: separator.start()].strip().lower()
        key = ".".join((section, name)) if section else name
        if key in entries:
            continue

        value = line[separator.end() :].strip()
        entries[key] = int(value) if _INTEGER.fullmatch(value) else value

    return entries
