"""The command line, in role modules.

`cli.py` was once one file holding the whole surface, which made the surface
unregrowable: a producer asked to rebuild it had to reproduce everything at
once.  The split is by ROLE, inner to outer, so each piece is a small claim
of its own:

    output      the channel contract — the envelope, the one-voice error line
    views       reading a claim or a session into a state dict
    report      the action-verb renderers
    statusview  the status/draft/tree family
    handlers    session setup, the traced run, producer preflight
    parser      the argv grammar
    verbs       one handler per verb
    dispatch    the routing table, and the shared refusal boundary

This module stays empty on purpose: the inner layers must import cleanly
before the outer ones exist.
"""
