"""Rendering: recipes out as TOML, and values out as text a human reads.

Two jobs that belong together because both are about presentation and
neither may ever decide anything. A recipe's TOML form must round-trip --
comments and formatting are free, the parsed content is what identity hashes
-- and the text helpers are the one place the tool decides how a digest, a
duration or a table looks.

Colour is information's second channel, never its only one: wherever colour
is off, the label word returns.
"""
import json
import os
import sys
import time

RESET = "\033[0m"
COLORS = {"red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
          "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m",
          "grey": "\033[90m", "bold": "\033[1m"}


# -- recipes ---------------------------------------------------------------
def toml(value) -> str:
    """One TOML value. JSON's string escaping is TOML-basic, exactly."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {toml(v)}"
                                for k, v in value.items()) + " }"
    raise TypeError(f"a recipe cannot carry {type(value).__name__}")


def dump_recipe(parsed: dict) -> str:
    """A parsed recipe back out as TOML, round-tripping its content."""
    lines = ["[claim]"]
    for key, value in (parsed.get("claim") or {}).items():
        lines.append(f"{key} = {toml(value)}")
    for step in parsed.get("step") or []:
        lines.append("")
        lines.append("[[step]]")
        for key, value in step.items():
            lines.append(f"{key} = {toml(value)}")
    return "\n".join(lines) + "\n"


# -- text ------------------------------------------------------------------
def short(digest, width: int = 12) -> str:
    """A digest, abbreviated for a line a human scans. Full hashes are what
    -v is for: an abbreviation is never what a comparison reads."""
    if not digest:
        return "-"
    return str(digest)[:width]


def duration(seconds) -> str:
    if seconds is None:
        return "-"
    seconds = float(seconds)
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 90:
        return f"{seconds:.1f}s"
    if seconds < 5400:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def ago(when) -> str:
    """How long ago an ISO-8601 UTC stamp was."""
    if not when:
        return "never"
    try:
        then = time.mktime(time.strptime(str(when), "%Y-%m-%dT%H:%M:%SZ")) \
            - time.timezone
    except (ValueError, TypeError):
        return str(when)
    gap = max(0.0, time.time() - then)
    if gap < 60:
        return "just now"
    if gap < 3600:
        return f"{int(gap // 60)}m ago"
    if gap < 86400:
        return f"{int(gap // 3600)}h ago"
    return f"{int(gap // 86400)}d ago"


def _wanted_color(stream=None) -> bool:
    """Colour as `ls` does it: auto means a tty, and the overrides are
    explicit. A captured stream is plain, so a test or a pipe reads text."""
    mode = (os.environ.get("RETICULI_COLOR") or "auto").lower()
    if mode in ("always", "yes", "1", "force"):
        return True
    if mode in ("never", "no", "0", "none"):
        return False
    stream = stream or sys.stdout
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def paint(text: str, color: str | None = None, stream=None) -> str:
    """Wrap text in one colour, where colour is wanted at all."""
    if not color or color not in COLORS or not _wanted_color(stream):
        return text
    return f"{COLORS[color]}{text}{RESET}"


def table(rows, headers=None, gap: int = 2) -> str:
    """Columns wide enough for their content, nothing fancier."""
    body = [[("" if cell is None else str(cell)) for cell in row]
            for row in rows]
    if headers:
        body = [[str(h) for h in headers]] + body
    if not body:
        return ""
    width = max(len(r) for r in body)
    body = [r + [""] * (width - len(r)) for r in body]
    widths = [max(len(r[i]) for r in body) for i in range(width)]
    lines = []
    for row in body:
        cells = [cell.ljust(widths[i]) for i, cell in enumerate(row)]
        lines.append((" " * gap).join(cells).rstrip())
    return "\n".join(lines)


def tree(node, indent: str = "") -> str:
    """A nested {label, children} mapping as an indented tree."""
    if not node:
        return ""
    lines = [indent + str(node.get("label", ""))]
    children = node.get("children") or []
    for child in children:
        lines.append(tree(child, indent + "    "))
    return "\n".join(line for line in lines if line.strip())
