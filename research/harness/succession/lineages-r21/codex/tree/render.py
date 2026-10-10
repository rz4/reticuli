"""Small, deterministic human-facing renderers and a recipe writer."""

import datetime
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
    raise TypeError(f"cannot write TOML value: {value!r}")


def dump_recipe(parsed):
    lines = []
    for table, value in parsed.items():
        if table == "step":
            for step in value:
                lines.extend(["", "[[step]]"])
                lines.extend(f"{key} = {_value(item)}" for key, item in step.items())
        elif isinstance(value, dict):
            lines.extend(["", f"[{table}]"])
            lines.extend(f"{key} = {_value(item)}" for key, item in value.items())
        else:
            lines.append(f"{table} = {_value(value)}")
    return "\n".join(lines).lstrip("\n") + "\n"


def toml(value):
    return dump_recipe(value) if isinstance(value, dict) and "claim" in value else _value(value)


def short(value, width=12):
    return str(value)[:width]


def duration(seconds):
    seconds = float(seconds)
    return f"{seconds:.1f}s" if seconds < 60 else f"{int(seconds // 60)}m {seconds % 60:.1f}s"


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    if isinstance(when, (int, float)):
        when = datetime.datetime.fromtimestamp(when, datetime.timezone.utc)
    return duration((datetime.datetime.now(datetime.timezone.utc) - when).total_seconds()) + " ago"


def paint(value, *_args, **_kwargs):
    return str(value)


def table(rows, headers=None):
    values = [list(map(str, row)) for row in rows]
    if headers:
        values.insert(0, list(map(str, headers)))
    return "\n".join("  ".join(row) for row in values)


def tree(value, indent=0):
    if isinstance(value, dict):
        return "\n".join(" " * indent + str(key) + ": " + tree(item, indent + 2)
                         for key, item in value.items())
    if isinstance(value, list):
        return "\n".join(" " * indent + "- " + tree(item, indent + 2) for item in value)
    return str(value)
