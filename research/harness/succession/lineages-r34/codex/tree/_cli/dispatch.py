import sys, difflib, json
from .. import kernel
from . import parser, verbs, handlers
from .output import _err

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv==['--version']:print(handlers._version_line());return 0
    if not argv or argv in (['-h'],['--help']):parser._parser()[0].print_help();return 0
    cmd=argv[0]
    if cmd not in parser.verbs():
        near=difflib.get_close_matches(cmd,parser.verbs(),n=1)
        _err(cmd,"is not a ret command"+('; did you mean '+near[0]+'?' if near else ''));return 2
    if '--help' in argv:parser._help_topic(cmd);return 0
    try:
        p,_=parser._parser();a=p.parse_args(argv)
    except ValueError as e:_err(cmd,str(e));return 2
    except SystemExit as e:return e.code
    mapping={'pack':verbs._dispatch_pack,'audit':verbs._dispatch_audit,'status':verbs._dispatch_status,'crosscheck':verbs._dispatch_crosscheck}
    fn=mapping.get(cmd) or getattr(verbs,'_handle_'+cmd)
    try:return fn(a)
    except kernel.ClaimError as e:
        if a.json:print(json.dumps({'command':cmd,'ok':False,'status':'error','root':None,'data':{'error':str(e)}}))
        else:_err(cmd,str(e))
        return 1
    except KeyboardInterrupt:_err(cmd,'interrupted');return 1
