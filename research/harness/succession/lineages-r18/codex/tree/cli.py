"""Reticuli command line entrypoint."""
import difflib
import sys
from ._cli.dispatch import NAMES, dispatch, parser_for, top_help, HELP

def verbs():return NAMES

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h','--help'):
        print(top_help());return 0
    if argv[0]=='--version':print('ret development');return 0
    name=argv.pop(0)
    if name not in NAMES:
        suggestion=difflib.get_close_matches(name,NAMES,n=1)
        print(f"ret: '{name}' is not a ret command"+(f"; did you mean {suggestion[0]}?" if suggestion else ''),file=sys.stderr)
        return 2
    p=parser_for(name)
    if argv==['-h']:
        print(p.format_help());return 0
    if argv==['--help']:
        print(HELP.get(name,'SYNOPSIS\n'+p.format_help()));return 0
    try:args=p.parse_args(argv)
    except ValueError as exc:
        print(f'ret: {name}: {exc}',file=sys.stderr);return 2
    if args.short_help:print(p.format_help());return 0
    if args.full_help:print(HELP.get(name,'SYNOPSIS\n'+p.format_help()));return 0
    return dispatch(name,args)
