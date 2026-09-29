"""Parser for a tiny INI-like configuration format.

Example::

    [section]
    key = value
    key: value
    # a comment
    long = this value \\
           continues here

Rules:

- Blank lines and lines starting with '#' are ignored.
- A line of the form "[name]" opens a section. Keys found afterwards
  are stored under "name.key" until the next section header. Keys
  found before any header are stored under their bare name.
- A key and its value are separated by the first '=' or ':' on the
  line, whichever comes first.
- A trailing backslash joins a line with the one that follows, so a
  single value may be written across multiple lines.
- Keys are lowercased, and the first assignment made to a key is the
  one that is kept.
- A value that consists only of digits, optionally prefixed with '-',
  is stored as an int. Anything else is stored as a stripped string.
"""
from __future__ import annotations


def parse(text: str) -> dict:
    result: dict = {}
    section = ""

    for line in _join_continuations(text):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        header = _section_name(line)
        if header is not None:
            section = header
            continue

        pair = _key_value(line)
        if pair is None:
            continue
        key, value = pair

        full_key = f"{section}.{key}" if section else key
        result.setdefault(full_key, _to_value(value))

    return result


def _join_continuations(text: str):
    """Yield logical lines from *text*, gluing a trailing '\\' to the next line."""
    buffer = ""
    for raw_line in text.split("\n"):
        if raw_line.endswith("\\"):
            buffer += raw_line[:-1]
        else:
            yield buffer + raw_line
            buffer = ""
    if buffer:
        yield buffer


def _section_name(line: str) -> str | None:
    if line.startswith("[") and line.endswith("]"):
        return line[1:-1].strip().lower()
    return None


def _key_value(line: str) -> tuple[str, str] | None:
    positions = [p for p in (line.find("="), line.find(":")) if p != -1]
    if not positions:
        return None
    split_at = min(positions)
    key = line[:split_at].strip().lower()
    value = line[split_at + 1:].strip()
    return key, value


def _to_value(text: str):
    body = text[1:] if text.startswith("-") else text
    if body.isdigit():
        return int(text)
    return text
