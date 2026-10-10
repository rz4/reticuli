"""The CLI entrypoint: `main(argv)` and `verbs()`, the two names the
conformance gate (and any embedder) imports from `reticuli.cli`. The real
grammar and verb wiring live in `_cli.dispatch`; this module is the stable,
public name for it.
"""
from ._cli import dispatch


def main(argv=None) -> int:
    return dispatch.main(argv)


def verbs():
    return dispatch.verbs()
