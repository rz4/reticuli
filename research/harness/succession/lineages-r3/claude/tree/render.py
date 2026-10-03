"""Rendering: recipe text, and small human-facing display helpers
(spec/layers.md: "render's recipe writer").

`dump_recipe` is the one byte-sensitive function here: it serializes a
parsed recipe (`[claim]` table, `[[step]]` entries -- `kernel.load_recipe`'s
return shape) back to TOML text that round-trips through `tomllib.loads` to
the same document. `toml` is the same value serialization, generically, for
any mapping a caller wants to write as plain `key = value` lines. Both write
nested structure (lists, tables) as TOML inline tables/arrays, so no section
header ever needs to come before or after another in a particular order.

`ago`/`duration`/`paint`/`short`/`table`/`tree` are small display helpers
for the surface layer (the CLI); nothing above the kernel depends on their
exact output, so they stay simple.
"""
import datetime
import os

# -- TOML value serialization (shared by `toml` and `dump_recipe`) ---------


def _dump_string(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == '"':
            out.append('\\"')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\t':
            out.append('\\t')
        elif ch == '\r':
            out.append('\\r')
        elif ord(ch) < 0x20:
            out.append(f'\\u{ord(ch):04x}')
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _dump_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return _dump_string(v)
    if isinstance(v, list):
        return "[" + ", ".join(_dump_value(i) for i in v) + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        return "{ " + ", ".join(f"{k} = {_dump_value(x)}" for k, x in v.items()) + " }"
    raise ValueError(f"unsupported TOML value: {v!r}")


def toml(obj: dict) -> str:
    """`obj` as TOML text: every top-level key its own `key = value` line,
    nested dicts and lists written inline (no section header), so the
    result round-trips through `tomllib.loads` regardless of nesting.
    """
    lines = [f"{k} = {_dump_value(v)}" for k, v in obj.items()]
    return "\n".join(lines) + ("\n" if lines else "")


def dump_recipe(doc: dict) -> str:
    """A parsed recipe (`kernel.load_recipe`'s return shape) as the
    `reticuli.toml` text that would produce it: `[claim]` as a table, each
    `[[step]]` as an array-of-tables entry, everything else inline --
    round-trips through `tomllib.loads` back to the same document.
    """
    lines = []
    claim = doc.get("claim")
    if isinstance(claim, dict):
        lines.append("[claim]")
        for k, v in claim.items():
            lines.append(f"{k} = {_dump_value(v)}")
    for step in doc.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for k, v in step.items():
            lines.append(f"{k} = {_dump_value(v)}")
    for k, v in doc.items():
        if k in ("claim", "step"):
            continue
        lines.append(f"{k} = {_dump_value(v)}")
    return "\n".join(lines) + "\n"


# -- Small display helpers ---------------------------------------------------

_COLORS = {"red": "31", "green": "32", "yellow": "33", "blue": "34",
           "magenta": "35", "cyan": "36", "dim": "2", "bold": "1"}


def paint(text: str, color: str) -> str:
    """`text` wrapped in an ANSI escape for `color`; unchanged when
    `color` is not recognized or `NO_COLOR` is set in the environment.
    """
    code = _COLORS.get(color)
    if not code or os.environ.get("NO_COLOR"):
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def short(value: str, n: int = 8) -> str:
    """The first `n` characters of `value` -- a digest shortened for
    display; `value` unchanged when it is already that short or shorter.
    """
    return value[:n]


def duration(seconds) -> str:
    """`seconds` as a short human-readable span: sub-minute as a plain
    `"<n>.<ff>s"`, otherwise `"<h>h <m>m <s>s"` with a leading absent
    hour unit dropped.
    """
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.2f}s"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if hours or minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def ago(when) -> str:
    """How long ago `when` was, as `"<n> <unit> ago"`. `when` is either a
    record-style UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`, spec/record.md) or
    a Unix epoch number.
    """
    if isinstance(when, str):
        moment = datetime.datetime.strptime(
            when, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    else:
        moment = datetime.datetime.fromtimestamp(float(when), tz=datetime.timezone.utc)
    secs = (datetime.datetime.now(datetime.timezone.utc) - moment).total_seconds()
    if secs < 0:
        return "just now"
    for unit, size in (("year", 31536000), ("month", 2592000), ("day", 86400),
                       ("hour", 3600), ("minute", 60)):
        if secs >= size:
            n = int(secs // size)
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


def table(rows, headers=None) -> str:
    """A simple aligned text table. `rows` is a list of dicts (columns
    are `headers`, or each dict's own keys in first-seen order) or a list
    of equal-length lists/tuples (columns are `headers`, when given).
    """
    rows = list(rows)
    if not rows:
        return ""
    if isinstance(rows[0], dict):
        if headers is None:
            headers = []
            for row in rows:
                for k in row:
                    if k not in headers:
                        headers.append(k)
        grid = [[str(row.get(h, "")) for h in headers] for row in rows]
    else:
        grid = [[str(cell) for cell in row] for row in rows]

    cols = headers if headers is not None else [f"col{i}" for i in range(len(grid[0]))]
    widths = [len(str(c)) for c in cols]
    for row in grid:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _fmt(cells):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = []
    if headers is not None:
        lines.append(_fmt([str(c) for c in cols]))
        lines.append("  ".join("-" * w for w in widths))
    for row in grid:
        lines.append(_fmt(row))
    return "\n".join(lines)


def tree(forest) -> str:
    """A forest of `(label, children)` pairs (`children` the same shape,
    recursively; a bare string is a leaf with no children) rendered as
    indented lines with `tree(1)`-style connectors.
    """
    def _norm(node):
        if isinstance(node, str):
            return node, []
        label, children = node
        return label, list(children or [])

    lines = []

    def _walk(nodes, prefix):
        nodes = [_norm(n) for n in nodes]
        for i, (label, children) in enumerate(nodes):
            last = i == len(nodes) - 1
            lines.append(prefix + ("└── " if last else "├── ") + str(label))
            _walk(children, prefix + ("    " if last else "│   "))

    _walk(forest, "")
    return "\n".join(lines)
