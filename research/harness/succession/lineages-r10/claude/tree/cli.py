"""reticuli.cli: the CLI entry point.

A thin re-export over `reticuli._cli.dispatch`, which owns the actual
argv grammar and verb logic (`spec/layers.md`: the surface layer).
Kept separate so the dispatcher's internals stay a private submodule
while `reticuli.cli.main`/`reticuli.cli.verbs` remain the stable names
both `python -m reticuli` and a direct import use.
"""
from reticuli._cli.dispatch import main, verbs

__all__ = ["main", "verbs"]
