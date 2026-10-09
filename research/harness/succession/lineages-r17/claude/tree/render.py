"""Render: turning claim-shaped data into text a human reads (`spec/layers.md`).

Presentation only -- no identity, no filesystem writes, no judging. `toml`
serializes one Python value (scalar, list, or flat dict) as TOML source;
`dump_recipe` uses it to write a whole recipe (`[claim]` plus `[[step]]`
tables) back to text that `tomllib` parses to an equal structure -- the
authoring layer's own round-trip, independent of the kernel's own private
writer. `short`/`ago`/`duration`/`paint`/`table`/`tree` are the small
display helpers a CLI builds on: a shortened hex digest, a relative time,
a human duration, an optional ANSI wrap, a plain text table, and an
indented tree listing.

Stdlib only.
"""
import json


# =============================================================================
# TOML: a recipe value as source text, and a whole recipe as a file
# =============================================================================

def toml(value) -> str:
    """One recipe value as TOML source: scalars, lists, and flat dicts --
    everything a recipe's `[claim]` table or a step ever carries."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {toml(v)}" for k, v in value.items()) + " }"
    raise ValueError(f"value has no TOML form: {value!r}")


def dump_recipe(recipe: dict) -> str:
    """A parsed recipe (`{"claim": {...}, "step": [...]}`) as TOML text that
    `tomllib.loads` parses back to an equal structure."""
    lines = ["[claim]"]
    for key, value in recipe.get("claim", {}).items():
        lines.append(f"{key} = {toml(value)}")
    for step in recipe.get("step", []):
        lines.append("")
        lines.append("[[step]]")
        for key, value in step.items():
            lines.append(f"{key} = {toml(value)}")
    return "\n".join(lines) + "\n"


# =============================================================================
# small display helpers
# =============================================================================

def short(digest: str, n: int = 8) -> str:
    """The first `n` characters of a hex digest, for compact display."""
    return digest[:n] if digest else ""


def ago(seconds: float) -> str:
    """A span of seconds, in words, as `"<n> <unit> ago"`."""
    seconds = max(0.0, float(seconds))
    for span, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= span:
            n = int(seconds // span)
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    n = int(seconds)
    return f"{n} second{'s' if n != 1 else ''} ago"


def duration(seconds: float) -> str:
    """A span of seconds as a short human duration, e.g. `"1m 30s"`."""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {rest}s"
    hours, rest_m = divmod(minutes, 60)
    return f"{hours}h {rest_m}m"


_ANSI = {"red": "31", "green": "32", "yellow": "33", "blue": "34", "dim": "2"}


def paint(text: str, color: str = None) -> str:
    """`text` wrapped in an ANSI color, or returned unchanged with no color
    given or an unknown color name."""
    code = _ANSI.get(color)
    if not code:
        return text
    return f"\033[{code}m{text}\033[0m"


def table(rows, headers=None) -> str:
    """A plain fixed-width text table over `rows` (equal-length sequences),
    with an optional header row and separator."""
    all_rows = ([list(headers)] if headers else []) + [list(r) for r in rows]
    if not all_rows:
        return ""
    width = len(all_rows[0])
    widths = [max(len(str(r[i])) for r in all_rows) for i in range(width)]
    lines = []
    for i, row in enumerate(all_rows):
        lines.append("  ".join(str(v).ljust(w) for v, w in zip(row, widths)))
        if headers and i == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def tree(node, indent: str = "") -> str:
    """`node` (a plain label, or `{label: [children, ...]}`) as an indented
    listing; a child may itself be a label or a nested `{label: [...]}`."""
    if isinstance(node, dict):
        lines = []
        for label, children in node.items():
            lines.append(f"{indent}{label}")
            for child in children:
                lines.append(tree(child, indent + "  "))
        return "\n".join(lines)
    return f"{indent}{node}"
