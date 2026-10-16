"""Weave the implementation into literate pages: full code, explained.

    python3 docs/weave.py          # regenerates docs/book/ from the tree

The old-school form -- the whole source presented in reading order, with
prose beside the code it explains -- fits this repository better than
hand-written API docs would, for a reason particular to reticuli: the
implementation under `src/` is GENERATED. It is one member of an
equivalence class, and any rebuild may replace it. Documentation written
ABOUT the implementation would drift the first time the tree regrew;
documentation woven FROM it cannot, because it is a rendering of the same
bytes. The prose these pages lift -- module docstrings, the `#:` attribute
notes, the why-comments -- is the institutional memory the selection lane
measures as `prose_bytes`, higher-is-better: the one axis that runs against
size because it is the only thing keeping the tree maintainable by a
person. These pages are that axis made readable.

The weave is docco-shaped: a module's docstring opens its page; every run
of full-line comments becomes narration between code blocks; everything
else -- including def and class docstrings, which belong to the code's own
voice -- stays verbatim in the code. Lifted comments are the only bytes
not shown inside fences, so the code blocks plus the narration reconstruct
the file.

Pages are DERIVED, like a population registry: regenerate after any
rebuild, never edit by hand, and losing them loses nothing.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOK = REPO / "docs" / "book"

#: What gets woven: (section title, root directory, package prefix for the
#: page name). zeta's queue is deliberately absent -- entries are sealed
#: claims, shown by reference, never re-rendered.
AREAS = [
    ("The kernel and its surface (src/reticuli)", REPO / "src" / "reticuli",
     "reticuli"),
    ("Zeta: the companion claim (zeta)", REPO / "zeta", "zeta"),
]

SKIP_PARTS = {"__pycache__", "queue", "population", "coverage", "selection",
              "promoted", "spec", "criteria"}
#: zeta/criteria and zeta/spec are pinned inputs of ZETA's root; they are
#: linked from the index but not woven, so nobody mistakes a rendering for
#: the pinned bytes. The excluded data directories are outputs.


def _modules(root):
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        yield path


def _module_docstring_span(source):
    """(docstring text, last line it occupies) or (None, 0)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None, 0
    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)):
        return tree.body[0].value.value, tree.body[0].end_lineno
    return None, 0


def _lift(line):
    stripped = line.lstrip()
    for marker in ("#: ", "#:", "# ", "#"):
        if stripped.startswith(marker):
            return stripped[len(marker):]
    return None


def weave(path):
    source = path.read_text(encoding="utf-8")
    doc, skip = _module_docstring_span(source)
    lines = source.splitlines()[skip:]

    pieces = []            # ("prose"|"code", [lines])
    mode, buffer = None, []

    def flush():
        nonlocal buffer
        if mode == "code":
            while buffer and not buffer[0].strip():
                buffer.pop(0)
            while buffer and not buffer[-1].strip():
                buffer.pop()
        if buffer:
            pieces.append((mode, buffer))
        buffer = []

    for line in lines:
        lifted = _lift(line)
        want = "prose" if lifted is not None else "code"
        if want == "code" and not line.strip() and mode == "prose":
            # a blank line inside a comment run is a paragraph break
            buffer.append("")
            continue
        if want != mode:
            flush()
        buffer.append(lifted if lifted is not None else line)
        mode = want
    flush()

    rel = path.relative_to(REPO)
    out = [f"# `{rel}`", ""]
    if doc:
        first, _, rest = doc.strip().partition("\n")
        out += [f"**{first.strip()}**", ""]
        if rest.strip():
            out += [rest.strip(), ""]
    for kind, chunk in pieces:
        if kind == "prose":
            # a divider comment (---------- name) is a section, so render it
            # as the heading it was standing in for
            rendered = []
            for line in chunk:
                bare = line.strip()
                if bare and set(bare.split()[0]) == {"-"} and len(bare.split()[0]) >= 8:
                    title = bare.lstrip("-").strip()
                    rendered.append(f"\n### {title}\n" if title else "")
                else:
                    rendered.append(line)
            out += ["\n".join(rendered).strip(), ""]
        else:
            out += ["```python", *chunk, "```", ""]
    out += ["---",
            f"*Woven from `{rel}` by `docs/weave.py`. The implementation is "
            f"generated -- one member of the claim's equivalence class -- so "
            f"this page is derived twice over: regenerate it, never edit it.*",
            ""]
    return "\n".join(out), (doc or "").strip().partition("\n")[0]


def main():
    root_hash = "unsealed"
    manifest = REPO / ".reticuli" / "manifest.json"
    if manifest.is_file():
        root_hash = json.loads(manifest.read_text()).get("root", "")[:12]

    toc = ["# The implementation, woven", "",
           f"Every module of the primary claim and its companion, full source "
           f"with its own narration lifted beside it. Generated against root "
           f"`{root_hash}`; regenerate with `python3 docs/weave.py` after any "
           f"rebuild.", "",
           "What is deliberately NOT here: `zeta/criteria` and `zeta/spec` "
           "(pinned inputs of zeta's own root -- read the bytes, not a "
           "rendering), the queue (each entry is a sealed claim), and the "
           "repository's own `criteria/` and `spec/` (pinned inputs of the "
           "primary root, same rule).", ""]

    count = 0
    for title, root, prefix in AREAS:
        toc += [f"## {title}", ""]
        for path in _modules(root):
            page, summary = weave(path)
            rel = path.relative_to(root)
            name = prefix + "." + ".".join(rel.with_suffix("").parts)
            name = name.replace(".__init__", "") or prefix
            target = BOOK / prefix / (name + ".md")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
            toc.append(f"- [`{name}`]({prefix}/{name}.md) — {summary or '(no docstring)'}")
            count += 1
        toc.append("")
    (BOOK / "index.md").write_text("\n".join(toc), encoding="utf-8")
    print(f"wove {count} modules into {BOOK}")


if __name__ == "__main__":
    main()
