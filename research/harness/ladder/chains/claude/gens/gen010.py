"""A tiny INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           continues here

- Blank lines, and lines whose first non-space character is '#', are skipped.
- A line of the form '[name]' starts a section. Keys that follow are stored
  under "name.key" until the next section header. Keys before any header
  are stored under their own name.
- Each remaining line is split into a key and a value at the first '=' or
  ':' in the line, whichever appears first.
- A line ending in a backslash is joined with the next physical line before
  any of the above rules are applied, so a value can span several lines.
- Keys are lowercased. If a key is assigned more than once, the first
  assignment wins and later ones are ignored.
- A value consisting only of digits, with an optional leading '-', is
  stored as an int; every other value is stored as a stripped string.
"""
from __future__ import annotations


def parse(text: str) -> dict:
    """Parse *text* and return the settings it defines."""
    settings: dict = {}
    section = ""

    for line in _logical_lines(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        key, value = _split_assignment(line)
        if key is None:
            continue

        full_key = f"{section}.{key}" if section else key
        settings.setdefault(full_key, _coerce(value))

    return settings


def _logical_lines(text: str):
    """Yield each line of *text*, joining lines that end in a backslash
    with the line that follows them."""
    pending = ""
    for raw_line in text.split("\n"):
        if raw_line.endswith("\\"):
            pending += raw_line[:-1]
            continue
        yield pending + raw_line
        pending = ""
    if pending:
        yield pending


def _split_assignment(line: str) -> tuple[str | None, str]:
    """Split *line* into a lowercased key and a value string, at whichever
    of '=' or ':' occurs first. Returns (None, "") if neither is present."""
    cut = min((i for i in (line.find("="), line.find(":")) if i != -1), default=None)
    if cut is None:
        return None, ""
    return line[:cut].strip().lower(), line[cut + 1:].strip()


def _coerce(value: str):
    """Return *value* as an int if it looks like one, otherwise unchanged."""
    digits = value[1:] if value.startswith("-") else value
    if digits.isdigit():
        return int(value)
    return value
