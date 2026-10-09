"""The surface layer's CLI internals (`spec/layers.md`).

`output` is the terminal boundary (the `--json` envelope, the one-voice
error line, a stderr progress reporter); `views` reads a sealed claim into
the state dict a command renders. Neither module owns argument parsing or
verb dispatch -- that is `cli.py`'s job, built on top of these.
"""
