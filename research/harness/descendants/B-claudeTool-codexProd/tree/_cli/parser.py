import argparse
_DESC = 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof'
_EPILOG = "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings."
PORCELAIN=('init','run','status','pack','pull','export','import','verify','audit','assess','rebuild','crosscheck','record','sign')
ALIASES={}
_FULL_HELP={'verify':'Does not execute acceptance criteria','rebuild':'Generated sources are withheld. Use --producer openai, --producer anthropic, --producer codex, --producer claude or any program.','environment':'RETICULI_KEY RETICULI_SIGNERS RETICULI_PRODUCER RETICULI_COLOR'}
def verbs(): return list(PORCELAIN)+['hook','help','completion']
def _add_verbose_json(p):
    p.add_argument('-v','--verbose',action='store_true');p.add_argument('--json',action='store_true');p.add_argument('--color',default='auto')
def _parser():
    p=argparse.ArgumentParser(prog='ret',description=_DESC,epilog=_EPILOG,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--version',action='store_true'); sub=p.add_subparsers(dest='cmd',metavar='command'); ps={}
    for name in verbs():
        q=sub.add_parser(name,add_help=False); ps[name]=q; q.add_argument('-h',action='help');q.add_argument('--help',action='store_true',dest='full_help'); _add_verbose_json(q)
        if name=='run': q.add_argument('command',nargs='+');q.add_argument('-C','--workspace',default='.')
        elif name=='crosscheck': q.add_argument('paths',nargs='*')
        elif name=='help': q.add_argument('topic',nargs='?');q.add_argument('-a',action='store_true')
        elif name=='completion': q.add_argument('shell',nargs='?',default='bash')
        elif name=='hook': q.add_argument('-C','--workspace',default='.')
        else: q.add_argument('path',nargs='?',default='.'); q.add_argument('dest',nargs='?')
        if name in ('pack','rebuild','export','record'): q.add_argument('-o','--output')
        if name in ('audit','crosscheck','assess'): q.add_argument('--mutants',type=int)
        if name=='init': q.add_argument('--agent');q.add_argument('--no-agent',action='store_true')
        if name=='status':
            for flag in ('all','files','tree','claims'): q.add_argument('--'+flag,action='store_true')
        if name=='audit':
            q.add_argument('--shallow',action='store_true');q.add_argument('--no-strict',action='store_true');q.add_argument('--record');q.add_argument('--reuse',action='store_true')
        if name=='pack':
            q.add_argument('--accept',nargs='+');q.add_argument('--name');q.add_argument('--generated',nargs='+');q.add_argument('--inputs',nargs='+');q.add_argument('--claim',nargs='+');q.add_argument('--gate');q.add_argument('--gate-output',default='OK');q.add_argument('--pytest');q.add_argument('--environment');q.add_argument('--force',action='store_true')
        if name=='rebuild': q.add_argument('--producer',required=True);q.add_argument('--without-guidance',action='store_true')
        if name=='export': q.add_argument('--blind',action='store_true')
        if name in ('sign','record'):
            q.add_argument('--key');q.add_argument('--as',dest='identity');q.add_argument('--check',action='store_true');q.add_argument('--signers');q.add_argument('--sign',action='store_true')
    return p,ps
def _help_all(): print(' '.join(verbs()))
def _help_topic(topic): print('SYNOPSIS\nret '+str(topic)+'\n'+_FULL_HELP.get(topic,''))
def _completion(shell): print('_ret_complete() { COMPREPLY=( $(compgen -W "'+ ' '.join(verbs())+'" -- "${COMP_WORDS[COMP_CWORD]}") ); }\ncomplete -F _ret_complete ret')
