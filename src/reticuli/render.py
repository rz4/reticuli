"""Every stdout is one of three shapes: a TOML fact sheet (one entity), a
pandas-style table (rows), or a tree (hierarchy). --json is always underneath.
"""
from __future__ import annotations

import json


def short(h) -> str:
    s = str(h or "")
    return s[:12] + "…" if len(s) == 64 else s


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
    if v is None:
        return ""
    if isinstance(v, bool):
        return "■" if v else "✗"      # ■ / ✗
    return str(v)


def _isnum(s: str) -> bool:
    try:
        float(s)
        return bool(s)
    except ValueError:
        return False


def table(rows: list, *columns) -> None:
    """Pandas-style, integer index; all-numeric columns right-align."""
    if not rows:
        print("Empty  (0 rows)")
        return
    keys = [k for k, _ in columns]
    heads = [h for _, h in columns]
    body = [[_cell(r.get(k)) for k in keys] for r in rows]
    iw = len(str(len(rows) - 1))
    num = [all(_isnum(row[c]) for row in body) for c in range(len(keys))]
    w = [max(len(heads[c]), *(len(row[c]) for row in body)) for c in range(len(keys))]

    def just(c, s):
        return s.rjust(w[c]) if num[c] else s.ljust(w[c])

    print("  ".join([" " * iw] + [just(c, heads[c]) for c in range(len(keys))]))
    for i, row in enumerate(body):
        print("  ".join([str(i).rjust(iw)] + [just(c, row[c]) for c in range(len(keys))]))


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
        for k in ("kind", "output", "class", "from", "run", "request", "inputs"):
            if k in step:
                lines.append(f"{k} = {_scalar(step[k])}")
    return "\n".join(lines) + "\n"
