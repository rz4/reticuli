"""reticuli._cli: the human/machine output contract (spec/layers.md "surface").

`output.py` renders a command's result either as the `--json` envelope or as
a one-voice line on the terminal; `views.py` turns a sealed claim's own files
into the small state dict a surface displays. Neither module touches
identity -- they format what the kernel and the layers below it already
computed.
"""
