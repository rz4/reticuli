"""Small presentation helpers and a TOML writer for claim recipes."""

from __future__ import annotations

import datetime as _datetime
import json


def _value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {_value(item)}" for key, item in value.items()) + " }"
    raise TypeError(f"cannot write TOML value {value!r}")


def dump_recipe(recipe):
    """Serialize a parsed recipe without changing its types or key order."""
    lines = ["[claim]"]
    for key, value in recipe["claim"].items():
        lines.append(f"{key} = {_value(value)}")
    for step in recipe.get("step", []):
        lines.extend(("", "[[step]]"))
        for key, value in step.items():
            lines.append(f"{key} = {_value(value)}")
    return "\n".join(lines) + "\n"


def toml(value):
    return dump_recipe(value) if isinstance(value, dict) and "claim" in value else _value(value)


def short(value, length=12):
    return str(value)[:length]


def duration(seconds):
    seconds = float(seconds)
    return f"{seconds:.1f}s" if seconds < 60 else f"{int(seconds // 60)}m {seconds % 60:.1f}s"


def ago(when):
    if isinstance(when, str):
        when = _datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    if isinstance(when, (int, float)):
        seconds = _datetime.datetime.now().timestamp() - when
    else:
        seconds = (_datetime.datetime.now(when.tzinfo) - when).total_seconds()
    return duration(max(0, seconds)) + " ago"


def table(rows, columns=None):
    rows = list(rows)
    if not rows:
        return ""
    if columns is None:
        columns = list(rows[0]) if isinstance(rows[0], dict) else range(len(rows[0]))
    cells = [[str(row[col]) for col in columns] for row in rows]
    headings = [str(col) for col in columns]
    widths = [max(len(headings[i]), *(len(row[i]) for row in cells)) for i in range(len(headings))]
    return "\n".join(["  ".join(x.ljust(widths[i]) for i, x in enumerate(headings)),
                      *["  ".join(x.ljust(widths[i]) for i, x in enumerate(row)) for row in cells]])


def tree(value, indent=0):
    if isinstance(value, dict):
        return "\n".join(" " * indent + str(key) + (":\n" + tree(item, indent + 2) if isinstance(item, (dict, list)) else ": " + str(item)) for key, item in value.items())
    if isinstance(value, list):
        return "\n".join(" " * indent + "- " + ("\n" + tree(item, indent + 2) if isinstance(item, (dict, list)) else str(item)) for item in value)
    return " " * indent + str(value)


def paint(value, *args, **kwargs):
    return str(value)
