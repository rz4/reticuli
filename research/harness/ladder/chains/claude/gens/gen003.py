"""A small parser for INI-flavored configuration text.

Supported syntax:

    [section]        starts a new section; later keys are prefixed "section.key"
    key = value       assignment; ':' works as a separator too
    key : value
    # comment         a line starting with '#' is ignored
    foo = bar \\       a trailing backslash joins this line with the next
        baz

Keys are lowercased. Within a given (possibly empty) section, the first
assignment to a key wins and later duplicates are ignored. Values that look
like plain integers are converted to int; everything else is kept as a
string.
"""
from __future__ import annotations

import re

_SECTION_RE = re.compile(r"^\[(?P<name>.*)\]$")
_INT_RE = re.compile(r"^-?\d+$")


def parse(text: str) -> dict:
    """Parse *text* and return the settings it defines as a dict."""
    result: dict = {}
    section = ""

    for line in _join_continuations(text).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        section_match = _SECTION_RE.match(line)
        if section_match:
            section = section_match.group("name").strip().lower()
            continue

        parsed = _split_assignment(line)
        if parsed is None:
            continue
        key, value = parsed

        full_key = f"{section}.{key}" if section else key
        result.setdefault(full_key, _coerce(value))

    return result


def _join_continuations(text: str) -> str:
    """Collapse "...\\\n..." into a single logical line."""
    return text.replace("\\\n", "")


def _split_assignment(line: str) -> tuple[str, str] | None:
    """Split *line* into (key, value) on the first '=' or ':'."""
    match = re.search(r"[=:]", line)
    if match is None:
        return None
    key = line[: match.start()].strip().lower()
    value = line[match.end() :].strip()
    return key, value


def _coerce(value: str):
    """Convert integer-looking values to int, otherwise leave as str."""
    return int(value) if _INT_RE.match(value) else value
