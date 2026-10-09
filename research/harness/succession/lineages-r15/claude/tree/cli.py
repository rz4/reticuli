"""The CLI entrypoint: `ret`'s argv grammar and dispatch.

A thin re-export of `reticuli._cli.dispatch` -- the grammar and every
verb's behavior live there; this module is the stable import surface
(`reticuli.cli.main`, `reticuli.cli.verbs`) that `reticuli.__main__` and
anything embedding the CLI programmatically reaches for.
"""
from reticuli._cli.dispatch import main, verbs

__all__ = ["main", "verbs"]
