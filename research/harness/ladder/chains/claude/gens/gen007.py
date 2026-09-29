"""A small INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           spans two lines

- Blank lines and lines starting with '#' are ignored.
- '[name]' opens a section; subsequent keys are stored as "name.key"
  until the next header. Keys before any header keep their bare name.
- Each line is split into key and value on the first '=' or ':', whichever
  comes first.
- A trailing backslash continues the line onto the next one, so a value
  can span several physical lines.
- Keys are lowercased. The first assignment of a key wins; later ones
  for the same key are dropped.
- A value made only of digits (with an optional leading '-') is stored
  as an int; everything else is kept as a stripped string.
"""
from __future__ import annotations

import re

_SECTION_RE = re.compile(r"\[(.+)\]")
_INT_RE = re.compile(r"-?\d+")


def parse(text: str) -> dict:
    """Parse *text* and return the settings it defines."""
    settings: dict = {}
    section = ""

    for line in _join_continuations(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = _SECTION_RE.fullmatch(line)
        if match:
            section = match.group(1).strip().lower()
            continue

        key, value = _split_assignment(line)
        if key is None:
            continue
        if section:
            key = f"{section}.{key}"
        settings.setdefault(key, _coerce(value))

    return settings


def _join_continuations(text: str):
    """Yield logical lines, stitching together any joined by a trailing backslash."""
    buffer = []
    for line in text.split("\n"):
        if line.endswith("\\"):
            buffer.append(line[:-1])
            continue
        buffer.append(line)
        yield "".join(buffer)
        buffer = []
    if buffer:
        yield "".join(buffer)


def _split_assignment(line: str) -> tuple[str | None, str]:
    """Split *line* on its first '=' or ':' into a lowercase key and raw value."""
    positions = (line.find("="), line.find(":"))
    positions = [p for p in positions if p != -1]
    if not positions:
        return None, ""
    cut = min(positions)
    return line[:cut].strip().lower(), line[cut + 1:].strip()


def _coerce(value: str):
    """Convert digit-only values to int, leaving anything else as a string."""
    return int(value) if _INT_RE.fullmatch(value) else value
