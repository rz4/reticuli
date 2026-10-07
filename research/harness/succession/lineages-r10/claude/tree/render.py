"""render: turning claim-shaped data into bytes and text.

`dump_recipe` is the one function the authoring layer leans on for real: it
serializes a recipe dict (`{"claim": {...}, "step": [...]}`) back into TOML
text that `tomllib` parses back into the identical dict -- the inverse of
`reticuli.kernel.load_recipe`. The rest (`ago`, `duration`, `paint`, `short`,
`table`, `toml`, `tree`) are small display helpers for a human-facing
surface (a CLI) layered on top of this one; their exact output is not a
contract, only that they exist and are callable.

Stdlib only.
"""
import json
import sys
import time


def _toml_scalar(value) -> str:
    """Render one TOML value, matching enough of the grammar that a
    document built only from these values round-trips through `tomllib`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            f"{key} = {_toml_scalar(v)}" for key, v in value.items()
        ) + " }"
    raise ValueError(f"cannot render {value!r} as a TOML value")


def dump_recipe(recipe: dict) -> str:
    """The inverse of `kernel.load_recipe`: a recipe dict back to TOML
    text, one `[claim]` table followed by its `[[step]]` array, in the
    dict's own key order."""
    lines = ["[claim]"]
    for key, value in recipe.get("claim", {}).items():
        lines.append(f"{key} = {_toml_scalar(value)}")
    for step in recipe.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for key, value in step.items():
            lines.append(f"{key} = {_toml_scalar(value)}")
    return "\n".join(lines) + "\n"


def toml(value) -> str:
    """Render one bare value in the same TOML spelling `dump_recipe` uses."""
    return _toml_scalar(value)


def short(digest, n: int = 8) -> str:
    """The first `n` characters of a hex digest -- enough to eyeball, not
    enough to claim uniqueness."""
    text = digest if isinstance(digest, str) else str(digest)
    return text[:n]


def duration(seconds) -> str:
    """A rough human rendering of an elapsed span, coarsest unit first."""
    try:
        seconds = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return "0s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"


def ago(ts) -> str:
    """How long ago a unix timestamp was, in `duration`'s spelling."""
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return "unknown"
    return duration(time.time() - ts) + " ago"


_PAINT_CODES = {
    "red": "31", "green": "32", "yellow": "33",
    "blue": "34", "magenta": "35", "cyan": "36", "dim": "2",
}


def paint(text: str, color: str = None) -> str:
    """Wrap `text` in an ANSI color, only when writing to a real terminal."""
    code = _PAINT_CODES.get(color)
    if not code or not getattr(sys.stdout, "isatty", lambda: False)():
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def table(rows, headers=None) -> str:
    """A plain fixed-width text table over `rows` (an iterable of
    iterables), with an optional header row."""
    str_rows = [[str(cell) for cell in row] for row in rows]
    all_rows = ([list(map(str, headers))] if headers else []) + str_rows
    if not all_rows:
        return ""
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(all_rows[0]))]

    def fmt(row):
        return "  ".join(cell.ljust(w) for cell, w in zip(row, widths))

    lines = []
    if headers:
        lines.append(fmt(list(map(str, headers))))
        lines.append("  ".join("-" * w for w in widths))
    lines.extend(fmt(row) for row in str_rows)
    return "\n".join(lines)


def tree(node, prefix: str = "") -> str:
    """An indented text rendering of a nested dict/list, for a claim's
    component or step structure."""
    lines = []
    if isinstance(node, dict):
        items = list(node.items())
        for i, (key, value) in enumerate(items):
            last = i == len(items) - 1
            lines.append(prefix + ("└── " if last else "├── ") + str(key))
            sub = tree(value, prefix + ("    " if last else "│   "))
            if sub:
                lines.append(sub)
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            last = i == len(node) - 1
            lines.append(prefix + ("└── " if last else "├── ") + str(value))
    else:
        lines.append(prefix + str(node))
    return "\n".join(lines)
