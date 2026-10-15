"""Presentation helpers for the authoring layer.

Small formatting primitives for human-facing output (`ago`, `duration`,
`paint`, `short`, `table`, `tree`) and a minimal TOML writer (`toml`) used
to serialize a claim's recipe back to disk (`dump_recipe`) -- the one
function that must agree with `tomllib` after a round trip
(`spec/claim-format.md`).

Stdlib only.
"""
import re
import time

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

# -- small formatting helpers -------------------------------------------------


def short(s: str, n: int = 8) -> str:
    """The first `n` characters of a hash or identifier, for display."""
    return s[:n] if s else s


def duration(seconds) -> str:
    """A wall-clock span as a compact human string, e.g. `1h2m3s`."""
    seconds = float(seconds)
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return sign + "".join(parts)


def ago(ts) -> str:
    """How long before now `ts` (a unix timestamp) was."""
    return f"{duration(max(0.0, time.time() - float(ts)))} ago"


_COLORS = {"red": "31", "green": "32", "yellow": "33",
           "blue": "34", "magenta": "35", "cyan": "36"}


def paint(text: str, color: str = None) -> str:
    """Wrap `text` in an ANSI color code; a no-op with no recognized color."""
    code = _COLORS.get(color)
    if not code:
        return text
    return f"\033[{code}m{text}\033[0m"


def table(rows, headers=None) -> str:
    """A simple column-aligned text table."""
    rows = [[str(c) for c in r] for r in rows]
    all_rows = ([list(headers)] + rows) if headers else rows
    if not all_rows:
        return ""
    width_n = len(all_rows[0])
    widths = [max(len(r[i]) for r in all_rows) for i in range(width_n)]
    lines = []
    for i, r in enumerate(all_rows):
        lines.append("  ".join(c.ljust(w) for c, w in zip(r, widths)))
        if headers and i == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def tree(entries, indent: str = "") -> str:
    """Render a nested `{name: subtree_or_None}` mapping as an indented tree."""
    items = list(entries.items()) if isinstance(entries, dict) else list(entries)
    lines = []
    for i, item in enumerate(items):
        name, children = item if isinstance(item, tuple) else (item, None)
        last = i == len(items) - 1
        branch = "└── " if last else "├── "
        lines.append(f"{indent}{branch}{name}")
        if children:
            next_indent = indent + ("    " if last else "│   ")
            sub = tree(children, next_indent)
            if sub:
                lines.append(sub)
    return "\n".join(lines)


# -- a minimal TOML writer -----------------------------------------------------


def _toml_key(k: str) -> str:
    return k if _BARE_KEY.match(k) else _toml_string(k)


def _toml_string(s: str) -> str:
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _toml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return _toml_string(v)
    raise TypeError(f"cannot serialize {v!r} as a TOML scalar")


def _toml_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(
            f"{_toml_key(k)} = {_toml_value(x)}" for k, x in v.items()
        ) + " }"
    return _toml_scalar(v)


def toml(doc: dict) -> str:
    """Render a document (plain tables and arrays of tables, as a claim's
    recipe uses) as TOML text."""
    lines = []
    for key, value in doc.items():
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for k, v in value.items():
                lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
            lines.append("")
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            for item in value:
                lines.append(f"[[{key}]]")
                for k, v in item.items():
                    lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
                lines.append("")
        else:
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    return "\n".join(lines)


def dump_recipe(recipe: dict) -> str:
    """A claim's recipe, rendered as TOML -- round-trips through `tomllib`
    back to an equal structure (`spec/claim-format.md`)."""
    return toml(recipe)
