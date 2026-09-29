"""A small INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           spans two lines

Rules:

* Blank lines and lines whose first non-space character is '#' are ignored.
* A line '[name]' opens a section; later keys are stored as "name.key"
  until the next header. Keys before any header keep their own name.
* A line splits into key and value at its first '=' or ':', whichever
  comes first.
* A trailing backslash joins a line with the one after it, so a value
  can span several physical lines.
* Keys are folded to lowercase. The first assignment to a key wins;
  later ones are ignored.
* A value that is only digits, optionally signed with a leading '-',
  is stored as an int. Anything else is stored as a stripped string.
"""
from __future__ import annotations

INT_RE_CHARS = set("0123456789")


def parse(text: str) -> dict:
    """Parse *text* and return the settings it defines."""
    settings = {}
    section = ""

    for line in _join_continuations(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        split = _find_separator(line)
        if split is None:
            continue
        key = line[:split].strip().lower()
        value = line[split + 1:].strip()

        full_key = f"{section}.{key}" if section else key
        if full_key not in settings:
            settings[full_key] = _coerce(value)

    return settings


def _join_continuations(text: str):
    """Yield logical lines, merging any that end with a backslash."""
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


def _find_separator(line: str) -> int | None:
    """Return the index of the first '=' or ':' in *line*, or None."""
    positions = (line.find(ch) for ch in "=:")
    positions = [pos for pos in positions if pos != -1]
    return min(positions) if positions else None


def _coerce(value: str):
    """Turn *value* into an int when it is one, otherwise leave it as a string."""
    body = value[1:] if value.startswith("-") else value
    if body and set(body) <= INT_RE_CHARS:
        return int(value)
    return value
