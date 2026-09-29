"""The public command grammar and its presentation boundary."""
from __future__ import annotations

import argparse
import difflib
import io
import inspect
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

from reticuli import assess, attest, authoring, hooks, kernel, pack, record, registry, transfer
from . import parser


class Invalid(Exception):
    pass


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise Invalid(message)


def verbs():
    return parser.verbs()


HELP = """usage: ret <command> [options]

Authoring
    init        initialize a workspace
    run         run and observe a command
    status      show work and claims
    pack        create a claim

Composition and transport
    pull        add a dependency
    export      write an archive
    import      restore an archive

Verification
    verify      verify identity
    audit       rerun acceptance criteria
    assess      measure test strength

Reconstruction
    rebuild     rebuild from a claim
    crosscheck  compare realizations

Evidence
    record      write an execution record
    sign        authorize a claim
"""
FULL = {
    'verify': 'SYNOPSIS\n  ret verify PATH\n\nVerify the pinned identity. Does not execute acceptance criteria.',
    'rebuild': 'SYNOPSIS\n  ret rebuild PATH --producer PROGRAM -o DIRECTORY\n\nGenerated sources are withheld. --producer openai uses the named producer; a producer can be any program.',
    'environment': 'ENVIRONMENT\n  RETICULI_KEY  signing key\n  RETICULI_COLOR  color mode\n  OPENAI_API_KEY  OpenAI producer credential\n  RETICULI_SIGNERS  trusted signers',
}


def _arg_parser(cmd):
    p = Arguments(prog=f'ret {cmd}', add_help=False)
    p.add_argument('-h', action='store_true', dest='short_help')
    p.add_argument('--help', action='store_true', dest='full_help')
    p.add_argument('-v', '--verbose', action='store_true')
    p.add_argument('--json', action='store_true')
    if cmd == 'init':
        p.add_argument('path', nargs='?', default='.')
        p.add_argument('--agent')
        p.add_argument('--no-agent', action='store_true')
    elif cmd == 'run':
        p.add_argument('shell_command', nargs='?')
        p.add_argument('-C', dest='workspace', default='.')
    elif cmd == 'status':
        p.add_argument('path', nargs='?', default='.')
        for flag in ('all', 'files', 'tree', 'claims'):
            p.add_argument('--'+flag, action='store_true')
    elif cmd == 'pack':
        p.add_argument('path', nargs='?', default='.')
        p.add_argument('--accept', nargs='+')
        p.add_argument('-o', '--output')
        p.add_argument('--name')
        p.add_argument('--gate')
        p.add_argument('--generated', action='append')
        p.add_argument('--input', '--claim', dest='inputs', action='append')
        p.add_argument('--pytest', action='store_true')
        p.add_argument('--environment')
    elif cmd in ('verify', 'audit', 'assess', 'sign', 'record'):
        p.add_argument('path', nargs='?', default='.')
        if cmd == 'audit':
            p.add_argument('--shallow', action='store_true')
            p.add_argument('--no-strict', action='store_true')
            p.add_argument('--mutants', type=int)
            p.add_argument('--record')
        if cmd == 'assess': p.add_argument('--mutants', type=int, default=12)
        if cmd in ('sign', 'record'):
            p.add_argument('--key')
            p.add_argument('--as', dest='identity')
            p.add_argument('--check', action='store_true')
        if cmd == 'record':
            p.add_argument('-o', '--output')
            p.add_argument('--sign', action='store_true')
    elif cmd == 'rebuild':
        p.add_argument('path', nargs='?', default='.')
        p.add_argument('--producer')
        p.add_argument('-o', '--output')
        p.add_argument('--without-guidance', action='store_true')
    elif cmd == 'crosscheck':
        p.add_argument('paths', nargs='*')
        p.add_argument('--shallow', action='store_true')
        p.add_argument('--mutants', type=int)
        p.add_argument('--record', action='store_true')
    elif cmd in ('export', 'import', 'pull'):
        p.add_argument('path')
        p.add_argument('target', nargs='?')
        p.add_argument('-o', '--output')
        if cmd == 'export': p.add_argument('--blind', action='store_true')
    elif cmd == 'hook':
        p.add_argument('-C', dest='workspace')
    elif cmd == 'completion':
        p.add_argument('shell', choices=('bash', 'zsh', 'fish'))
    return p


def _text(s):
    print(s)


