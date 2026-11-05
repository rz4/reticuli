"""The command-line facade: `ret`.

Everything the surface does lives in `_cli/`; this module is the one name
the outside world binds to, so the sub-layers underneath can be rebuilt
independently without any caller noticing.
"""
from ._cli.dispatch import main
from ._cli.parser import verbs

__all__ = ["main", "verbs"]
