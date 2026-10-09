"""The surface layer's public name (`spec/layers.md`): `main`, `verbs`.

The grammar and every verb's dispatch logic live in `_cli/dispatch.py`;
this module is the stable name a caller imports (`from reticuli import
cli`) and the one `reticuli.__main__` runs.
"""
from reticuli._cli.dispatch import main, verbs
