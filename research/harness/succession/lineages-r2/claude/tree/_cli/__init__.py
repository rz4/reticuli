"""reticuli._cli: the human/script handshake (spec/layers.md, surface layer).

`output.py` owns the --json envelope and the one-voice error line; `views.py`
reads a sealed claim into the small state dict a command prints. Neither
module reaches past `reticuli.kernel`'s public surface.
"""
