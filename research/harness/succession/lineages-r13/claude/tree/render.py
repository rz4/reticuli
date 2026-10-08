"""Rendering: a faithful TOML writer for a parsed recipe, and small text
helpers the surface layer (CLI) uses to show a human a claim, a cost, or a
dependency tree (spec/layers.md's authoring layer).

`toml` is a general, two-level TOML writer: a top-level dict value becomes a
`[section]`, a top-level list of dicts becomes repeated `[[section]]`
entries, and anything nested inside either (a plain scalar, a list, or an
inline table) is written with `_toml_value` -- never promoted to a section
of its own. That is exactly `reticuli.toml`'s own shape (`[claim]` plus
repeated `[[step]]`), so `dump_recipe` is `toml` under a recipe-specific
name: what a recipe writer commits to is round-tripping byte-for-byte
through `tomllib.loads`, not a different serialization.
"""
import time

# --------------------------------------------------------------- toml --

def _toml_string(s: str) -> str:
    """A TOML basic string literal for `s`."""
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


def _toml_key(k: str) -> str:
    if k and all(c.isalnum() or c in "_-" for c in k):
        return k
    return _toml_string(k)


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return _toml_string(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        return "{ " + ", ".join(
            f"{_toml_key(k2)} = {_toml_value(v2)}" for k2, v2 in v.items()
        ) + " }"
    raise ValueError(f"cannot render {v!r} as TOML")


def _toml_table_body(table: dict) -> list:
    return [f"{_toml_key(k)} = {_toml_value(v)}" for k, v in table.items()]


def toml(doc: dict) -> str:
    """A document whose top-level values are either a table (becomes a
    `[section]`), a non-empty list of tables (becomes repeated
    `[[section]]` entries), or a scalar -- exactly the shape a recipe is."""
    lines = []
    for key, value in doc.items():
        if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
            for item in value:
                lines.append(f"[[{_toml_key(key)}]]")
                lines.extend(_toml_table_body(item))
                lines.append("")
        elif isinstance(value, dict):
            lines.append(f"[{_toml_key(key)}]")
            lines.extend(_toml_table_body(value))
            lines.append("")
        else:
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    text = "\n".join(lines).rstrip("\n")
    return text + "\n"


def dump_recipe(recipe: dict) -> str:
    """A recipe written as TOML, byte-parseable back into the same dict
    (`tomllib.loads(dump_recipe(r)) == r`) -- the renderer's one identity
    commitment; comments and key order are free."""
    return toml(recipe)


# ------------------------------------------------------------- display --

def ago(ts: float, now: float = None) -> str:
    """A short "<n> <unit> ago" rendering of a UNIX timestamp."""
    if now is None:
        now = time.time()
    delta = max(0.0, now - ts)
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if delta >= size:
            n = int(delta // size)
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    n = int(delta)
    return f"{n} second{'s' if n != 1 else ''} ago"


def duration(seconds: float) -> str:
    """A compact "1h2m3s"-style rendering of a span of seconds."""
    whole = int(max(0.0, float(seconds)))
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return "".join(parts)


_COLORS = {"red": 31, "green": 32, "yellow": 33, "blue": 34, "magenta": 35, "cyan": 36}


def paint(text: str, color: str = None) -> str:
    """Wrap `text` in an ANSI color code; `color=None` (or unknown) returns
    it unchanged."""
    code = _COLORS.get(color)
    if code is None:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def short(s: str, n: int = 12) -> str:
    """The first `n` characters of `s`, ellipsised if it was longer --
    for showing a root or a digest without the full 64 hex characters."""
    if len(s) <= n:
        return s
    return s[:n] + "…"


def table(rows, columns: list = None) -> str:
    """A plain-text table: a header row, a rule, then one row per entry."""
    rows = list(rows)
    if not rows:
        return ""
    cols = columns or list(rows[0].keys())
    widths = {c: max([len(c)] + [len(str(r.get(c, ""))) for r in rows]) for c in cols}

    def _line(values):
        return "  ".join(str(v).ljust(widths[c]) for c, v in zip(cols, values))

    lines = [_line(cols), _line(["-" * widths[c] for c in cols])]
    for r in rows:
        lines.append(_line([r.get(c, "") for c in cols]))
    return "\n".join(lines)


def tree(node: dict, prefix: str = "") -> str:
    """An indented tree rendering of `{"name": ..., "children": [...]}`-shaped
    data -- a dependency DAG, a component chain."""
    lines = [prefix + str(node.get("name", ""))]
    children = node.get("children") or []
    for i, child in enumerate(children):
        last = i == len(children) - 1
        branch = "└── " if last else "├── "
        sub_lines = tree(child, "").splitlines()
        lines.append(prefix + branch + sub_lines[0])
        for extra in sub_lines[1:]:
            lines.append(prefix + ("    " if last else "│   ") + extra)
    return "\n".join(lines)
