"""Parser for a small INI-flavored configuration format.

Example::

    [server]
    host = localhost
    port: 8080
    # comments are ignored
    banner = welcome to \\
             the machine

Rules:

* Blank lines and lines starting with '#' are ignored.
* A '[section]' line changes the current section. Keys that follow are
  stored under "section.key"; keys before any section use their bare name.
* Each remaining line is an assignment, split on the first '=' or ':'
  (whichever comes first) into a key and a value.
* A trailing backslash continues a line onto the next one, before any
  other rule is applied - so an assignment's value can span several
  physical lines.
* Keys are folded to lowercase. If the same key is assigned twice, the
  first assignment wins and later ones are ignored.
* A value consisting only of digits, optionally preceded by '-', is
  stored as an int. Everything else is stored as a stripped string.
"""
from __future__ import annotations

SECTION_KEY_SEP = "."


def parse(text: str) -> dict:
    """Parse *text* and return a dict mapping qualified keys to values."""
    result: dict = {}
    section = ""

    for line in _join_continuations(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if _is_section_header(line):
            section = line[1:-1].strip().lower()
            continue

        assignment = _split_assignment(line)
        if assignment is None:
            continue
        key, value = assignment

        qualified_key = f"{section}{SECTION_KEY_SEP}{key}" if section else key
        result.setdefault(qualified_key, _coerce(value))

    return result


def _join_continuations(text: str):
    """Yield logical lines from *text*, gluing lines ending in '\\' to the next."""
    buffer = ""
    for raw_line in text.split("\n"):
        if raw_line.endswith("\\"):
            buffer += raw_line[:-1]
            continue
        yield buffer + raw_line
        buffer = ""
    if buffer:
        yield buffer


def _is_section_header(line: str) -> bool:
    return line.startswith("[") and line.endswith("]") and len(line) >= 2


def _split_assignment(line: str) -> tuple[str, str] | None:
    """Split *line* on its first '=' or ':' into (key, value), lowercasing the key."""
    positions = [p for p in (line.find("="), line.find(":")) if p != -1]
    if not positions:
        return None
    cut = min(positions)
    key = line[:cut].strip().lower()
    value = line[cut + 1:].strip()
    return key, value


def _coerce(value: str):
    """Convert *value* to an int when it looks like one, else return it unchanged."""
    unsigned = value.removeprefix("-")
    if unsigned.isdigit():
        return int(value)
    return value
