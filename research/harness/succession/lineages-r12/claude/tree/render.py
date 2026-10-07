"""Rendering: the small text-formatting vocabulary the surface and
authoring layers share (`spec/layers.md`: "render's recipe writer").

`toml` is a minimal, round-tripping TOML writer for the plain-data shapes
a recipe uses (tables, arrays of tables, strings, numbers, booleans,
lists, inline tables); `dump_recipe` is `toml` applied to a parsed claim
recipe, so a recipe `kernel.load_recipe` returns and this module rewrites
is the same document (`tomllib.loads(dump_recipe(recipe)) == recipe`).
The rest -- `ago`, `duration`, `paint`, `short`, `table`, `tree` -- are
small presentation helpers a CLI uses to show a claim's state to a human;
none of their output is identity-bearing or otherwise pinned.

Stdlib only.
"""
import re
import time

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

_COLORS = {
    "red": "31", "green": "32", "yellow": "33", "blue": "34",
    "magenta": "35", "cyan": "36", "bold": "1", "dim": "2",
}


# ---------------------------------------------------------------------------
# A minimal, round-tripping TOML writer
# ---------------------------------------------------------------------------

def _emit_string(s: str) -> str:
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


def _emit_key(k: str) -> str:
    return k if _BARE_KEY.match(k) else _emit_string(k)


def _emit_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return _emit_string(v)
    if isinstance(v, list):
        return "[" + ", ".join(_emit_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_emit_key(k)} = {_emit_value(x)}"
                                for k, x in v.items()) + " }"
    raise ValueError(f"cannot render as TOML: {v!r}")


def _is_table(v) -> bool:
    return isinstance(v, dict)


def _is_array_of_tables(v) -> bool:
    return isinstance(v, list) and len(v) > 0 and all(isinstance(x, dict) for x in v)


def toml(doc: dict) -> str:
    """A TOML document for a flat-ish mapping: a top-level dict value
    becomes a `[section]` table, a top-level list of dicts becomes a
    `[[section]]` array of tables, everything else is a plain key/value
    line. A dict nested inside a section or an array-of-tables entry
    renders as an inline table -- the one shape a recipe field needs it
    for (`[claim] envelope`).
    """
    simple, sections, array_sections = {}, {}, {}
    for k, v in doc.items():
        if _is_table(v):
            sections[k] = v
        elif _is_array_of_tables(v):
            array_sections[k] = v
        else:
            simple[k] = v

    lines = [f"{_emit_key(k)} = {_emit_value(v)}" for k, v in simple.items()]
    for k, v in sections.items():
        lines.append("")
        lines.append(f"[{_emit_key(k)}]")
        for ik, iv in v.items():
            lines.append(f"{_emit_key(ik)} = {_emit_value(iv)}")
    for k, v in array_sections.items():
        for item in v:
            lines.append("")
            lines.append(f"[[{_emit_key(k)}]]")
            for ik, iv in item.items():
                lines.append(f"{_emit_key(ik)} = {_emit_value(iv)}")
    return "\n".join(lines).strip("\n") + "\n"


def dump_recipe(recipe: dict) -> str:
    """A parsed claim recipe, rendered as `reticuli.toml` text -- `toml`
    applied to exactly the shape `kernel.load_recipe` returns."""
    return toml(recipe)


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

def ago(ts: float, now: float = None) -> str:
    """A short "N unit ago" rendering of a past unix timestamp."""
    now = time.time() if now is None else now
    delta = now - ts
    if delta < 0:
        return "just now"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= size:
            return f"{int(delta // size)}{unit} ago"
    return f"{int(delta)}s ago"


def duration(seconds: float) -> str:
    """A short, human rendering of an elapsed span in seconds."""
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def paint(text: str, color: str) -> str:
    """`text` wrapped in an ANSI color code; returned unchanged for an
    unknown color -- a CLI's one-line colorizer."""
    code = _COLORS.get(color)
    return f"\033[{code}m{text}\033[0m" if code else text


def short(digest: str, n: int = 8) -> str:
    """The first `n` characters of a hex digest -- enough to eyeball,
    never enough to mistake for the whole."""
    return digest[:n]


def table(rows: list, headers: list = None) -> str:
    """A simple column-aligned text table from a list of equal-length rows."""
    all_rows = ([list(headers)] if headers else []) + [list(r) for r in rows]
    if not all_rows:
        return ""
    widths = [max(len(str(c)) for c in col) for col in zip(*all_rows)]
    lines = []
    for i, row in enumerate(all_rows):
        lines.append("  ".join(str(c).ljust(w) for c, w in zip(row, widths)))
        if headers and i == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def tree(node: dict, prefix: str = "") -> str:
    """An ASCII tree rendering of `{name: {child name: {...}}}`-shaped
    nesting -- a dependency DAG, or any other named hierarchy."""
    lines = []
    names = list(node)
    for i, name in enumerate(names):
        last = i == len(names) - 1
        branch = "└── " if last else "├── "
        lines.append(prefix + branch + str(name))
        children = node[name] or {}
        if isinstance(children, dict) and children:
            ext = "    " if last else "│   "
            lines.append(tree(children, prefix + ext))
    return "\n".join(line for line in lines if line)
