"""render: turning claim/registry data into text (spec/layers.md).

A small CLI toolkit the surface layer builds on: human-readable durations
and "time ago" strings, shortened hashes, optional ANSI color, simple text
tables and trees, and a TOML writer for recipe-shaped dicts. No layer below
this one needs it. Stdlib only.
"""
import time

# -- time -------------------------------------------------------------------

_AGO_UNITS = (
    ("year", 31536000),
    ("month", 2592000),
    ("day", 86400),
    ("hour", 3600),
    ("minute", 60),
)


def ago(ts: float) -> str:
    """A human "time ago" string for a unix timestamp."""
    delta = max(0.0, time.time() - ts)
    for unit, seconds in _AGO_UNITS:
        if delta >= seconds:
            n = int(delta // seconds)
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


def duration(seconds: float) -> str:
    """A human duration string, `1h2m3s` style."""
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    whole = int(seconds)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return "".join(parts)


# -- color --------------------------------------------------------------

_COLORS = {"red": "31", "green": "32", "yellow": "33", "blue": "34",
           "magenta": "35", "cyan": "36", "gray": "90"}


def paint(text: str, color: str = None) -> str:
    """`text` wrapped in an ANSI color code, or unchanged if `color` is
    unknown or absent."""
    code = _COLORS.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def short(digest: str, n: int = 8) -> str:
    """The first `n` characters of a hash, for display."""
    return (digest or "")[:n]


# -- tabular text -------------------------------------------------------

def table(rows, headers=None) -> str:
    """A simple, aligned text table."""
    rows = [[str(c) for c in row] for row in rows]
    all_rows = ([list(headers)] + rows) if headers else rows
    if not all_rows:
        return ""
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(all_rows[0]))]

    def fmt(row):
        return "  ".join(c.ljust(w) for c, w in zip(row, widths))

    lines = []
    if headers:
        lines.append(fmt([str(h) for h in headers]))
        lines.append("  ".join("-" * w for w in widths))
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def tree(nodes, name_key="name", children_key="depends_on", child_name_key="component") -> str:
    """A simple indented tree over `registry.deps()`-shaped data."""
    lines = []
    for node in nodes:
        lines.append(str(node.get(name_key, "")))
        for child in node.get(children_key) or []:
            label = child.get(child_name_key, child) if isinstance(child, dict) else child
            lines.append(f"  └─ {label}")
    return "\n".join(lines)


# -- TOML ---------------------------------------------------------------

def _toml_escape(text: str) -> str:
    out = []
    for ch in text:
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
    return "".join(out)


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return '"' + _toml_escape(value) + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot render {value!r} as TOML")


def toml(doc: dict) -> str:
    """`doc` (a TOML-shaped dict: tables, arrays, scalars) as TOML text a
    conforming reader parses back to an equal structure."""
    return "\n".join(f"{key} = {_toml_value(value)}" for key, value in doc.items()) + "\n"


def dump_recipe(recipe: dict) -> str:
    """A parsed recipe (`[claim]` table, `[[step]]` array) as TOML text."""
    return toml(recipe)
