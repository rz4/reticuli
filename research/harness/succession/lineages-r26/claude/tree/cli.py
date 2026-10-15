"""The `ret` CLI -- the human handshake named in `spec/layers.md`.

A thin public facade over `reticuli._cli.dispatch`: `main(argv=None)` is
the single place argv becomes an exit code, and `verbs()` names every
registered subcommand. Everything else -- the grammar, the verb table,
the output envelope, the renderers -- lives under `reticuli._cli` and is
not this module's concern.

Stdlib only.
"""
from reticuli._cli.dispatch import main, verbs

__all__ = ["main", "verbs"]
