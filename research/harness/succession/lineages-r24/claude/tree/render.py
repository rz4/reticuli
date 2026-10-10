"""render: turning claim data into bytes and text (spec/layers.md "authoring").

`dump_recipe` is the authoring layer's TOML writer: given a parsed recipe
dict (the shape `kernel.load_recipe` returns), it writes TOML text that
`tomllib.loads` parses back into an equal dict -- the recipe round-trip the
rest of this layer depends on to author claims byte-for-byte. The remaining
functions are small, stdlib-only display helpers for a CLI surface above
this layer (human-readable durations, short hashes, plain tables, a
dependency tree); none of them touch identity.
"""
import time as _time


# -- TOML value serialization: only what a recipe's own shapes need --------

def _toml_string(s: str) -> str:
    out = ['"']
    for ch in s:
        cp = ord(ch)
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
        elif cp < 0x20 or cp == 0x7F:
            out.append("\\u%04x" % cp)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


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
        return "{" + ", ".join(f"{k} = {_toml_value(vv)}" for k, vv in v.items()) + "}"
    raise ValueError(f"cannot render a {type(v).__name__} value as TOML")


def dump_recipe(recipe: dict) -> str:
    """A parsed recipe dict as TOML text, parseable back into an equal
    dict (`tomllib.loads(dump_recipe(r)) == r`)."""
    lines = ["[claim]"]
    claim = recipe.get("claim", {})
    for k in sorted(claim):
        lines.append(f"{k} = {_toml_value(claim[k])}")
    for step in recipe.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for k in sorted(step):
            lines.append(f"{k} = {_toml_value(step[k])}")
    return "\n".join(lines) + "\n"


def toml(obj: dict) -> str:
    """A generic dict as TOML text: scalars first, then nested tables
    (`[name]`), then lists of tables (`[[name]]`) -- for data that is not a
    recipe's own claim/step shape."""
    scalars, tables, arrays = {}, {}, {}
    for k, v in obj.items():
        if isinstance(v, dict):
            tables[k] = v
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            arrays[k] = v
        else:
            scalars[k] = v
    lines = [f"{k} = {_toml_value(scalars[k])}" for k in sorted(scalars)]
    for k in sorted(tables):
        lines.append("")
        lines.append(f"[{k}]")
        for kk in sorted(tables[k]):
            lines.append(f"{kk} = {_toml_value(tables[k][kk])}")
    for k in sorted(arrays):
        for item in arrays[k]:
            lines.append("")
            lines.append(f"[[{k}]]")
            for kk in sorted(item):
                lines.append(f"{kk} = {_toml_value(item[kk])}")
    return "\n".join(lines) + "\n"


# -- small display helpers for a CLI surface above this layer ---------------

def duration(seconds) -> str:
    """A human-readable span, e.g. `250ms`, `3.4s`, `2m5s`, `1h03m`."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "?"
    if s < 0:
        s = 0.0
    if s < 1:
        return f"{s * 1000:.0f}ms"
    if s < 60:
        return f"{s:.1f}s"
    minutes, secs = divmod(int(s), 60)
    if minutes < 60:
        return f"{minutes}m{secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def ago(ts) -> str:
    """How long ago a unix timestamp was, e.g. `3.4s ago`."""
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return "unknown"
    delta = _time.time() - ts
    return f"{duration(delta)} ago"


_PAINT_CODES = {"red": "31", "green": "32", "yellow": "33",
                "blue": "34", "magenta": "35", "cyan": "36"}


def paint(text: str, color: str = None) -> str:
    """`text` wrapped in an ANSI color code, or unchanged if `color` is
    `None` or unrecognized -- never required for correctness, only display."""
    code = _PAINT_CODES.get(color)
    return text if code is None else f"\033[{code}m{text}\033[0m"


def short(value, length: int = 12) -> str:
    """The first `length` characters of `value`'s string form -- a root or
    digest shortened for display."""
    s = str(value)
    return s if len(s) <= length else s[:length]


def table(rows, headers=None) -> str:
    """A plain fixed-width text table over `rows` (each an iterable of
    cells), with an optional header row."""
    body = [[str(c) for c in row] for row in rows]
    all_rows = ([[str(h) for h in headers]] + body) if headers else body
    if not all_rows:
        return ""
    width = max(len(r) for r in all_rows)
    widths = [max((len(r[i]) for r in all_rows if i < len(r)), default=0)
              for i in range(width)]
    lines = []
    for i, row in enumerate(all_rows):
        lines.append("  ".join(c.ljust(widths[j]) for j, c in enumerate(row)))
        if headers and i == 0:
            lines.append("  ".join("-" * widths[j] for j in range(len(row))))
    return "\n".join(lines)


def tree(dag: dict) -> str:
    """A dependency DAG (`registry.deps`'s shape: `{"claims": [{"name",
    "depends_on": [...]}]}`) as an indented text tree."""
    claims = dag.get("claims", []) if isinstance(dag, dict) else []
    lines = []
    for c in claims:
        lines.append(str(c.get("name")))
        for dep in c.get("depends_on", []) or []:
            lines.append(f"  -> {dep.get('component')} ({dep.get('status')})")
    return "\n".join(lines)
