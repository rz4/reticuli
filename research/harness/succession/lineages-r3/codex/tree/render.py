"""Small text renderers, including the claim recipe writer."""

from __future__ import annotations

import datetime
import json
import math


def toml(value):
    """Render a TOML value used by a recipe."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {toml(item)}" for key, item in value.items()) + " }"
    raise TypeError(f"cannot write TOML value: {value!r}")


def dump_recipe(recipe):
    lines = ["[claim]"]
    for key, value in recipe["claim"].items():
        lines.append(f"{key} = {toml(value)}")
    for step in recipe.get("step", []):
        lines.extend(["", "[[step]]"])
        for key, value in step.items():
            lines.append(f"{key} = {toml(value)}")
    return "\n".join(lines) + "\n"


def short(value, length=12):
    return str(value)[:length]


def duration(seconds):
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.1f}s"


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    if isinstance(when, (int, float)):
        when = datetime.datetime.fromtimestamp(when, datetime.timezone.utc)
    return duration(max(0, (datetime.datetime.now(datetime.timezone.utc) - when).total_seconds())) + " ago"


def table(rows):
    return "\n".join("  ".join(map(str, row)) if not isinstance(row, dict)
                     else "  ".join(map(str, row.values())) for row in rows)


def tree(rows):
    return "\n".join(str(row) for row in rows)


def paint(value, *args, **kwargs):
    return str(value)