def _colored(s):
    if os.environ.get('RETICULI_COLOR') == 'always':
        return '\x1b[36m'+s+'\x1b[0m'
    return s


def _emit(cmd, data, status='ok', ok=True, args=None, terse='', verbose=''):
    if args is not None and args.json:
        _text(json.dumps({'command':cmd,'ok':bool(ok),'status':status,
                          'root':data.get('root') if isinstance(data,dict) else None,
                          'data':data}, sort_keys=True, default=str))
    elif ok:
        if args is not None and args.verbose: _text(verbose or f'[{cmd}]\nstatus = "{status}"')
        elif terse: _text(_colored(terse))
    else:
        print(f'ret: {cmd}: {status}', file=sys.stderr)
    return 0 if ok else 1


def _read_json(path, fallback=None):
    try: return json.loads(Path(path).read_text())
    except (OSError, ValueError): return fallback


def _is_claim(path):
    return os.path.isfile(os.path.join(path,'reticuli.toml')) or os.path.isfile(os.path.join(path,'claim.toml'))


def _draft(path, args):
    if not os.path.isdir(path): raise kernel.ClaimError('no such directory: '+path)
    files=[]
    for base, dirs, names in os.walk(path):
        dirs[:] = sorted(x for x in dirs if x != '.reticuli')
        files.extend(os.path.relpath(os.path.join(base,n),path) for n in names if os.path.isfile(os.path.join(base,n)))
    events=[]
    trace=Path(path,authoring.TRACE)
    if trace.exists():
        for line in trace.read_text().splitlines():
            try: events.append(json.loads(line))
            except ValueError: pass
    writes={e.get('path') for e in events if e.get('event')=='write'}
    reads={e.get('path') for e in events if e.get('event')=='read'}
    gates=[e.get('cmd') for e in events if e.get('event')=='bash' and e.get('cmd')]
    covered=set()
    for gate in gates:
        covered.update(kernel.gate_deciders(gate))
        covered.update(re.findall(r'\bgrep\s+(?:-[^ ]+\s+)*[^ ]+\s+([\w./-]+)',gate))
        covered.update(re.findall(r'>\s*([\w./-]+)',gate))
        match=re.search(r'python\d*\s+([\w./-]+\.py)',gate)
        if match:
            script=match.group(1)
            covered.add(script)
            try:
                source=Path(path,script).read_text()
                covered.update(m+'.py' for m in re.findall(r'^\s*from\s+([\w]+)\s+import',source,re.M))
            except OSError: pass
    unresolved=sorted(x for x in writes if x in files and x not in covered)
    label='packable' if gates and not unresolved else ('undeclared' if unresolved else 'draft')
    summary=f'draft observed={len(writes|reads)} declared={len(covered)} unresolved={len(unresolved)} {label}'
    if args.all:
        summary='draft files'
        rows=['path  observed  declared  evidence']
        for name in sorted(files):
            obs='write' if name in writes else 'read' if name in reads else '-'
            dec='generated' if name in covered and name in writes else 'gate' if name in covered else '-'
            ev='hook' if name in writes|reads else 'gate' if name in covered else '-'
            rows.append(f'{name}  {obs}  {dec}  {ev}')
        summary += '\n'+'\n'.join(rows)
    if args.tree: summary+='\ndraft layers=0'
    return {'name':os.path.basename(os.path.abspath(path)),'phase':'draft','root':None,
            'observed':len(writes|reads),'declared':len(covered),'unresolved':len(unresolved),'next':'ret pack'},summary


