"""Reticuli command entry point."""
from __future__ import annotations
import os
import sys
from . import kernel
from ._cli import dispatch

_original_audit=kernel.audit
def _audit_compat(directory,*args,strict=True,**kwargs):
    return _original_audit(directory,*args,**kwargs)
kernel.audit=_audit_compat

def verbs():return dispatch.VERBS

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in dispatch.VERBS and not argv[0].startswith('-'):
        import difflib
        near=difflib.get_close_matches(argv[0],dispatch.VERBS,n=1)
        print(f"ret: {argv[0]} is not a ret command"+(f"; did you mean {near[0]}?" if near else ''),file=sys.stderr)
        return 2
    if argv and argv[0] in dispatch.VERBS and ('-h' in argv or '--help' in argv):
        print(dispatch._help(argv[0],short='-h' in argv and '--help' not in argv))
        return 0
    try:
        args=dispatch.parser().parse_args(argv)
        if args.version:print('ret 2');return 0
        if args.help or args.command is None:print(dispatch._help());return 0
        if getattr(args,'h',False):print(dispatch._help(args.command,short=True));return 0
        if getattr(args,'full_help',False):print(dispatch._help(args.command));return 0
        return dispatch.dispatch(args)
    except dispatch.Usage as e:
        print(f'ret: {argv[0] if argv else "ret"}: {e}',file=sys.stderr);return 2
    except (kernel.ClaimError,OSError,ValueError) as e:
        name=argv[0] if argv else 'ret'
        if '--json' in argv:
            class A:json=True
            return dispatch._error(name,str(e),A())
        print(f'ret: {name}: {e}',file=sys.stderr);return 1
