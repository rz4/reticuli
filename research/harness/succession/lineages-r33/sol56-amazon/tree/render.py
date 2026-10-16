"""Small, dependency-free renderers used by Reticuli's upper layers.

The TOML writer is intentionally boring: recipes are parsed objects, so a
stable, ordinary spelling is preferable to preserving incidental source
formatting.
"""
from __future__ import annotations

import datetime as _datetime
import json
import math
import re
from collections.abc import Mapping, Sequence

_BARE = re.compile(r"^[A-Za-z0-9_-]+$")
_COLORS = {"red": 31, "green": 32, "yellow": 33, "blue": 34,
           "magenta": 35, "cyan": 36, "bold": 1, "dim": 2}


def short(value, width=12):
    """Return a compact display spelling of *value*."""
    text = str(value)
    width = max(1, int(width))
    return text if len(text) <= width else text[:width]


def duration(seconds):
    """Render a duration in a compact human-readable form."""
    if seconds is None:
        return "?"
    value = float(seconds)
    if value < 1:
        return f"{value * 1000:.0f}ms"
    if value < 60:
        return f"{value:.1f}s" if value < 10 else f"{value:.0f}s"
    minutes, sec = divmod(int(round(value)), 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def ago(when, now=None):
    """Render an ISO timestamp (or epoch value) relative to now."""
    if isinstance(when, str):
        try:
            point = _datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            return when
    elif isinstance(when, _datetime.datetime):
        point = when
    else:
        point = _datetime.datetime.fromtimestamp(float(when), _datetime.timezone.utc)
    if point.tzinfo is None:
        point = point.replace(tzinfo=_datetime.timezone.utc)
    if now is None:
        current = _datetime.datetime.now(_datetime.timezone.utc)
    elif isinstance(now, _datetime.datetime):
        current = now if now.tzinfo else now.replace(tzinfo=_datetime.timezone.utc)
    else:
        current = _datetime.datetime.fromtimestamp(float(now), _datetime.timezone.utc)
    delta = (current - point).total_seconds()
    if delta < 0:
        return "in " + duration(-delta)
    return duration(delta) + " ago"


def paint(text, colour=None, enabled=True, **kwargs):
    """Apply a named ANSI colour when enabled; otherwise return plain text."""
    if colour is None:
        colour = kwargs.get("color")
    value = str(text)
    code = _COLORS.get(str(colour))
    return f"\x1b[{code}m{value}\x1b[0m" if enabled and code else value


def table(rows, columns=None):
    """Render mappings or sequences as a simple aligned text table."""
    rows = list(rows)
    if not rows:
        return ""
    if isinstance(rows[0], Mapping):
        columns = list(columns or rows[0].keys())
        body = [[str(row.get(col, "")) for col in columns] for row in rows]
        all_rows = [[str(x) for x in columns]] + body
    else:
        body = [[str(x) for x in row] for row in rows]
        all_rows = body
    width = max(len(r) for r in all_rows)
    sizes = [max((len(r[i]) if i < len(r) else 0) for r in all_rows)
             for i in range(width)]
    return "\n".join("  ".join((r[i] if i < len(r) else "").ljust(sizes[i])
                                 for i in range(width)).rstrip()
                     for r in all_rows)


def tree(value, prefix=""):
    """Render a nested mapping/list as an indented tree."""
    lines = []
    def walk(item, indent):
        if isinstance(item, Mapping):
            for key, child in item.items():
                lines.append(indent + str(key))
                walk(child, indent + "  ")
        elif isinstance(item, (list, tuple)):
            for child in item:
                lines.append(indent + "-")
                walk(child, indent + "  ")
        else:
            lines.append(indent + str(item))
    walk(value, prefix)
    return "\n".join(lines)


def _key(value):
    text = str(value)
    return text if _BARE.fullmatch(text) else json.dumps(text, ensure_ascii=True)


def toml(value):
    """Return the TOML scalar/array/inline-table spelling of *value*."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml(x) for x in value) + "]"
    if isinstance(value, Mapping):
        return "{ " + ", ".join(f"{_key(k)} = {toml(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"value cannot be represented in TOML: {value!r}")


def dump_recipe(recipe):
    """Serialize a parsed Reticuli recipe to semantically equivalent TOML."""
    if not isinstance(recipe, Mapping):
        raise TypeError("recipe must be a mapping")
    lines = []
    # Root scalars must precede table declarations.
    for key, value in recipe.items():
        if key not in ("claim", "step") and not isinstance(value, Mapping):
            lines.append(f"{_key(key)} = {toml(value)}")
    if lines:
        lines.append("")
    claim = recipe.get("claim")
    if isinstance(claim, Mapping):
        lines.append("[claim]")
        for key, value in claim.items():
            lines.append(f"{_key(key)} = {toml(value)}")
        lines.append("")
    steps = recipe.get("step", [])
    for step in steps if isinstance(steps, list) else []:
        lines.append("[[step]]")
        for key, value in step.items():
            lines.append(f"{_key(key)} = {toml(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["ago", "duration", "paint", "short", "table", "toml", "tree", "dump_recipe"]
