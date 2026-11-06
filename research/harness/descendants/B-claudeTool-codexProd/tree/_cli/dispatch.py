import sys,difflib
from .. import kernel
from . import parser,verbs
from .output import _err,_finish

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv==['--version']: print('ret 6');return 0
    if argv and not argv[0].startswith('-') and argv[0] not in parser.verbs():
        near=difflib.get_close_matches(argv[0],parser.verbs(),n=1)
        _err(argv[0],"is not a ret command"+('; did you mean '+near[0]+'?' if near else ''));return 2
    p,ps=parser._parser()
    try: a=p.parse_args(argv)
    except SystemExit as e: return e.code
    if not a.cmd: p.print_help();return 0
    if getattr(a,'full_help',False): parser._help_topic(a.cmd);return 0
    fn=getattr(verbs,('_dispatch_' if a.cmd in ('pack','audit','status','crosscheck') else '_handle_')+a.cmd)
    try: return fn(a)
    except (kernel.ClaimError,OSError,ValueError) as e:
        if a.json: return _finish(a.cmd,{'error':str(e)},False,'error',a)
        _err(a.cmd,str(e));return 1
