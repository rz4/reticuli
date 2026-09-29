"""Parser for a small INI-flavored configuration format.

Grammar, informally:

    [section]              -- switches the active section
    key = value             -- assignment ('=' or ':' both work)
    # comment                -- ignored, must start the line
    trailing backslash \\    -- joins with the next line before anything else

Keys are folded to lowercase. Inside a section, keys are stored as
"section.key". The first assignment to a key wins; later ones are
dropped. Values that parse as a plain integer (optional leading '-')
are converted to int; everything else stays a string.
"""
from __future__ import annotations

import re

_INT = re.compile(r"-?[0-9]+")
_SECTION = re.compile(r"\[(.*)\]")


def parse(text: str) -> dict:
    """Parse *text* and return the resulting {key: value} dict."""
    settings: dict[str, object] = {}
    section = ""

    for raw_line in _unwrap_continuations(text).splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        section_match = _SECTION.fullmatch(line)
        if section_match:
            section = section_match.group(1).strip().lower()
            continue

        assignment = _parse_assignment(line)
        if assignment is None:
            continue
        key, value = assignment

        qualified_key = f"{section}.{key}" if section else key
        if qualified_key not in settings:
            settings[qualified_key] = _coerce(value)

    return settings


def _unwrap_continuations(text: str) -> str:
    """Merge lines ending in a backslash with the line that follows."""
    return text.replace("\\\n", "")


def _parse_assignment(line: str) -> tuple[str, str] | None:
    """Split *line* on the first '=' or ':', whichever comes first."""
    positions = [p for p in (line.find("="), line.find(":")) if p != -1]
    if not positions:
        return None

    split_at = min(positions)
    key = line[:split_at].strip().lower()
    value = line[split_at + 1:].strip()
    return key, value


def _coerce(value: str) -> object:
    """Turn integer-looking strings into ints; leave everything else alone."""
    return int(value) if _INT.fullmatch(value) else value
