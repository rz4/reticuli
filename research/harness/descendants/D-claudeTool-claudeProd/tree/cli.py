"""The command line, as one name.

A facade: the grammar lives in `_cli/parser.py`, the handlers in
`_cli/verbs.py`, and the routing in `_cli/dispatch.py`. Callers -- including
`python3 -m reticuli` -- reach exactly `main` and `verbs` from here.
"""
from ._cli.dispatch import main
from ._cli.parser import ALIASES, PORCELAIN, verbs

__all__ = ["main", "verbs", "PORCELAIN", "ALIASES"]
