"""The human handshake: `ret`.

A facade.  The grammar lives in `_cli.parser`, the handlers in `_cli.verbs`,
the routing in `_cli.dispatch`; this module is what a caller imports and what
`python3 -m reticuli` runs, so the entrypoint is one name whatever the inside
is arranged like.
"""
import sys

from ._cli import dispatch, parser

__all__ = ["main", "verbs"]


def verbs() -> list:
    """Every name that dispatches, so help and the parser cannot disagree."""
    return parser.verbs()


def main(argv=None) -> int:
    """Run one invocation and hand back its exit code."""
    return dispatch.main(argv)


if __name__ == "__main__":
    sys.exit(main())
