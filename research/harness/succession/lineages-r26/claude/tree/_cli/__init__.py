"""The human-facing CLI's internals -- see `spec/layers.md` (surface layer).

`output.py` owns the `--json` envelope and the one-voice error line;
`views.py` reads a claim directory into the state dict the CLI renders.
Neither reaches a `reticuli._kernel` private; both stick to `reticuli.kernel`'s
pinned surface. Stdlib only.
"""
