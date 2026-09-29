"""A small parser for INI-flavored configuration text.

    [server]
    host = localhost
    port: 8080
    # comments are ignored
    banner = welcome to \\
             the machine

Rules:

* Blank lines and lines starting with '#' are ignored.
* A line of the form '[name]' switches the current section. Keys defined
  after it are stored as "name.key"; keys before any section use their
  bare name.
* Every other non-empty line is an assignment: everything before the
  first '=' or ':' (whichever appears first) is the key, everything
  after is the value.
* A line ending in a backslash is joined with the line that follows,
  before any other rule is applied, so a value may span several lines.
* Keys are lowercased. The first assignment of a given key wins; later
  ones are ignored.
* A value that is only digits, with an optional leading '-', is stored
  as an int. Anything else is stored as a stripped string.
"""
from __future__ import annotations

__all__ = ["parse"]


def parse(text: str) -> dict:
    """Parse *text* and return a dict of qualified keys to values."""
    values: dict = {}
    section = ""

    for line in _logical_lines(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        key, sep, value = _partition_on_first(line, "=:")
        if sep is None:
            continue

        key = key.strip().lower()
        full_key = f"{section}.{key}" if section else key
        values.setdefault(full_key, _coerce(value.strip()))

    return values


def _logical_lines(text: str):
    """Split *text* into lines, merging any that end with a backslash
    continuation into the line that follows."""
    pending = ""
    for raw in text.split("\n"):
        if raw.endswith("\\"):
            pending += raw[:-1]
        else:
            yield pending + raw
            pending = ""
    if pending:
        yield pending


def _partition_on_first(line: str, separators: str):
    """Like str.partition, but split on whichever character in
    *separators* occurs earliest in *line*. Returns (before, sep, after);
    sep is None and after is "" if none of the separators appear."""
    positions = (line.find(ch) for ch in separators)
    positions = [p for p in positions if p != -1]
    if not positions:
        return line, None, ""
    index = min(positions)
    return line[:index], line[index], line[index + 1:]


def _coerce(value: str):
    """Turn *value* into an int when it looks like one; otherwise leave
    it as a string."""
    digits = value[1:] if value.startswith("-") else value
    if digits and digits.isdigit():
        return int(value)
    return value
