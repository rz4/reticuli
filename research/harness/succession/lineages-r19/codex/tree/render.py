"""Small text renderers and the authoring recipe writer."""

from __future__ import annotations

import datetime
import json
import time


def toml(value):
    """Render a value admitted by a claim recipe as TOML."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{ " + ", ".join(f"{key} = {toml(item)}" for key, item in value.items()) + " }"
    raise TypeError(f"cannot write TOML value: {value!r}")


def dump_recipe(recipe):
    lines = ["[claim]"]
    for key, value in recipe["claim"].items():
        lines.append(f"{key} = {toml(value)}")
    for step in recipe.get("step", []):
        lines.extend(("", "[[step]]"))
        for key, value in step.items():
            lines.append(f"{key} = {toml(value)}")
    return "\n".join(lines) + "\n"


def short(value, length=12):
    value = str(value)
    return value if len(value) <= length else value[:length] + "…"


def duration(seconds):
    seconds = max(0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {remaining}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
    return duration(time.time() - float(when)) + " ago"


def paint(value, color=None):
    return str(value)


def table(rows, headers=None):
    rows = [list(map(str, row)) for row in rows]
    if headers is not None:
        rows.insert(0, list(map(str, headers)))
    if not rows:
        return ""
    widths = [max(len(row[i]) if i < len(row) else 0 for row in rows)
              for i in range(max(map(len, rows)))]
    return "\n".join("  ".join((row[i] if i < len(row) else "").ljust(width)
                                for i, width in enumerate(widths)).rstrip()
                     for row in rows)


def tree(node, prefix=""):
    if isinstance(node, dict):
        return "\n".join(prefix + str(key) + ("\n" + tree(value, prefix + "  ")
                                               if isinstance(value, (dict, list)) else ": " + str(value))
                         for key, value in node.items())
    if isinstance(node, list):
        return "\n".join(tree(item, prefix) for item in node)
    return prefix + str(node)
