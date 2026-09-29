"""A small INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           spans two lines

- Blank lines and lines starting with '#' are ignored.
- '[name]' opens a section. Keys that follow are stored under
  "name.key" until the next section header; keys before any header
  are stored bare (no prefix).
- The key/value separator is the first '=' or ':' on the line.
- A trailing backslash joins a line with the one after it, so a
  value can be written across several physical lines.
- Keys are case-folded to lowercase. The first value assigned to a
  key wins; later assignments to the same key are ignored.
- Values that look like plain integers ('-'? followed by digits) are
  converted to int; everything else is kept as the stripped string.
"""
from __future__ import annotations

import re

_SECTION_RE = re.compile(r"\[(?P<name>.+)\]")
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
            section = match.group("name").strip().lower()
            continue

        parsed = _split_assignment(line)
        if parsed is None:
            continue
        key, value = parsed

        full_key = f"{section}.{key}" if section else key
        settings.setdefault(full_key, _to_value(value))

    return settings


def _join_continuations(text: str):
    """Yield logical lines, splicing together any joined by a trailing '\\'."""
    buffer = []
    for raw in text.split("\n"):
        if raw.endswith("\\"):
            buffer.append(raw[:-1])
            continue
        buffer.append(raw)
        yield "".join(buffer)
        buffer.clear()
    if buffer:
        yield "".join(buffer)


def _split_assignment(line: str) -> tuple[str, str] | None:
    """Split on the first '=' or ':' into (key, value); None if neither is present."""
    for i, char in enumerate(line):
        if char in "=:":
            return line[:i].strip().lower(), line[i + 1:].strip()
    return None


def _to_value(raw: str):
    """Coerce integer-looking text to int; leave anything else as a string."""
    return int(raw) if _INT_RE.fullmatch(raw) else raw
