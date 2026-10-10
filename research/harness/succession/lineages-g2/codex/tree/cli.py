"""Public Reticuli command line entrypoint."""
from ._cli.dispatch import main, ALL

def verbs():
    return ALL
