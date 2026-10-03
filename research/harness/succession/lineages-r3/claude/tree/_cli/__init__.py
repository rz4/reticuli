"""The human handshake: CLI output formatting and claim views.

`output.py` owns the `--json` envelope and the one-voice error line;
`views.py` reads a sealed claim into the state dict `cli.py` renders and
the ladder of what to run next. Nothing here runs a gate -- a view is a
read, never a verdict.
"""
