"""The CLI surface: `ret`'s entry point and the grammar it answers to.

The dispatch logic itself lives in `reticuli._cli.dispatch` (spec/layers.md's
surface layer); this module is the stable public name both `python3 -m
reticuli` (`reticuli.__main__`) and anything embedding this tool import.
"""
from ._cli.dispatch import main, verbs

__all__ = ["main", "verbs"]
