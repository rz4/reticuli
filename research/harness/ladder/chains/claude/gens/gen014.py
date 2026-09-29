"""A minimal parser for INI-style configuration text.

    [server]
    host = localhost
    port: 8080
    # comments are ignored
    banner = welcome to \\
             the machine

- Blank lines and lines starting with '#' are skipped.
- "[section]" switches the current section; later keys are stored as
  "section.key". Keys given before any section use their bare name.
- The first '=' or ':' on a line (whichever appears first) splits key
  from value.
- A line ending in a backslash is glued to the next line before any
  of the above rules are applied, so a value can span several lines.
- Keys are case-insensitive (stored lowercased); if a key is assigned
  more than once, the earliest assignment wins.
- Values made up only of an optional leading '-' and digits are
  converted to int; everything else is kept as a stripped string.
"""
from __future__ import annotations


def parse(text: str) -> dict:
    """Parse *text* and return a flat dict of qualified keys to values."""
    config: dict = {}
    section = ""

    for line in _logical_lines(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        name = _parse_section(line)
        if name is not None:
            section = name
            continue

        parsed = _parse_assignment(line)
        if parsed is None:
            continue
        key, raw_value = parsed

        qualified = f"{section}.{key}" if section else key
        config.setdefault(qualified, _coerce(raw_value))

    return config


def _logical_lines(text: str):
    """Split *text* into lines, joining any line ending in '\\' with the next."""
    pending = []
    for line in text.split("\n"):
        if line.endswith("\\"):
            pending.append(line[:-1])
            continue
        pending.append(line)
        yield "".join(pending)
        pending = []
    if pending:
        yield "".join(pending)


def _parse_section(line: str) -> str | None:
    """Return the section name if *line* is a "[name]" header, else None."""
    if len(line) >= 2 and line[0] == "[" and line[-1] == "]":
        return line[1:-1].strip().lower()
    return None


def _parse_assignment(line: str) -> tuple[str, str] | None:
    """Split *line* into (key, value) on the first '=' or ':', if any."""
    cut = min((i for i in (line.find("="), line.find(":")) if i != -1), default=-1)
    if cut == -1:
        return None
    key = line[:cut].strip().lower()
    value = line[cut + 1:].strip()
    return key, value


def _coerce(value: str):
    """Turn *value* into an int when it looks like one, else leave it as a string."""
    digits = value[1:] if value.startswith("-") else value
    if digits and digits.isdigit():
        return int(value)
    return value
