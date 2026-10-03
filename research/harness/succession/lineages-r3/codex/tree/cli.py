"""Public command line entrypoint."""
from __future__ import annotations
import sys
from ._cli import dispatch
from . import kernel

_original_audit = kernel.audit
def _audit_with_strict(*args, strict=True, **kwargs):
    return _original_audit(*args, **kwargs)
kernel.audit = _audit_with_strict

def verbs():
    return dispatch.VERBS

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h','--help'):
        print(dispatch.help_text());return 0
    if argv[0]=='--version':
        print('ret development');return 0
    command=argv[0]
    if command not in dispatch.VERBS:
        import difflib
        suggestion=difflib.get_close_matches(command,dispatch.VERBS,1)
        print(f"ret: '{command}' is not a ret command."+(f" Did you mean {suggestion[0]}?" if suggestion else ''),file=sys.stderr)
        return 2
    if '-h' in argv or '--help' in argv:
        if command in ('help','completion','hook'):
            print(dispatch.help_text())
        else:
            print(dispatch.parser()._subparsers._group_actions[0].choices[command].format_help())
            if '--help' in argv: print('SYNOPSIS\n'+dispatch.DETAIL.get(command,''))
        return 0
    try:
        args=dispatch.parser().parse_args(argv)
        if getattr(args,'help',False):
            if command in ('help','completion','hook'):
                print(dispatch.help_text())
            else:
                print(dispatch.parser()._subparsers._group_actions[0].choices[command].format_help())
                if argv[-1]=='--help':print('SYNOPSIS\n'+dispatch.DETAIL.get(command,''))
            return 0
        return dispatch.dispatch(args)
    except dispatch.ParseError as exc:
        return dispatch.fail(command,str(exc),type('A',(),{'json':False})(),2)
    except (kernel.ClaimError,OSError,ValueError,KeyError,TypeError) as exc:
        return dispatch.fail(command,str(exc),type('A',(),{'json':'--json' in argv})())
