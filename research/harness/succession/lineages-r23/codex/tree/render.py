"""Small human-readable renderers and a TOML recipe writer."""
import datetime
import json
import re


def _key(value):
    return value if re.fullmatch(r"[A-Za-z0-9_-]+", value) else json.dumps(value)


def _value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(map(_value, value)) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot render TOML value: {value!r}")


def dump_recipe(recipe):
    lines = []
    for name, fields in recipe.items():
        if name == "step":
            for step in fields:
                lines.append("[[step]]")
                lines.extend(f"{_key(k)} = {_value(v)}" for k, v in step.items())
                lines.append("")
        elif isinstance(fields, dict):
            lines.append(f"[{_key(name)}]")
            lines.extend(f"{_key(k)} = {_value(v)}" for k, v in fields.items())
            lines.append("")
        else:
            lines.append(f"{_key(name)} = {_value(fields)}")
    return "\n".join(lines).rstrip() + "\n"


toml = dump_recipe


def short(value, length=12):
    value = str(value)
    return value if len(value) <= length else value[:length] + "…"


def duration(seconds):
    return f"{seconds:.1f}s"


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    return duration((datetime.datetime.now(datetime.timezone.utc) - when).total_seconds()) + " ago"


def paint(text, color=None):
    return str(text)


def table(rows, columns=None):
    rows = list(rows)
    if not rows:
        return ""
    if columns is None:
        columns = list(rows[0]) if isinstance(rows[0], dict) else list(range(len(rows[0])))
    values = [[str(row[c]) for c in columns] for row in rows]
    return "\n".join("  ".join(row) for row in values)


def tree(rows, indent=0):
    return "\n".join(" " * indent + str(row) for row in rows)
