"""Small renderers for claim recipes and terminal reports."""
from __future__ import annotations

import datetime
import json


def toml(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {toml(item)}" for key, item in value.items()) + " }"
    raise TypeError(f"cannot render as TOML: {type(value).__name__}")


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
    return str(value)[:length]


def duration(seconds):
    return f"{float(seconds):.1f}s"


def ago(when):
    if isinstance(when, (int, float)):
        seconds = datetime.datetime.now().timestamp() - when
    else:
        try:
            then = datetime.datetime.fromisoformat(str(when).replace("Z", "+00:00"))
            seconds = (datetime.datetime.now(datetime.timezone.utc) - then).total_seconds()
        except ValueError:
            return str(when)
    return duration(max(0, seconds)) + " ago"


def table(rows, columns=None):
    rows = list(rows)
    if not rows:
        return ""
    columns = list(columns or (rows[0].keys() if isinstance(rows[0], dict) else range(len(rows[0]))))
    cells = [[str(row[column]) for column in columns] for row in rows]
    widths = [max(len(str(column)), *(len(row[i]) for row in cells)) for i, column in enumerate(columns)]
    return "\n".join(["  ".join(str(column).ljust(widths[i]) for i, column in enumerate(columns)),
                      *["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in cells]])


def tree(value, indent=0):
    if isinstance(value, dict):
        return "\n".join(" " * indent + str(key) + ": " +
                         (tree(item, indent + 2) if isinstance(item, (dict, list)) else str(item))
                         for key, item in value.items())
    if isinstance(value, list):
        return "\n".join(" " * indent + "- " + tree(item, indent + 2) for item in value)
    return str(value)


def paint(value, color=None):
    return str(value)
