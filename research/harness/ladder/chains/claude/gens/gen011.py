"""A tiny INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           continues here

Rules:

* Blank lines and comment lines (first non-space character '#') are ignored.
* A line "[name]" opens a section; subsequent keys are stored as
  "name.key" until the next section header (or the end of the text).
  Keys given before any section header are stored under their bare name.
* Each remaining line is split into a key and a value at the first '='
  or ':', whichever comes first in the line.
* A trailing backslash joins a line with the one after it, before any
  other rule is applied, so a value may be spread across several lines.
* Keys are lowercased, and the first assignment to a key wins; later
  ones are ignored.
* A value that is only digits, optionally preceded by '-', is stored as
  an int; anything else is kept as a stripped string.
"""
from __future__ import annotations

SECTION_HEADER = ("[", "]")
COMMENT_PREFIX = "#"
ASSIGNMENT_CHARS = ("=", ":")


def parse(text: str) -> dict:
    """Parse *text* and return the settings it defines."""
    settings: dict = {}
    section = ""

    for line in _join_continuations(text):
        line = line.strip()
        if not line or line.startswith(COMMENT_PREFIX):
            continue

        header = _section_name(line)
        if header is not None:
            section = header
            continue

        assignment = _parse_assignment(line)
        if assignment is None:
            continue
        key, value = assignment

        full_key = f"{section}.{key}" if section else key
        if full_key not in settings:
            settings[full_key] = _coerce(value)

    return settings


def _join_continuations(text: str):
    """Yield the logical lines of *text*, splicing together any physical
    line ending in a backslash with the line that follows it."""
    buffer = []
    for raw_line in text.split("\n"):
        if raw_line.endswith("\\"):
            buffer.append(raw_line[:-1])
            continue
        buffer.append(raw_line)
        yield "".join(buffer)
        buffer.clear()
    if buffer:
        yield "".join(buffer)


def _section_name(line: str) -> str | None:
    """Return the lowercased name of a "[section]" header, or None if
    *line* is not one."""
    opening, closing = SECTION_HEADER
    if line.startswith(opening) and line.endswith(closing):
        return line[1:-1].strip().lower()
    return None


def _parse_assignment(line: str) -> tuple[str, str] | None:
    """Split *line* at the first '=' or ':' into a lowercased key and a
    value, or return None if it contains neither."""
    positions = (line.find(ch) for ch in ASSIGNMENT_CHARS)
    positions = [pos for pos in positions if pos != -1]
    if not positions:
        return None

    split_at = min(positions)
    key = line[:split_at].strip().lower()
    value = line[split_at + 1:].strip()
    return key, value


def _coerce(value: str):
    """Return *value* as an int when it is an optionally negative run of
    digits, otherwise return it unchanged."""
    magnitude = value[1:] if value.startswith("-") else value
    if magnitude.isdigit():
        return int(value)
    return value
