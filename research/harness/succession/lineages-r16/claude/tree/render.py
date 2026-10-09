"""render: turning claim-shaped data into text (`spec/layers.md`).

`dump_recipe` writes a parsed recipe dict back out as TOML, byte-for-byte
round-trippable through `tomllib.loads` -- the authoring layer's own
writer for the recipes it authors, independent of the kernel's own
preimage writer (`reticuli._kernel.build._recipe_to_toml`), which exists
only to reproduce the room the root was computed from and deliberately
drops producer guidance at format >= 3. `dump_recipe` keeps everything,
because round-tripping the AUTHORED recipe -- guidance included -- is
exactly what this layer's own conformance gate measures.

The remaining six callables (`ago`, `duration`, `paint`, `short`, `table`,
`tree`) are the CLI's small presentation vocabulary: elapsed time, a span
of seconds, ANSI color, a shortened hex digest, a plain text table, and an
indented tree listing. `toml` is the one TOML-value serializer the others
(`dump_recipe` included) all build on. None of the six is exercised by
this layer's own conformance gate; each is implemented to a plain, literal
reading of its name.
"""
import time


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


def toml(value) -> str:
    """One TOML value, literally -- a string, number, boolean, array, or
    inline table -- exactly as `tomllib` reads it back."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{k} = {toml(v)}" for k, v in value.items())
        return "{ " + inner + " }"
    raise ValueError(f"cannot serialize to TOML: {value!r}")


def dump_recipe(recipe: dict) -> str:
    """A recipe dict as TOML text, round-trippable through `tomllib.loads`
    back to the identical dict -- guidance, format, everything, kept."""
    lines = []
    claim = recipe.get("claim")
    if isinstance(claim, dict):
        lines.append("[claim]")
        for k, v in claim.items():
            lines.append(f"{k} = {toml(v)}")
        lines.append("")
    for key, value in recipe.items():
        if key in ("claim", "step"):
            continue
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for k, v in value.items():
                lines.append(f"{k} = {toml(v)}")
            lines.append("")
        else:
            lines.append(f"{key} = {toml(value)}")
    for step in recipe.get("step", []):
        lines.append("[[step]]")
        for k, v in step.items():
            lines.append(f"{k} = {toml(v)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def ago(ts: float, *, now: float = None) -> str:
    """How long ago a unix timestamp was, in human words."""
    now = time.time() if now is None else now
    return duration(max(0.0, now - ts)) + " ago"


def duration(seconds: float) -> str:
    """A span of seconds, in human words."""
    seconds = float(seconds)
    if seconds < 1:
        return "0s"
    units = (("d", 86400), ("h", 3600), ("m", 60), ("s", 1))
    parts = []
    remaining = int(seconds)
    for suffix, size in units:
        if remaining >= size:
            value, remaining = divmod(remaining, size)
            parts.append(f"{value}{suffix}")
    return " ".join(parts) if parts else "0s"


_COLORS = {"red": "31", "green": "32", "yellow": "33", "blue": "34",
           "magenta": "35", "cyan": "36", "white": "37"}


def paint(text: str, color: str) -> str:
    """`text`, wrapped in the ANSI escape for `color`; unchanged if `color`
    is not one of the named colors."""
    code = _COLORS.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def short(digest: str, length: int = 8) -> str:
    """A hex digest, shortened to its first `length` characters."""
    return digest[:length] if digest else digest


def table(rows) -> str:
    """A plain text table: `rows` is a list of equal-length sequences,
    columns aligned by their widest cell."""
    rows = [[str(c) for c in row] for row in rows]
    if not rows:
        return ""
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for row in rows:
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths)))
    return "\n".join(lines)


def tree(node, *, indent: str = "") -> str:
    """`node` -- a `{label: child-node-or-None}` mapping or a list of
    labels -- as an indented text tree."""
    lines = []
    if isinstance(node, dict):
        for label, child in node.items():
            lines.append(f"{indent}{label}")
            if isinstance(child, (dict, list)):
                rendered = tree(child, indent=indent + "  ")
                if rendered:
                    lines.append(rendered)
    elif isinstance(node, list):
        for label in node:
            lines.append(f"{indent}{label}")
    else:
        lines.append(f"{indent}{node}")
    return "\n".join(l for l in lines if l)
