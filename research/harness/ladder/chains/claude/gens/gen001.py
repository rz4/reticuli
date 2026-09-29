"""A minimal parser for INI-like configuration text.

Supports ``[section]`` headers, ``key = value`` or ``key: value``
assignments, ``#`` comments, blank lines, trailing-backslash line
continuations, and automatic coercion of integer-looking values.
"""
import re

INTEGER_RE = re.compile(r"-?\d+")


def parse(text):
    """Parse configuration text and return a dict of key -> value.

    Keys are lower-cased and, inside a ``[section]`` block, prefixed
    with ``section.``. The first assignment for a given key wins;
    later duplicates are ignored. Values that look like integers are
    converted to ``int``.
    """
    text = _join_continuations(text)
    settings = {}
    section = ""

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        header = _section_header(line)
        if header is not None:
            section = header
            continue

        parsed = _split_assignment(line)
        if parsed is None:
            continue
        key, value = parsed

        full_key = f"{section}.{key}" if section else key
        settings.setdefault(full_key, _coerce(value))

    return settings


def _join_continuations(text):
    return text.replace("\\\n", "")


def _section_header(line):
    if line.startswith("[") and line.endswith("]"):
        return line[1:-1].strip().lower()
    return None


def _split_assignment(line):
    cut = min((i for i in (line.find("="), line.find(":")) if i != -1), default=-1)
    if cut == -1:
        return None
    key = line[:cut].strip().lower()
    value = line[cut + 1:].strip()
    return key, value


def _coerce(value):
    if INTEGER_RE.fullmatch(value):
        return int(value)
    return value
