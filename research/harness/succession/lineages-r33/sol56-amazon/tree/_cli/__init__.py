"""Private helpers shared by Reticuli's command-line front end.

The package is deliberately small: :mod:`output` owns terminal/JSON output and
:mod:`views` turns kernel state into presentation-neutral dictionaries.  They
are private modules, but keeping these concerns here prevents individual
commands from inventing subtly different status and error vocabularies.
"""

from . import output, views

__all__ = ["output", "views"]
