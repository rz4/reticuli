"""A small INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           spans two lines

Rules:

- Blank lines and lines starting with '#' are ignored.
- A '[name]' line opens a section. Keys that follow are stored under
  "name.key" until the next section header. Keys before any header
  are stored under their bare name.
- The key and value are split on whichever comes first, '=' or ':'.
- A line ending in a backslash is joined with the next physical line,
  so a value may be continued across several lines.
- Keys are case-folded to lowercase. If a key is assigned more than
  once, the first assignment wins and later ones are ignored.
- A value that looks like a plain integer (an optional leading '-'
  followed by digits) is converted to int; anything else is kept as
  the stripped string.
"""
from __future__ import annotations

import re

SECTION_HEADER = re.compile(r"^\[(.+)\]$")
INTEGER = re.compile(r"^-?\d+$")


def parse(text: str) -> dict:
    """Parse *text* and return the settings it defines."""
    settings = {}
    section = ""

    for line in _logical_lines(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        header = SECTION_HEADER.match(line)
        if header:
            section = header.group(1).strip().lower()
            continue

        key, value = _split_key_value(line)
        if key is None:
            continue

        full_key = f"{section}.{key}" if section else key
        settings.setdefault(full_key, _coerce(value))

    return settings


def _logical_lines(text: str):
    """Split *text* into lines, joining any pair linked by a trailing backslash."""
    pending = ""
    for raw_line in text.split("\n"):
        if raw_line.endswith("\\"):
            pending += raw_line[:-1]
            continue
        yield pending + raw_line
        pending = ""
    if pending:
        yield pending


def _split_key_value(line: str) -> tuple[str | None, str]:
    """Split *line* on its first '=' or ':' into a lowercased key and a value."""
    cut = min((i for i, c in enumerate(line) if c in "=:"), default=None)
    if cut is None:
        return None, ""
    return line[:cut].strip().lower(), line[cut + 1:].strip()


def _coerce(value: str):
    """Turn integer-looking text into an int, and leave everything else as a string."""
    return int(value) if INTEGER.match(value) else value
