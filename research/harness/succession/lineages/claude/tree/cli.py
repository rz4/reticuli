"""reticuli.cli -- the `ret` command line entry point.

Everything the grammar and dispatch need lives in `reticuli._cli.dispatch`;
this module is just the stable public name the entry point (`__main__.py`)
and the surface gate import.
"""
from ._cli import dispatch


def main(argv=None) -> int:
    return dispatch.main(argv)


def verbs() -> tuple:
    return dispatch.verbs()