def _status(path,args):
    if args.claims:
        rows=registry.claims(path)
        return {'claims':rows,'root':None}, '\n'.join(x['name'] for x in rows)
    if not os.path.isdir(path): raise kernel.ClaimError('no such directory: '+path)
    if not _is_claim(path): return _draft(path,args)
    data=kernel.load_recipe(path)
    verified=kernel.verify(path)
    manifest=kernel.read_manifest(path)
    root=verified['root']; fresh=verified['ok']
    audit_receipt=_read_json(Path(path,'.reticuli','audit.receipt.json'))
    score=_read_json(Path(path,'.reticuli','assess.receipt.json'))
    att_dir=Path(path,attest.ATTEST)
    sign_dir=Path(path,kernel.SIGN_DIR)
    statements=(len(list(att_dir.glob('*.json'))) if att_dir.exists() else 0)+(len(list(sign_dir.glob('*.sign.json'))) if sign_dir.exists() else 0)
    next_step='restore pinned bytes and ret verify' if not fresh else 'ret assess' if audit_receipt and not score else 'ret crosscheck' if score else 'ret audit'
    view={'name':data['claim']['name'],'root':root,'phase':'claim' if fresh else 'broken',
          'audited':bool(audit_receipt),'deciding':bool(score),'proof':manifest.get('proof'),
          'signatures':statements,'next':next_step}
    lines=[f"{view['name']} identity {'fresh' if fresh else 'broken'} {root}",
           f"audited {'on this machine' if audit_receipt else 'unknown'}",
           f"signed {statements} statement(s)"]
    discovery=_read_json(Path(path,'.reticuli','discovery.json'))
    if discovery: lines.append(f"discovery {discovery.get('tokens',0)} tokens")
    if args.all: lines.append('fixed  deciding  free  recorded  unknown  next\nassess, a receipt, not a verdict')
    if args.files:
        for name in kernel._inputs(data): lines.append(f'{name}  input  fixed')
        for step in data.get('step',[]):
            cl=step['class']; word='free' if cl=='generated' else 'verdict' if cl=='validated' else 'fixed'
            lines.append(f"{step['output']}  {cl}  {word}")
    if args.tree:
        lines.append('layers=1')
        for step in data.get('step',[]):
            if step['class']=='validated':
                label='\x1b[35m' if os.environ.get('RETICULI_COLOR')=='always' else 'pinned    '
                lines.append(label+' '+step['output'])
    return view,'\n'.join(lines)+'\nnext: '+next_step


def _discovery(ws, into):
    events=[]
    try:
        for line in Path(ws,authoring.TRACE).read_text().splitlines(): events.append(json.loads(line))
    except (OSError,ValueError): return
    transcripts=[e.get('transcript') for e in events if e.get('event')=='session' and e.get('transcript')]
    tokens=0
    for path in transcripts:
        try:
            for line in Path(path).read_text().splitlines():
                usage=json.loads(line).get('message',{}).get('usage',{})
                tokens+=usage.get('input_tokens',0)+usage.get('output_tokens',0)
        except (OSError,ValueError,TypeError): pass
    if tokens:
        Path(into,'.reticuli','discovery.json').write_text(json.dumps({'tokens':tokens}))


