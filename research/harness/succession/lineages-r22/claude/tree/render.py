"""Rendering: the recipe writer, and small text-formatting helpers the
surface layer (CLI, status views) draws on.

`dump_recipe`/`toml` write a parsed recipe dict (the same shape
`kernel.load_recipe` returns) back out as real TOML, so a round trip
through `tomllib.loads` reproduces the same dict -- tables as `[name]`
sections, a list-of-tables value as repeated `[[name]]` array-of-tables
entries, everything else as a scalar/array/inline-table assignment.
`ago`/`duration`/`short`/`table`/`tree`/`paint` are small, independent text
helpers: a relative timestamp, a human duration, a truncated digest, a
plain-text table, an indented tree, and (optionally) ANSI color -- none of
them identity-bearing, all of them display only.
"""
import datetime
import time


def _toml_key(key: str) -> str:
    if key and all(c.isalnum() or c in "_-" for c in key):
        return key
    return _toml_string(key)


def _toml_string(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_toml_key(k)} = {_toml_value(v)}"
                               for k, v in value.items()) + "}"
    raise TypeError(f"cannot serialize value to TOML: {value!r}")


def toml(doc: dict) -> str:
    """A minimal TOML document writer: a dict-valued key becomes a
    `[key]` table, a key whose value is a non-empty list of dicts becomes
    a repeated `[[key]]` array of tables, everything else is a scalar,
    array, or inline-table assignment at the document's root. `tomllib`
    reads any document this writes back into the same dict it started
    from."""
    scalars, tables, array_tables = [], [], []
    for key, value in doc.items():
        if isinstance(value, dict):
            tables.append((key, value))
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            array_tables.append((key, value))
        else:
            scalars.append((key, value))

    lines = []
    for key, value in scalars:
        lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    if scalars:
        lines.append("")
    for key, value in tables:
        lines.append(f"[{_toml_key(key)}]")
        for k, v in value.items():
            lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
        lines.append("")
    for key, items in array_tables:
        for item in items:
            lines.append(f"[[{_toml_key(key)}]]")
            for k, v in item.items():
                lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def dump_recipe(recipe: dict) -> str:
    """A parsed recipe dict, written back out as `reticuli.toml` text --
    the `[claim]` table, then the `[[step]]` array of tables."""
    return toml(recipe)


def short(digest, n: int = 8) -> str:
    """A digest (or any string), truncated to its first `n` characters --
    display only, never used to compare identity."""
    text = digest if isinstance(digest, str) else str(digest)
    return text[:n]


def duration(seconds) -> str:
    """A human-readable span: `"500ms"`, `"12.3s"`, `"3m 4s"`, `"1h 02m"`."""
    seconds = float(seconds)
    if seconds < 1:
        return f"{int(round(seconds * 1000))}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m {rest}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def ago(when) -> str:
    """How long ago `when` (a unix timestamp, or a `YYYY-MM-DDTHH:MM:SSZ`
    string) was, as `"<duration> ago"`, or `"just now"` within one second."""
    if isinstance(when, str):
        ts = datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ") \
            .replace(tzinfo=datetime.timezone.utc).timestamp()
    else:
        ts = float(when)
    delta = max(0.0, time.time() - ts)
    if delta < 1:
        return "just now"
    return f"{duration(delta)} ago"


def table(rows, headers=None) -> str:
    """A plain-text table: `headers` (optional) and every row in `rows`
    rendered as whitespace-padded, left-aligned columns."""
    all_rows = ([list(headers)] if headers else []) + [list(r) for r in rows]
    if not all_rows:
        return ""
    width = max(len(r) for r in all_rows)
    cells = [[str(c) for c in r] + [""] * (width - len(r)) for r in all_rows]
    widths = [max(len(cells[r][c]) for r in range(len(cells))) for c in range(width)]
    lines = ["  ".join(cell.ljust(widths[c]) for c, cell in enumerate(row)).rstrip()
              for row in cells]
    if headers:
        lines.insert(1, "  ".join("-" * widths[c] for c in range(width)))
    return "\n".join(lines)


def tree(obj, *, indent: str = "") -> str:
    """An indented text tree of a nested dict/list/scalar structure."""
    lines = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{indent}{key}:")
                lines.append(tree(value, indent=indent + "  "))
            else:
                lines.append(f"{indent}{key}: {value}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{indent}-")
                lines.append(tree(item, indent=indent + "  "))
            else:
                lines.append(f"{indent}- {item}")
    else:
        lines.append(f"{indent}{obj}")
    return "\n".join(lines)


_COLORS = {
    "red": "31", "green": "32", "yellow": "33",
    "blue": "34", "magenta": "35", "cyan": "36", "gray": "90",
}


def paint(text: str, color: str) -> str:
    """`text` wrapped in the ANSI escape for `color` (one of the names in
    `_COLORS`), or `text` unchanged for an unrecognized color."""
    code = _COLORS.get(color)
    if not code:
        return text
    return f"\033[{code}m{text}\033[0m"
