"""Small display helpers and a TOML writer for claim recipes."""
from __future__ import annotations

import datetime as _datetime
import json
from typing import Any


def toml(value: Any) -> str:
    """Represent a JSON-like value in TOML syntax."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {toml(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot write TOML value: {value!r}")


def dump_recipe(recipe: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in recipe.items():
        if key == "step":
            for step in value:
                lines.append("[[step]]")
                lines.extend(f"{json.dumps(k)} = {toml(v)}" for k, v in step.items())
                lines.append("")
        elif isinstance(value, dict):
            lines.append(f"[{json.dumps(key)}]")
            lines.extend(f"{json.dumps(k)} = {toml(v)}" for k, v in value.items())
            lines.append("")
        else:
            lines.append(f"{json.dumps(key)} = {toml(value)}")
    return "\n".join(lines) + "\n"


def short(value: Any, length: int = 12) -> str:
    value = str(value)
    return value if len(value) <= length else value[:length] + "…"


def duration(seconds: float) -> str:
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {rest:.0f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


def ago(when: Any) -> str:
    if isinstance(when, (int, float)):
        when = _datetime.datetime.fromtimestamp(when, _datetime.timezone.utc)
    elif isinstance(when, str):
        when = _datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    now = _datetime.datetime.now(_datetime.timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=_datetime.timezone.utc)
    return duration(max(0, (now - when).total_seconds())) + " ago"


def paint(value: Any, *args: Any, **kwargs: Any) -> str:
    return str(value)


def table(rows: Any, headers: Any = None) -> str:
    rows = list(rows)
    if headers is not None:
        rows.insert(0, headers)
    return "\n".join("  ".join(map(str, row)) for row in rows)


def tree(value: Any, prefix: str = "") -> str:
    if isinstance(value, dict):
        return "\n".join(prefix + str(key) + ": " + tree(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return "\n".join(prefix + str(item) for item in value)
    return str(value)
