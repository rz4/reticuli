"""Parser for a small INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment line
    long = this line \\
           continues here

Rules:

- Blank lines and lines starting with '#' are ignored.
- A line "[name]" opens a section; keys defined after it are stored as
  "name.key" until the next section header (or the top of the file, for
  keys with no section, which are stored bare).
- A key and value are separated by the first '=' or ':' on the line.
- A line ending in a backslash is joined with the line that follows it,
  so a value can be spread across multiple lines.
- Keys are folded to lowercase. If a key is assigned more than once in
  the same section, the first value wins.
- A value that looks like an integer (optional leading '-', digits only)
  is stored as an int; everything else is stored as the stripped string.
"""
from __future__ import annotations

import re

SECTION_HEADER = re.compile(r"\[(.+)\]")
INTEGER = re.compile(r"-?\d+")


def parse(text: str) -> dict:
    """Parse *text* and return the settings it defines."""
    settings: dict = {}
    section = ""

    for line in _logical_lines(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        header = SECTION_HEADER.fullmatch(line)
        if header:
            section = header.group(1).strip().lower()
            continue

        entry = _parse_assignment(line)
        if entry is None:
            continue
        key, value = entry

        full_key = f"{section}.{key}" if section else key
        if full_key not in settings:
            settings[full_key] = _coerce(value)

    return settings


def _logical_lines(text: str):
    """Yield *text* line by line, with backslash continuations joined."""
    pending = ""
    for raw_line in text.split("\n"):
        if raw_line.endswith("\\"):
            pending += raw_line[:-1]
            continue
        yield pending + raw_line
        pending = ""
    if pending:
        yield pending


def _parse_assignment(line: str) -> tuple[str, str] | None:
    """Split *line* on its first '=' or ':' into a (key, value) pair."""
    for i, ch in enumerate(line):
        if ch in "=:":
            return line[:i].strip().lower(), line[i + 1 :].strip()
    return None


def _coerce(value: str):
    """Turn integer-looking strings into ints; leave everything else alone."""
    return int(value) if INTEGER.fullmatch(value) else value
