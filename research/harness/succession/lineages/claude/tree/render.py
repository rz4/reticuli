"""reticuli.render -- turning claim data into text a human reads
(`spec/layers.md`).

`dump_recipe` (and the `toml` primitive it is built on) is the recipe
writer: the inverse of `tomllib.load`, so a recipe a layer above builds as
a plain dict can be written to disk and read back byte-for-byte
equivalent. The rest (`ago`, `duration`, `paint`, `short`, `table`,
`tree`) are small, independent formatting helpers for a CLI surface above
this layer -- human-readable relative times, wall-clock spans, terminal
color, shortened digests, tables, and indented trees. None of them touch
identity; they only ever describe it.
"""
import os
import time

# ---------------------------------------------------------------------------
# toml / dump_recipe: rendering a parsed recipe (or any plain dict of
# tables) back to TOML text. Values round-trip through `tomllib.loads`
# unchanged; key and section ORDER is free, since dict equality does not
# care about it.
# ---------------------------------------------------------------------------
def _toml_key(key: str) -> str:
    if key and all(c.isalnum() or c in "_-" for c in key):
        return key
    return _toml_string(key)


def _toml_string(s: str) -> str:
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return _toml_string(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        inner = ", ".join(f"{_toml_key(k)} = {_toml_value(x)}" for k, x in v.items())
        return "{" + inner + "}"
    raise ValueError(f"cannot render {v!r} as TOML")


def toml(doc: dict) -> str:
    """Render a parsed document (`[section]` tables, `[[array]]` of
    tables, and scalar keys) as TOML text."""
    lines = []
    for key, value in doc.items():
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for k2, v2 in value.items():
                lines.append(f"{_toml_key(k2)} = {_toml_value(v2)}")
            lines.append("")
        elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
            for item in value:
                lines.append(f"[[{key}]]")
                for k2, v2 in item.items():
                    lines.append(f"{_toml_key(k2)} = {_toml_value(v2)}")
                lines.append("")
        else:
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    return "\n".join(lines).rstrip("\n") + "\n"


def dump_recipe(recipe: dict) -> str:
    """A recipe dict (`[claim]` table, `[[step]]` array), as TOML text --
    the inverse of `reticuli.kernel.load_recipe`."""
    return toml(recipe)


# ---------------------------------------------------------------------------
# Small formatting helpers for a CLI surface
# ---------------------------------------------------------------------------
def ago(ts: float, *, now: float = None) -> str:
    """A rough human phrase for how long ago a unix timestamp was."""
    if now is None:
        now = time.time()
    delta = max(0.0, now - ts)
    for unit, size in (("year", 31536000), ("week", 604800), ("day", 86400),
                       ("hour", 3600), ("minute", 60)):
        if delta >= size:
            n = int(delta // size)
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


def duration(seconds: float) -> str:
    """A wall-clock span as a short string, e.g. `1h2m3s`."""
    seconds = float(seconds)
    if seconds < 60:
        return f"{int(seconds)}s" if seconds == int(seconds) else f"{seconds:.1f}s"
    minutes, s = divmod(int(seconds), 60)
    hours, m = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if hours or m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return "".join(parts)


_COLORS = {"red": "31", "green": "32", "yellow": "33", "blue": "34", "cyan": "36", "gray": "90"}


def paint(text: str, color: str = None) -> str:
    """`text` wrapped in an ANSI color code; unchanged if `color` is
    unknown or `NO_COLOR` is set."""
    code = _COLORS.get(color)
    if not code or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


def short(digest: str, n: int = 8) -> str:
    """The first `n` characters of a hex digest, for display."""
    return digest[:n] if digest else ""


def table(rows, headers=None) -> str:
    """A plain, space-aligned text table."""
    rows = [[str(c) for c in r] for r in rows]
    if headers:
        rows = [[str(h) for h in headers]] + rows
    if not rows:
        return ""
    width = len(rows[0])
    widths = [max(len(r[i]) for r in rows) for i in range(width)]
    lines = []
    for i, r in enumerate(rows):
        lines.append("  ".join(cell.ljust(widths[j]) for j, cell in enumerate(r)))
        if headers and i == 0:
            lines.append("  ".join("-" * widths[j] for j in range(width)))
    return "\n".join(lines)


def tree(node, *, indent: str = "") -> str:
    """A nested dict rendered as an indented tree of its keys."""
    if not isinstance(node, dict):
        return f"{indent}{node}"
    lines = []
    items = list(node.items())
    for i, (key, value) in enumerate(items):
        last = i == len(items) - 1
        lines.append(f"{indent}{'`-- ' if last else '|-- '}{key}")
        if isinstance(value, dict) and value:
            lines.append(tree(value, indent=indent + ("    " if last else "|   ")))
    return "\n".join(lines)
