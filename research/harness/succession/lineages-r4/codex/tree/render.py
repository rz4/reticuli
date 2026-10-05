"""Small text renderers and a TOML recipe writer."""

import datetime
import json


def toml(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {toml(item)}" for key, item in value.items()) + " }"
    raise TypeError(f"cannot write TOML value: {type(value).__name__}")


def dump_recipe(recipe):
    lines = []
    for section, value in recipe.items():
        if section == "step":
            for step in value:
                lines.extend(("", "[[step]]"))
                lines.extend(f"{key} = {toml(item)}" for key, item in step.items())
        elif isinstance(value, dict):
            lines.extend((f"[{section}]",))
            lines.extend(f"{key} = {toml(item)}" for key, item in value.items())
        else:
            lines.append(f"{section} = {toml(value)}")
    return "\n".join(lines).lstrip("\n") + "\n"


def short(value, width=12):
    return str(value)[:width]


def duration(seconds):
    seconds = float(seconds)
    return f"{seconds:.1f}s"


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    delta = datetime.datetime.now(datetime.timezone.utc) - when
    return duration(delta.total_seconds()) + " ago"


def paint(value, *args, **kwargs):
    return str(value)


def table(rows, *args, **kwargs):
    return "\n".join("  ".join(map(str, row)) if not isinstance(row, str) else row for row in rows)


def tree(rows, *args, **kwargs):
    return "\n".join(map(str, rows))
