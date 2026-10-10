"""Small text renderers, including the authoring recipe writer."""

from __future__ import annotations

import json
import re


def _key(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z0-9_-]+", value) else json.dumps(value)


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
        return "{ " + ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot render TOML value: {value!r}")


def dump_recipe(recipe: dict) -> str:
    lines = ["[claim]"]
    for key, value in recipe["claim"].items():
        lines.append(f"{_key(key)} = {_value(value)}")
    for step in recipe.get("step", []):
        lines.extend(("", "[[step]]"))
        for key, value in step.items():
            lines.append(f"{_key(key)} = {_value(value)}")
    return "\n".join(lines) + "\n"


def toml(value):
    return dump_recipe(value) if isinstance(value, dict) and "claim" in value else _value(value)


def short(value, length=12):
    return str(value)[:length]


def duration(seconds):
    return f"{seconds:.1f}s"


def ago(seconds):
    return duration(seconds) + " ago"


def paint(text, *args, **kwargs):
    return str(text)


def table(rows, columns=None):
    rows = list(rows)
    if not rows:
        return ""
    columns = columns or list(rows[0])
    return "\n".join("  ".join(str(row.get(key, "")) for key in columns) for row in rows)


def tree(rows):
    return "\n".join(str(row) for row in rows)
