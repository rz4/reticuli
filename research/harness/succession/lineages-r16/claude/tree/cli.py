"""`ret`: the command-line entry point (`spec/layers.md`'s surface layer).

The grammar, verb handlers, and presentation live in `reticuli._cli.dispatch`;
this module is the published surface -- `main`, and `verbs()` for anything
that wants the grammar without touching argv.

Extends `kernel.audit` with a `strict` toggle (True: judge in the sandboxed
jail, the existing default; False: opt down, `--no-strict`) -- the same
higher-layer-patches-a-lower-layer-module idiom `kernel.py` itself uses on
`_kernel.*`. `audit`'s own acceptance check never exercises `strict`; the
surface's does, since `--no-strict` is a CLI-level choice.
"""
import os

from reticuli import kernel
from reticuli._cli import dispatch
from reticuli._cli.dispatch import build_parser, verbs

_real_audit = kernel.audit


def _audit_with_strict(d, *, produce_from=None, strict=True, **kw):
    if strict:
        return _real_audit(d, produce_from=produce_from, **kw)
    prior = os.environ.get(kernel._JAILED)
    os.environ[kernel._JAILED] = "1"
    try:
        return _real_audit(d, produce_from=produce_from, **kw)
    finally:
        if prior is None:
            os.environ.pop(kernel._JAILED, None)
        else:
            os.environ[kernel._JAILED] = prior


kernel.audit = _audit_with_strict


def main(argv=None) -> int:
    return dispatch.main(argv)
