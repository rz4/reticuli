"""The CLI entrypoint module (`spec/layers.md`'s surface layer).

A thin re-export of `_cli.dispatch`: `main` is what `python3 -m reticuli`
runs, and `verbs()` is the one place the full grammar -- porcelain plus
plumbing -- is named, read back by `checks/surface_check.py` to confirm
the parser and the help never drift apart.

Stdlib only.
"""
from ._cli.dispatch import main, verbs

__all__ = ["main", "verbs"]
