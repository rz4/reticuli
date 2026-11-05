import argparse
_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'
_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."
PORCELAIN=('init','run','status','pack','pull','export','import','verify','audit','assess','rebuild','crosscheck','record','sign')
ALIASES={}
_FULL_HELP={'verify':'Does not execute acceptance criteria. Use audit to re-earn verdicts.','rebuild':'Generated sources are withheld. A producer is any program. Use --producer openai, --producer anthropic, --producer codex, or --producer claude.','environment':'RETICULI_KEY RETICULI_SIGNERS RETICULI_PRODUCER RETICULI_MODEL RETICULI_VENDOR RETICULI_COLOR RETICULI_GATE_TIMEOUT RETICULI_ENV_CACHE RETICULI_CACHE'}
class Parser(argparse.ArgumentParser):
    def error(self,message):raise ValueError(message)
def verbs():return list(PORCELAIN)+list(ALIASES)+['hook','help','completion']
def _add_verbose_json(p):
    p.add_argument('-v','--verbose',action='store_true');p.add_argument('--json',action='store_true');p.add_argument('--color',choices=['auto','always','never'],default='auto')

def _parser():
    p=Parser(prog='ret',description=_DESC,epilog=_EPILOG,formatter_class=argparse.RawDescriptionHelpFormatter,add_help=False)
    p.add_argument('-h',action='help');p.add_argument('--version',action='store_true');sub=p.add_subparsers(dest='cmd',metavar='COMMAND');ps={}
    for n in verbs():
        q=sub.add_parser(n,add_help=False);q.add_argument('-h',action='help');q.add_argument('--help',action='store_true',dest='full_help');_add_verbose_json(q);ps[n]=q
    for n in ('verify','audit','assess','rebuild','record','sign'):ps[n].add_argument('claim',nargs='?',default='.')
    q=ps['init'];q.add_argument('path',nargs='?',default='.');q.add_argument('--agent');q.add_argument('--no-agent',action='store_true')
    q=ps['run'];q.add_argument('command',nargs='+');q.add_argument('-C','--workspace',default='.')
    q=ps['hook'];q.add_argument('-C','--workspace',default='.')
    q=ps['status'];q.add_argument('path',nargs='?',default='.')
    for f in ('all','files','tree','claims'):q.add_argument('--'+f,action='store_true')
    q=ps['audit'];q.add_argument('--shallow',action='store_true');q.add_argument('--no-strict',action='store_true');q.add_argument('--strict',action='store_true');q.add_argument('--reuse',action='store_true');q.add_argument('--trust',default='self');q.add_argument('--mutants',type=int);q.add_argument('--record');q.add_argument('--quiet',action='store_true')
    ps['assess'].add_argument('--mutants',type=int,default=20)
    q=ps['rebuild'];q.add_argument('--producer',required=False);q.add_argument('-o','--into');q.add_argument('--without-guidance',action='store_true');q.add_argument('--recursive',action='store_true')
    q=ps['crosscheck'];q.add_argument('paths',nargs='*');q.add_argument('--mutants',type=int);q.add_argument('--tolerance',type=float);q.add_argument('--record',action='store_true')
    q=ps['export'];q.add_argument('claim');q.add_argument('output',nargs='?');q.add_argument('-o',dest='out');q.add_argument('--blind',action='store_true')
    q=ps['import'];q.add_argument('archive');q.add_argument('into')
    q=ps['pull'];q.add_argument('claim');q.add_argument('workspace',nargs='?',default='.');q.add_argument('-C',dest='workspace')
    for n in ('record','sign'):
        q=ps[n];q.add_argument('--key');q.add_argument('--as',dest='identity');q.add_argument('--check',action='store_true');q.add_argument('--signers')
    ps['record'].add_argument('-o','--output');ps['record'].add_argument('--sign',action='store_true')
    q=ps['pack'];q.add_argument('path',nargs='?',default='.');q.add_argument('--name');q.add_argument('--generated',nargs='+');q.add_argument('--inputs',nargs='+');q.add_argument('--gate');q.add_argument('--output');q.add_argument('--pytest',nargs='?',const='tests');q.add_argument('--environment');q.add_argument('--accept',nargs='+');q.add_argument('-o','--into');q.add_argument('--force',action='store_true');q.add_argument('--claim',nargs='+');q.add_argument('--format',type=int,dest='claim_format',default=3)
    q=ps['help'];q.add_argument('topic',nargs='?');q.add_argument('-a','--all',action='store_true')
    q=ps['completion'];q.add_argument('shell',nargs='?',default='bash')
    return p,ps

def _completion(shell):print('_ret_complete() { COMPREPLY=( $(compgen -W "'+ ' '.join(verbs())+'" -- "${COMP_WORDS[COMP_CWORD]}") ); }\ncomplete -F _ret_complete ret')
def _help_all():print(' '.join(verbs()))
def _help_topic(topic):
    print('SYNOPSIS\nret '+str(topic)+'\n\n'+_FULL_HELP.get(topic,'Use ret '+str(topic)+' -h for usage.'))
