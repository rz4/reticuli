"""render: turning claim and session state into text (spec/layers.md).

A generic TOML writer (`toml`) is the one function everything else in this
module and `authoring.py`/`pack.py` builds on: it serializes any dict of the
shape `load_recipe` reads back -- scalars, lists, nested dicts (inline
tables), and lists of dicts (arrays of tables) -- into TOML text that
round-trips through `tomllib.loads`. `dump_recipe` is that writer applied to
a parsed recipe, private-loader-key and all, which is what a recipe editor
or a `ret rebuild --without-guidance` diff needs. The rest (`ago`,
`duration`, `paint`, `short`, `table`, `tree`) are the small human-facing
primitives a status line or a CLI report is built from.

Stdlib only.
"""
import time

# ---------------------------------------------------------------------------
# generic TOML writer
# ---------------------------------------------------------------------------


def _toml_string(s: str) -> str:
    escaped = (
        s.replace("\\", "\\\\").replace('"', '\\"')
        .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
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
        return "{ " + ", ".join(f"{k} = {_toml_value(x)}" for k, x in v.items()) + " }"
    raise ValueError(f"cannot serialize {v!r} into TOML")


def toml(obj: dict) -> str:
    """Serialize `obj` -- any dict of scalars, lists, nested dicts, and
    lists-of-dicts -- into TOML text.

    A dict-valued key becomes a `[key]` table; a non-empty list-of-dicts
    becomes one `[[key]]` per item; everything else is a bare top-level
    assignment, written first so the document stays valid TOML (bare keys
    must precede any table header). Round-trips through `tomllib.loads`.
    """
    scalars, tables, array_tables = [], [], []
    for k, v in obj.items():
        if isinstance(v, dict):
            tables.append((k, v))
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            array_tables.append((k, v))
        else:
            scalars.append((k, v))

    lines = [f"{k} = {_toml_value(v)}" for k, v in scalars]
    for k, v in tables:
        lines.append("")
        lines.append(f"[{k}]")
        for kk, vv in v.items():
            lines.append(f"{kk} = {_toml_value(vv)}")
    for k, arr in array_tables:
        for item in arr:
            lines.append("")
            lines.append(f"[[{k}]]")
            for kk, vv in item.items():
                lines.append(f"{kk} = {_toml_value(vv)}")
    return "\n".join(lines) + "\n"


def dump_recipe(doc: dict) -> str:
    """A parsed recipe (`kernel.load_recipe`'s return, private `_dir` key
    included) as TOML text -- `toml(doc)` under the one shape a recipe ever
    takes."""
    return toml(doc)


# ---------------------------------------------------------------------------
# small human-facing primitives
# ---------------------------------------------------------------------------


def short(value: str, n: int = 12) -> str:
    """The first `n` characters of a hash-like string, ellipsized if it was
    longer -- `spec/identity.md`'s worked example shortens its root the
    same way (`03d039ca6878609359e5770866377edf40a26eff48bdb1147e300aecee26f175`
    to `03d039ca6878…`)."""
    if len(value) <= n:
        return value
    return value[:n] + "…"


def ago(ts: float, now: float = None) -> str:
    """A human-readable relative time: `"5s ago"`, `"3m ago"`, `"2h ago"`,
    `"1d ago"`."""
    if now is None:
        now = time.time()
    delta = max(0.0, now - ts)
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def duration(seconds: float) -> str:
    """A human-readable span: `"2.3s"`, `"1m 5s"`, `"2h 3m"`."""
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


_COLORS = {
    "red": "31", "green": "32", "yellow": "33", "blue": "34",
    "magenta": "35", "cyan": "36", "dim": "2", "bold": "1",
}


def paint(text: str, color: str) -> str:
    """`text` wrapped in the ANSI escape for `color`; an unknown color name
    returns `text` unchanged rather than raising."""
    code = _COLORS.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def table(rows, headers=None) -> str:
    """A plain-text, column-aligned table; `headers`, if given, is the
    first row."""
    data = [list(map(str, r)) for r in rows]
    if headers:
        data = [list(map(str, headers))] + data
    if not data:
        return ""
    width = max(len(row) for row in data)
    widths = [max((len(row[i]) if i < len(row) else 0) for row in data)
              for i in range(width)]
    lines = []
    for row in data:
        cells = [row[i].ljust(widths[i]) if i < len(row) else "".ljust(widths[i])
                 for i in range(width)]
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def tree(node: dict, prefix: str = "") -> str:
    """A nested `{"label": str, "children": [node, ...]}` structure as an
    ASCII tree (`├──` / `└──` connectors)."""
    lines = [str(node.get("label", ""))]
    children = node.get("children") or []
    for i, child in enumerate(children):
        last = i == len(children) - 1
        connector = "└── " if last else "├── "
        sub_prefix = prefix + ("    " if last else "│   ")
        child_lines = tree(child, sub_prefix).split("\n")
        lines.append(prefix + connector + child_lines[0])
        lines.extend(child_lines[1:])
    return "\n".join(lines)
