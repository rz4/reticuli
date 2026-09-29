"""A small INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           spans two lines

Rules:

* Blank lines and lines whose first non-space character is '#' are ignored.
* A line of the form '[name]' opens a section. Every key that follows is
  stored under "name.key" until the next section header. Keys that appear
  before any header are stored under their own name.
* A line is split into key and value at its first '=' or ':', whichever
  appears first.
* A line ending in a backslash is joined with the line that follows it,
  so a value can be written across several physical lines.
* Keys are folded to lowercase. If a key is assigned more than once, the
  first assignment wins and later ones are ignored.
* A value consisting only of digits, optionally preceded by '-', is
  stored as an int. Every other value is stored as a stripped string.
"""
from __future__ import annotations

import re

_HEADER = re.compile(r"\[(?P<name>.+)\]")
_INTEGER = re.compile(r"-?\d+")


def parse(text: str) -> dict:
    """Parse *text* and return the settings it defines."""
    settings: dict = {}
    section = ""

    for raw_line in _logical_lines(text):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        header = _HEADER.fullmatch(line)
        if header is not None:
            section = header.group("name").strip().lower()
            continue

        assignment = _split_key_value(line)
        if assignment is None:
            continue
        key, value = assignment
        full_key = f"{section}.{key}" if section else key
        settings.setdefault(full_key, _parse_value(value))

    return settings


def _logical_lines(text: str):
    """Yield one string per logical line, merging any that end in '\\'."""
    pending = ""
    for physical_line in text.split("\n"):
        if physical_line.endswith("\\"):
            pending += physical_line[:-1]
            continue
        yield pending + physical_line
        pending = ""
    if pending:
        yield pending


def _split_key_value(line: str) -> tuple[str, str] | None:
    """Split *line* at its first '=' or ':', returning a lowercase key.

    Returns None if the line has neither separator.
    """
    cut_points = [line.find(sep) for sep in "=:"]
    cut_points = [pos for pos in cut_points if pos >= 0]
    if not cut_points:
        return None
    cut = min(cut_points)
    return line[:cut].strip().lower(), line[cut + 1:].strip()


def _parse_value(text: str):
    """Return *text* as an int when it looks like one, else as-is."""
    if _INTEGER.fullmatch(text):
        return int(text)
    return text
