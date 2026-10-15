"""Small text renderers and a TOML recipe writer."""

import json
import time


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
        return "{ " + ", ".join(f"{_key(k)} = {toml(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot write TOML value {value!r}")


def _key(key):
    return key if key.replace("_", "").replace("-", "").isalnum() and not key[0].isdigit() else json.dumps(key)


def dump_recipe(recipe):
    lines = []
    for section, values in recipe.items():
        if section == "step":
            for step in values:
                lines.extend(("", "[[step]]"))
                lines.extend(f"{_key(k)} = {toml(v)}" for k, v in step.items())
        elif isinstance(values, dict):
            lines.extend(("" if lines else "", f"[{_key(section)}]"))
            lines.extend(f"{_key(k)} = {toml(v)}" for k, v in values.items())
        else:
            lines.append(f"{_key(section)} = {toml(values)}")
    return "\n".join(lines).lstrip("\n") + "\n"


def short(value, length=12):
    value = str(value)
    return value if len(value) <= length else value[:length] + "…"


def duration(seconds):
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def ago(when):
    from datetime import datetime, timezone
    if isinstance(when, str):
        when = datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
    return duration(max(0, time.time() - float(when))) + " ago"


def paint(value, color=None):
    return str(value)


def table(rows, headers=None):
    rows = list(rows)
    if headers is not None:
        rows.insert(0, headers)
    if not rows:
        return ""
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) for row in rows)


def tree(rows, prefix=""):
    return "\n".join(prefix + str(row) for row in rows)
