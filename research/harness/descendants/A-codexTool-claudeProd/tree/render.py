"""Rendering: text for humans, and TOML for recipes.

Two jobs that happen to be the same job.  A recipe written back out must
round-trip — `tomllib.loads(dump_recipe(r)) == r` — because an authoring tool
that could not re-read what it wrote would be unable to reseal a claim it had
just made.  And a report printed for a person must carry its information in
WORDS, never only in a hue: color is decoration that can be turned off, so
every label word returns wherever color is off.
"""
import json
import os
import time

#: SGR codes, by the role a word plays rather than by the colour it happens
#: to be — the names are what a reader of this module needs.
_PAINT = {
    "ok": "32", "good": "32", "fresh": "32", "earned": "32",
    "warn": "33", "pending": "33", "draft": "33",
    "bad": "31", "broken": "31", "failed": "31",
    "dim": "90", "name": "36", "bold": "1", "sealed": "36", "signed": "35",
    "generated": "90", "validated": "32", "pinned": "36", "carried": "33",
    "input": "36",
}


def paint(text: str, role: str, color: bool = True) -> str:
    """Wrap text in the role's colour, or hand it back untouched."""
    code = _PAINT.get(role)
    if not color or not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def short(digest, width: int = 12) -> str:
    """A hash, shortened for a glance.  Full hashes live under -v."""
    if not digest:
        return "-"
    text = str(digest)
    return text[:width] if len(text) > width else text


def duration(seconds) -> str:
    """A span of time, in the largest unit that keeps it readable."""
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "-"
    if value < 1:
        return f"{value * 1000:.0f}ms"
    if value < 60:
        return f"{value:.1f}s"
    if value < 3600:
        return f"{value / 60:.1f}m"
    return f"{value / 3600:.1f}h"


def ago(when) -> str:
    """How long ago a timestamp was, read from the one spelling we emit."""
    if not when:
        return "-"
    try:
        moment = time.strptime(str(when), "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return str(when)
    delta = time.time() - time.mktime(moment) + time.timezone
    if delta < 0:
        delta = 0
    if delta < 90:
        return "just now"
    if delta < 5400:
        return f"{delta / 60:.0f} minutes ago"
    if delta < 172800:
        return f"{delta / 3600:.0f} hours ago"
    return f"{delta / 86400:.0f} days ago"


def table(rows: list, headers: list = None, indent: str = "  ") -> str:
    """Columns aligned to their widest cell; nothing hidden to fit."""
    body = [[("-" if cell is None else str(cell)) for cell in row]
            for row in rows]
    if headers:
        body = [[str(h) for h in headers]] + body
    if not body:
        return ""
    width = max(len(row) for row in body)
    body = [row + [""] * (width - len(row)) for row in body]
    widths = [max(len(row[i]) for row in body) for i in range(width)]
    lines = []
    for row in body:
        cells = [row[i].ljust(widths[i]) for i in range(width)]
        lines.append((indent + "  ".join(cells)).rstrip())
    return "\n".join(lines)


def tree(node: dict, indent: str = "") -> str:
    """A nested structure as indented lines — no glyphs, just shape."""
    lines = []
    label = node.get("label") or node.get("name") or "?"
    detail = node.get("detail")
    lines.append(f"{indent}{label}" + (f"  {detail}" if detail else ""))
    for child in node.get("children") or []:
        lines.append(tree(child, indent + "    "))
    return "\n".join(lines)


# -- TOML -------------------------------------------------------------------


def _scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)      # JSON string escaping is TOML-basic
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {_scalar(v)}"
                                for k, v in value.items()) + " }"
    raise TypeError(f"a recipe cannot carry {type(value).__name__}")


def toml(tables: dict) -> str:
    """Emit a `[claim]` + `[[step]]` document.

    Keys are quoted on purpose: a bare key is legal TOML only for a limited
    character set, and an authoring tool that guessed wrong would write a
    recipe it could not read back.
    """
    lines = []
    claim = tables.get("claim")
    if claim is not None:
        lines.append("[claim]")
        for key, value in claim.items():
            lines.append(f"{json.dumps(key)} = {_scalar(value)}")
    for key, value in tables.items():
        if key in ("claim", "step"):
            continue
        lines.append("")
        lines.append(f"[{json.dumps(key)}]")
        for inner, item in (value or {}).items():
            lines.append(f"{json.dumps(inner)} = {_scalar(item)}")
    for step in tables.get("step") or []:
        lines.append("")
        lines.append("[[step]]")
        for key, value in step.items():
            lines.append(f"{json.dumps(key)} = {_scalar(value)}")
    return "\n".join(lines) + "\n"


def dump_recipe(tables: dict) -> str:
    """`toml`, under the name the authoring layer calls it by."""
    return toml(tables)
