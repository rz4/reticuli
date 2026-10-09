"""Small human-facing renderers and a lossless recipe writer."""
import json
import re
import time
import tomllib

from . import kernel


def _key(value):
    return value if re.fullmatch(r"[A-Za-z0-9_-]+", value) else json.dumps(value)


def toml(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(map(toml, value)) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_key(k)} = {toml(v)}" for k, v in value.items()) + " }"
    raise kernel.ClaimError(f"cannot write TOML value: {value!r}")


def dump_recipe(document):
    lines = []
    for key, value in document.items():
        if isinstance(value, dict):
            lines.append(f"[{_key(key)}]")
            lines.extend(f"{_key(k)} = {toml(v)}" for k, v in value.items())
            lines.append("")
        elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
            for item in value:
                lines.append(f"[[{_key(key)}]]")
                lines.extend(f"{_key(k)} = {toml(v)}" for k, v in item.items())
                lines.append("")
        else:
            lines.append(f"{_key(key)} = {toml(value)}")
    result = "\n".join(lines).rstrip() + "\n"
    if tomllib.loads(result) != document:
        raise kernel.ClaimError("recipe changed while rendering")
    return result


def short(value, length=12):
    return str(value)[:length]


def duration(seconds):
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:g}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {seconds:g}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


def ago(when):
    if isinstance(when, (int, float)):
        return duration(max(0, time.time() - when)) + " ago"
    return str(when)


def paint(value, color=None):
    return str(value)


def table(rows, columns=None):
    rows = list(rows)
    if not rows:
        return ""
    columns = list(columns or (rows[0].keys() if isinstance(rows[0], dict) else range(len(rows[0]))))
    cells = [[str(row.get(column, "")) if isinstance(row, dict) else str(row[column]) for column in columns] for row in rows]
    widths = [max(len(str(column)), *(len(row[i]) for row in cells)) for i, column in enumerate(columns)]
    return "\n".join(["  ".join(str(c).ljust(widths[i]) for i, c in enumerate(columns))] +
                     ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in cells])


def tree(value, indent=0):
    if isinstance(value, dict):
        return "\n".join(" " * indent + str(k) + ": " + ("\n" + tree(v, indent + 2) if isinstance(v, (dict, list)) else str(v)) for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(" " * indent + "- " + ("\n" + tree(v, indent + 2) if isinstance(v, (dict, list)) else str(v)) for v in value)
    return " " * indent + str(value)