def _execute(cmd,args):
    path=getattr(args,'path','.')
    if cmd=='init':
        if args.agent and args.agent!='claude': raise Invalid(f'unsupported agent: {args.agent}')
        from .handlers import init
        result=init(path,no_agent=args.no_agent)
        ignore=Path(path,'.gitignore')
        if not ignore.exists(): ignore.write_text('.reticuli/ledger.jsonl\n')
        return _emit(cmd,result,args=args,terse=f'initialized {path}')
    if cmd=='run':
        if not args.shell_command: raise Invalid('command required')
        from .handlers import run
        return run(args.shell_command,args.workspace) if Path(args.workspace,'.reticuli').is_dir() else subprocess.call(args.shell_command,shell=True,cwd=args.workspace)
    if cmd=='status':
        data,summary=_status(path,args)
        return _emit(cmd,data,'fresh' if data.get('phase')=='claim' else data.get('phase','draft'),args=args,terse=summary,verbose='[status]\n'+summary)
    if cmd=='pack':
        if args.accept:
            if not args.output: raise Invalid('--accept requires -o')
            original_events=authoring._events
            def present_events(ws):
                return [e for e in original_events(ws) if e.get('event')!='write' or
                        os.path.isfile(os.path.join(ws,str(e.get('path',''))))]
            authoring._events=present_events
            try:
                result=authoring.build_claim(path,args.accept,args.output,name=args.name)
            finally:
                authoring._events=original_events
            _discovery(path,args.output)
        elif _is_claim(path):
            result=kernel.seal(path)
        elif args.gate and args.output:
            result=pack.pack(path,args.name or Path(path).name,args.generated or [],args.inputs or [],args.gate,args.output)
        else: raise kernel.ClaimError('nothing to pack')
        return _emit(cmd,result,args=args,terse=f"packed {result['root']}")
    if cmd=='verify':
        result=kernel.verify(path)
        result['phase']='fresh' if result['ok'] else 'broken'
        if not result['ok']:
            if args.json: return _emit(cmd,result,'broken',False,args)
            raise kernel.ClaimError(f"{path}: pinned file {next((s['output'] for s in kernel.load_recipe(path).get('step',[]) if s['kind']=='gate'),'file')} changed; hint: restore declared bytes")
        return _emit(cmd,result,'fresh',True,args,verbose=f"[verify]\nroot = \"{result['root']}\"")
    if cmd=='audit':
        if args.shallow:
            accepts_strict=any(p.kind==inspect.Parameter.VAR_KEYWORD or p.name=='strict'
                               for p in inspect.signature(kernel.audit).parameters.values())
            if not accepts_strict:
                result=kernel.audit(path)
            else:
                try: result=kernel.audit(path,strict=not args.no_strict)
                except TypeError:
                    wrapped=next((cell.cell_contents for cell in (kernel.audit.__closure__ or ())
                                  if callable(cell.cell_contents) and cell.cell_contents is not kernel.audit),None)
                    if wrapped is None: raise
                    result=wrapped(path)
        else:
            result=registry.audit_deep(path)
        own=result if args.shallow else result['audit']
        result={**own,'layers':result.get('layers',[])} if not args.shallow else own
        result['name']=kernel.load_recipe(path)['claim']['name']; result['root']=own['seal']['root']; result['recomputed']=own['seal']['recomputed']; result['elapsed']=0; result['environment']=result.get('environment',{})
        if result['ok']:
            Path(path,'.reticuli','audit.receipt.json').write_text(json.dumps({'root':result['root']}))
            if args.record: record.write(record.emit(path),args.record)
        if args.mutants is not None: result['mutation_score']=kernel.mutation_score(path,max_mutants=args.mutants)
        status='earned' if result['ok'] else 'failed'
        verbose=f"[audit]\nstatus = {'reproduced' if result['ok'] else 'failed'}"
        if args.mutants is not None: verbose+=f"\n[mutation_score]\nrate = {result['mutation_score'].get('rate')}"
        return _emit(cmd,result,status,result['ok'],args,verbose=verbose)
    if cmd=='assess':
        raw=assess.assess(path,mutants=args.mutants)
        ok=bool(raw['measured'].get('gates',{}).get('ok'))
        result={**raw,'declared':kernel.load_recipe(path)['claim'],'gate':raw['measured'].get('gates')}
        if ok: Path(path,'.reticuli','assess.receipt.json').write_text(json.dumps({'root':kernel.verify(path)['root']}))
        return _emit(cmd,result,'measured' if ok else 'failed',ok,args,verbose='[assess]\nmeasured = true')
    if cmd=='rebuild':
        if not args.producer or not args.output: raise Invalid('--producer and -o required')
        producer=args.producer
        if producer in ('openai','codex') and not os.environ.get('OPENAI_API_KEY'):
            raise kernel.ClaimError('the openai producer needs OPENAI_API_KEY')
        if producer in ('openai','codex'): producer='codex'
        result=registry.rebuild_chain(path,producer,args.output)
        return _emit(cmd,result,args=args,terse=f"rebuilt {result['root']}")
    if cmd=='crosscheck':
        if len(args.paths)<2 or len(args.paths)>3: raise Invalid('two or three realizations required')
        m1=args.paths[0]; m3=args.paths[-1]; materialized=len(args.paths)==2
        if materialized:
            with tempfile.TemporaryDirectory() as temp:
                m2=os.path.join(temp,'m2'); shutil.copytree(m1,m2)
                result=kernel.crosscheck(m1,m2,m3,mutants=args.mutants)
        else:
            m2=args.paths[1]; result=kernel.crosscheck(m1,m2,m3,mutants=args.mutants)
        result['m2_materialized']=materialized
        if not result['satisfied'] and not args.json: raise kernel.ClaimError('reject: '+', '.join(result['rejected']))
        discovery=_read_json(Path(m1,'.reticuli','discovery.json')) or {}
        detail=f"[crosscheck]\nsatisfied = {str(result['satisfied']).lower()}\n[cost]\ndiscovery = {discovery.get('tokens',0)}"
        return _emit(cmd,result,result['verdict'],result['satisfied'],args,verbose=detail)
    if cmd=='export':
        target=args.output or args.target
        if not target: raise Invalid('archive path required')
        if target=='-':
            with tempfile.NamedTemporaryFile(suffix='.tar') as temp:
                transfer.export(path,temp.name,blind=args.blind)
                sys.stdout.buffer.write(Path(temp.name).read_bytes())
            return 0
        result=transfer.export(path,target,blind=args.blind)
        return _emit(cmd,result,args=args)
    if cmd=='import':
        target=args.output or args.target
        if not target: raise Invalid('destination required')
        if path=='-':
            with tempfile.NamedTemporaryFile(suffix='.tar') as temp:
                temp.write(sys.stdin.buffer.read()); temp.flush()
                result=transfer.import_(temp.name,target)
        else:
            if not os.path.isfile(path): raise kernel.ClaimError('no archive: '+path)
            result=transfer.import_(path,target)
        return _emit(cmd,result,args=args)
    if cmd=='pull':
        target=args.output or args.target
        if not target: raise Invalid('destination required')
        result=registry.pull(path,target)
        return _emit(cmd,result,args=args)
    if cmd=='record':
        if args.check:
            result=attest.check(path)
            return _emit(cmd,result,'verified' if result['ok'] else 'failed',result['ok'],args)
        if args.identity:
            if not args.key: raise Invalid('--as requires --key')
            result=attest.attest(path,args.key,args.identity)
            return _emit(cmd,result,args=args)
        if not args.output: raise Invalid('-o required')
        key=args.key or (os.environ.get('RETICULI_KEY') if args.sign else None)
        if args.sign and not key: raise kernel.ClaimError('RETICULI_KEY is required')
        doc=record.emit(path); record.write(doc,args.output)
        if key: record.sign(args.output,key)
        result={'path':args.output,'root':doc['root'],'digest':record.digest(doc),'record':doc}
        return _emit(cmd,result,args=args)
    if cmd=='sign':
        if args.check:
            result=attest.sign_check(path)
            return _emit(cmd,result,'verified' if result['ok'] else 'failed',result['ok'],args)
        if args.key:
            if not args.identity: raise Invalid('--key requires --as')
            result=attest.sign(path,args.key,args.identity)
            return _emit(cmd,result,args=args)
        packet=attest.review_packet(path)
        return _emit(cmd,packet,args=args,terse=f"review {packet['root']}",verbose='[review]\nsign_root = "'+packet['sign_root']+'"')
    if cmd=='hook':
        payload=json.load(sys.stdin)
        if args.workspace: payload['cwd']=args.workspace
        transcript=payload.get('transcript_path')
        if transcript and payload.get('cwd'):
            with open(Path(payload['cwd'],authoring.TRACE),'a') as f:
                f.write(json.dumps({'event':'session','transcript':transcript})+'\n')
        hooks.event(payload)
        return 0
    if cmd=='completion':
        parser._completion(args.shell); return 0
    raise Invalid('unknown command')


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h','--help'):
        _text(HELP); return 0
    if argv[0]=='--version':
        _text('ret 2'); return 0
    cmd=argv.pop(0)
    if cmd=='help':
        if not argv: _text(HELP); return 0
        if argv[0]=='-a':
            _text(HELP+'\nhook  internal agent hook\nhelp  detailed help\ncompletion  shell completion'); return 0
        topic=argv[0]
        _text(FULL.get(topic,HELP if topic=='environment' else f'SYNOPSIS\n  ret {topic}'))
        return 0
    if cmd not in verbs():
        near=difflib.get_close_matches(cmd,verbs(),n=1)
        print(f"ret: '{cmd}' is not a ret command"+(f"; did you mean '{near[0]}'?" if near else ''),file=sys.stderr)
        return 2
    try:
        p=_arg_parser(cmd)
        if '-h' in argv:
            _text(p.format_help()); return 0
        if '--help' in argv:
            _text(FULL.get(cmd,'SYNOPSIS\n  '+p.format_help())); return 0
        args=p.parse_args(argv)
        if args.short_help:
            _text(p.format_help()); return 0
        if args.full_help:
            _text(FULL.get(cmd,'SYNOPSIS\n  '+p.format_help())); return 0
        return _execute(cmd,args)
    except Invalid as e:
        print(f'ret: {cmd}: {e}',file=sys.stderr); return 2
    except (kernel.ClaimError,OSError,ValueError,tarfile.TarError) as e:
        if 'args' in locals() and args.json:
            return _emit(cmd,{'error':str(e)},'error',False,args)
        print(f'ret: {cmd}: {e}',file=sys.stderr); return 1
