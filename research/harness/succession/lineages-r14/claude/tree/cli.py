"""reticuli.cli -- the command-line entry point (spec/layers.md: surface).

A thin facade over `_cli.dispatch`: `main(argv)` parses argv and routes to
the verb it names, and `verbs()` reads the grammar back off the parser so
help text and the parser itself can never drift apart.
"""
from reticuli._cli.dispatch import main, verbs

__all__ = ["main", "verbs"]
