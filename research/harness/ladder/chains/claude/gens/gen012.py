"""A tiny INI-like configuration format.

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           continues here

- Blank lines and lines starting with '#' are ignored.
- A line "[name]" starts a section; keys that follow are stored as
  "name.key" until the next header. Keys before any header use their
  bare name.
- Each line splits into a key and a value at the first '=' or ':'.
- A line ending in a backslash is joined with the next line before
  anything else is parsed, so a value can span several lines.
- Keys are lowercased. The first assignment to a key wins.
- A value made up only of digits, optionally preceded by '-', becomes
  an int; everything else stays a stripped string.
"""
from __future__ import annotations


def parse(text: str) -> dict:
    settings: dict = {}
    section = ""

    for line in _unwrap(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        split = _split_assignment(line)
        if split is None:
            continue
        key, value = split

        key = f"{section}.{key}" if section else key
        settings.setdefault(key, _coerce(value))

    return settings


def _unwrap(text: str):
    """Yield logical lines, joining a line ending in '\\' with the next."""
    pending = ""
    for raw in text.split("\n"):
        if raw.endswith("\\"):
            pending += raw[:-1]
            continue
        yield pending + raw
        pending = ""
    if pending:
        yield pending


def _split_assignment(line: str) -> tuple[str, str] | None:
    """Split *line* at whichever of '=' or ':' appears first."""
    cut = min((i for i in (line.find("="), line.find(":")) if i != -1), default=-1)
    if cut == -1:
        return None
    return line[:cut].strip().lower(), line[cut + 1:].strip()


def _coerce(value: str):
    digits = value[1:] if value.startswith("-") else value
    return int(value) if digits.isdigit() else value
