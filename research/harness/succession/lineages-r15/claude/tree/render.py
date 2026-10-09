"""render: human-facing formatting for the authoring layer and the CLI above
it (`spec/layers.md`) -- plus `dump_recipe`, the one TOML writer every
claim-producing module in this layer shares, so a recipe's on-disk bytes
always come from exactly one serializer.

Stdlib only.
"""
import re

_BASIC_KEY = re.compile(r"[A-Za-z0-9_-]+")


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
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _toml_key(k: str) -> str:
    return k if _BASIC_KEY.fullmatch(k) else _toml_string(k)


def toml(value) -> str:
    """One TOML-syntax value for `value`: a string, bool, int, float, list,
    or dict (rendered as an inline table) -- the scalar grammar a recipe
    field needs (`spec/claim-format.md`). Integers are exact decimal;
    floats use `repr`, the shortest round-tripping form.
    """
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
        inner = ", ".join(f"{_toml_key(k)} = {toml(v)}" for k, v in value.items())
        return "{ " + inner + " }"
    raise TypeError(f"cannot render to TOML: {value!r}")


def dump_recipe(doc: dict) -> str:
    """A recipe dict (`{"claim": {...}, "step": [...]}`) as TOML text, that
    round-trips through `tomllib.loads` back to the same dict: one
    `[claim]` table, then one `[[step]]` array-of-tables entry per step
    (`spec/claim-format.md`'s schema).
    """
    lines = ["[claim]"]
    for k, v in doc.get("claim", {}).items():
        lines.append(f"{_toml_key(k)} = {toml(v)}")
    for step in doc.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for k, v in step.items():
            lines.append(f"{_toml_key(k)} = {toml(v)}")
    return "\n".join(lines) + "\n"


def short(digest: str, n: int = 8) -> str:
    """The first `n` characters of a hex digest, for display."""
    return digest[:n] if digest else digest


def duration(seconds) -> str:
    """A human-readable span, smallest unit `s`: `"1h 02m 03s"`-style."""
    total = int(float(seconds or 0))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def ago(seconds_elapsed) -> str:
    """`"<duration> ago"`, for a span already measured in seconds."""
    return f"{duration(seconds_elapsed)} ago"


_COLORS = {"red": "31", "green": "32", "yellow": "33", "blue": "34", "cyan": "36"}


def paint(text: str, color: str = None) -> str:
    """`text` wrapped in an ANSI color escape; an unknown or absent `color`
    returns `text` unchanged, so a caller may pass `None` for plain text.
    """
    code = _COLORS.get(color)
    return text if not code else f"\033[{code}m{text}\033[0m"


def table(rows, headers=None) -> str:
    """A left-aligned, whitespace-padded text table over `rows` (a list of
    equal-length sequences), with an optional `headers` row.
    """
    all_rows = ([list(headers)] if headers else []) + [list(r) for r in rows]
    if not all_rows:
        return ""
    widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(all_rows[0]))]
    return "\n".join(
        "  ".join(str(cell).ljust(w) for cell, w in zip(r, widths))
        for r in all_rows
    )


def tree(node, label=lambda n: str(n), children=lambda n: [], indent: int = 0) -> str:
    """A text tree over `node`, drawn by recursing through `children(node)`;
    `label` renders one node.
    """
    lines = ["  " * indent + label(node)]
    for child in children(node):
        lines.append(tree(child, label=label, children=children, indent=indent + 1))
    return "\n".join(lines)
