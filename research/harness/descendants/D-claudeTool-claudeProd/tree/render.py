"""Rendering: recipes out, and the small shapes every view is built from.

`toml` is the recipe writer -- the inverse of the kernel's reader, so a
proposed recipe round-trips byte-faithfully. The rest is presentation: hashes
shortened, durations in words, rows aligned, trees drawn, and colour applied
only where a caller says it may be.
"""
import json
import time

#: ANSI, by name. Information never lives only in a hue, so every caller that
#: paints also keeps the label word available.
_COLORS = {"red": "31", "green": "32", "yellow": "33", "blue": "34",
           "magenta": "35", "cyan": "36", "grey": "90", "bold": "1",
           "dim": "2"}


def toml(document: dict) -> str:
    """Write a parsed recipe back out as TOML."""
    lines = []
    for key, value in document.items():
        if _is_table(value) or _is_table_array(value):
            continue
        lines.append(f"{_key(key)} = {_value(value)}")
    for key, value in document.items():
        if _is_table(value):
            lines.append("")
            lines.append(f"[{_key(key)}]")
            for inner, item in value.items():
                lines.append(f"{_key(inner)} = {_value(item)}")
    for key, value in document.items():
        if _is_table_array(value):
            for element in value:
                lines.append("")
                lines.append(f"[[{_key(key)}]]")
                for inner, item in element.items():
                    lines.append(f"{_key(inner)} = {_value(item)}")
    return "\n".join(lines) + "\n"


def dump_recipe(document: dict) -> str:
    """The recipe writer, under the name the authoring layer calls it."""
    return toml(document)


def _is_table(value) -> bool:
    return isinstance(value, dict)


def _is_table_array(value) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(item, dict) for item in value))


def _key(key: str) -> str:
    plain = key != "" and all(c.isalnum() or c in "_-" for c in key)
    return key if plain else json.dumps(key)


def _value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_value(v)}"
                                for k, v in value.items()) + " }"
    raise ValueError(f"cannot write {type(value).__name__} into a recipe")


def short(digest, width: int = 12) -> str:
    """A hash, shortened for a terse view. Full hashes are a -v matter."""
    if not digest:
        return "-"
    text = str(digest)
    return text[:width] if len(text) > width else text


def duration(seconds) -> str:
    """A span, in the largest unit that still reads as a number."""
    if seconds is None:
        return "-"
    value = float(seconds)
    if value < 1:
        return f"{value * 1000:.0f}ms"
    if value < 90:
        return f"{value:.1f}s"
    if value < 5400:
        return f"{value / 60:.1f}m"
    return f"{value / 3600:.1f}h"


def ago(when) -> str:
    """How long ago a moment was, for a receipt a reader is weighing."""
    if when is None:
        return "never"
    if isinstance(when, str):
        try:
            moment = time.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
            stamp = time.mktime(moment) - time.timezone
        except ValueError:
            return when
    else:
        stamp = float(when)
    gap = max(0.0, time.time() - stamp)
    if gap < 90:
        return "just now"
    if gap < 5400:
        return f"{gap / 60:.0f} minutes ago"
    if gap < 172800:
        return f"{gap / 3600:.0f} hours ago"
    return f"{gap / 86400:.0f} days ago"


def paint(text: str, color: str, enabled: bool = True) -> str:
    """Colour, only where a caller says it may be applied."""
    code = _COLORS.get(color or "")
    if not enabled or not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def table(rows, headers=None, gap: int = 2) -> str:
    """Aligned columns. Every cell is a string; a missing one is a dash."""
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
        lines.append((" " * gap).join(cells).rstrip())
    return "\n".join(lines)


def tree(node: dict, indent: str = "") -> str:
    """A claim and everything beneath it, drawn with plain indentation."""
    if not node:
        return ""
    head = f"{indent}{node.get('name', '?')}  {short(node.get('root'))}  " \
           f"{node.get('phase', '?')}"
    lines = [head.rstrip()]
    for child in node.get("components") or []:
        inner = child.get("tree")
        if inner:
            lines.append(tree(inner, indent + "    "))
        else:
            lines.append(f"{indent}    {child.get('component')}  "
                         f"{short(child.get('root'))}  "
                         f"{child.get('status', 'unresolved')}")
    return "\n".join(lines)
