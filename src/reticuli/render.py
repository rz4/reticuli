"""The presentation layer, under one written contract: docs/cli-style.md.

Stdout is one of three shapes: a fact block, an aligned table, or a tree.
Color follows the ls rule — it may REPLACE a label word on a terminal, and
the word returns wherever color is off, so no information ever lives only
in a hue. --json is always underneath, and is the only parse-stable form.
"""
from __future__ import annotations

import json
import os
import sys
import time

#: -v flips this: every hash prints in full instead of 12+"...".
FULL_HASHES = False

# -- color: auto on a terminal, NO_COLOR and RETICULI_COLOR/--color obeyed --

_ANSI = {"green": "32", "red": "31", "yellow": "33", "cyan": "36",
         "magenta": "35", "dim": "2", "bold": "1"}
#: What each semantic role looks like. Verdict words stay words — color
#: reinforces them; class roles may stand in for a label word on a tty.
ROLES = {"pass": "green", "fail": "red", "warn": "yellow",
         "hash": "yellow", "pinned": "cyan", "generated": None,
         "validated": "magenta", "meta": "dim", "hint": "yellow"}
_COLOR_STDOUT = False
_COLOR_STDERR = False


def init_color(mode: str | None = None) -> None:
    """Resolve color once per invocation: --color beats RETICULI_COLOR beats
    auto (a tty, NO_COLOR unset, TERM not dumb). Each stream decides for
    itself, so `ret ... | tee` keeps stderr colored and stdout plain."""
    global _COLOR_STDOUT, _COLOR_STDERR
    mode = mode or os.environ.get("RETICULI_COLOR") or "auto"
    if mode not in ("auto", "always", "never"):
        mode = "auto"

    def on(stream) -> bool:
        if mode == "always":
            return True
        if mode == "never" or os.environ.get("NO_COLOR") \
                or os.environ.get("TERM") == "dumb":
            return False
        try:
            return stream.isatty()
        except (AttributeError, ValueError):
            return False

    _COLOR_STDOUT, _COLOR_STDERR = on(sys.stdout), on(sys.stderr)


def colored(stderr: bool = False) -> bool:
    return _COLOR_STDERR if stderr else _COLOR_STDOUT


def paint(s, role: str, stderr: bool = False) -> str:
    s = str(s)
    name = ROLES.get(role, role)
    code = _ANSI.get(name or "")
    if not code or not colored(stderr):
        return s
    return f"\x1b[{code}m{s}\x1b[0m"


def short(h) -> str:
    s = str(h or "")
    if len(s) != 64:
        return s
    return s if FULL_HASHES else s[:12] + "..."


def duration(seconds) -> str:
    """134.2 -> 2m14s; sub-minute keeps one decimal."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    if s < 60:
        return f"{s:.1f}s"
    m, sec = divmod(round(s), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m}m{sec}s" if h else f"{m}m{sec}s"


def ago(iso: str) -> str:
    """An ISO-8601 UTC stamp, humanized for a terminal; the stamp itself
    everywhere machines read."""
    try:
        then = time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    except (TypeError, ValueError):
        return str(iso)
    delta = max(0, int(time.time() - then))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= size:
            return f"{delta // size}{unit} ago"
    return "just now"


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_scalar(x) for x in v) + "]"
    if isinstance(v, dict):
        return ("{ " + ", ".join(f"{k} = {_scalar(x)}" for k, x in v.items())
                + " }")
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml(*blocks) -> None:
    """Each block is (header, mapping). header "" -> bare keys; "name" -> [name];
    "[[name]]" -> an array-of-tables element. None values dropped."""
    out: list[str] = []
    for header, kv in blocks:
        body = [f"{k} = {_scalar(v)}" for k, v in kv.items() if v is not None]
        if not body and not header.startswith("[["):
            continue
        if header:
            out.append(header if header.startswith("[[") else f"[{header}]")
        out += body
        out.append("")
    print("\n".join(out).rstrip())


def _cell(v) -> str:
    if v is None or v == "":
        return "-"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _isnum(s: str) -> bool:
    try:
        float(s)
        return bool(s)
    except ValueError:
        return False


def table(rows: list, *columns) -> None:
    """Plain aligned columns, git-style: a header row, no index, `-` for
    absent, words for booleans. All-numeric columns right-align."""
    if not rows:
        print("(none)")
        return
    keys = [k for k, _ in columns]
    heads = [h for _, h in columns]
    body = [[_cell(r.get(k)) for k in keys] for r in rows]
    num = [all(_isnum(row[c]) or row[c] == "-" for row in body)
           and any(_isnum(row[c]) for row in body) for c in range(len(keys))]
    w = [max(len(heads[c]), *(len(row[c]) for row in body)) for c in range(len(keys))]

    def just(c, s):
        return s.rjust(w[c]) if num[c] else s.ljust(w[c])

    print("  ".join(just(c, heads[c]) for c in range(len(keys))).rstrip())
    for row in body:
        print("  ".join(just(c, row[c]) for c in range(len(keys))).rstrip())


def tree(root_label: str, node: dict) -> None:
    """A dependency/hierarchy tree. node = {"label", "children": [node, ...]}."""
    print(root_label)

    def walk(n, prefix, last):
        conn = "└── " if last else "├── "
        print(prefix + conn + n["label"])
        kids = n.get("children", [])
        for i, c in enumerate(kids):
            walk(c, prefix + ("    " if last else "│   "), i == len(kids) - 1)

    kids = node.get("children", [])
    for i, c in enumerate(kids):
        walk(c, "", i == len(kids) - 1)


def emit(obj: dict, as_json: bool, render) -> int:
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
    else:
        render(obj)
    return 0


# -- a minimal TOML writer for recipes (tomllib only reads) -----------------


def dump_recipe(recipe: dict) -> str:
    lines = ["[claim]", f'name = "{recipe["claim"]["name"]}"']
    inputs = recipe["claim"].get("inputs")
    if inputs:
        lines.append("inputs = " + _scalar(inputs))
    # The claim's declared contract. Every key the format defines is carried,
    # including the two nothing in this repository writes yet (`format`,
    # `gate_timeout`): a writer that silently drops a key any reader accepts
    # will one day rewrite someone's recipe into a different claim than the one
    # it was handed. Unknown keys are still lost, which is why callers that
    # rewrite an EXISTING recipe re-read what they wrote and compare.
    for k in ("format", "inputs_manifest", "gate_timeout", "tolerance",
              "mutation_floor", "requires", "environment", "envelope"):
        if k in recipe["claim"]:
            lines.append(f"{k} = " + _scalar(recipe["claim"][k]))
    for step in recipe.get("step", []):
        lines += ["", "[[step]]"]
        for k in ("kind", "output", "class", "from", "run", "guidance",
                  "request", "inputs"):
            if k in step:
                lines.append(f"{k} = {_scalar(step[k])}")
    return "\n".join(lines) + "\n"
