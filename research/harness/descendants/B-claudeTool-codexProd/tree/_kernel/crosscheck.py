import os,re,shlex,ast,tempfile,tokenize,io
from .core import *
from .core import _write_json,_safe
from .recipe import load_recipe,produces,generated_outputs,step_class
from .identity import build_digest
from .seal import verify,read_manifest,seal
from .build import audit
from .run import cost,independence,_independence_line,_in_band
from .attest import record_read,record_digest,record_signer
_COMPARISON=('>','<','>=','<=','==','!=')
_INTERPRETERS=frozenset({'Rscript','awk','lua','python','python3','python2','node','ruby','perl','dash','deno','py.test','zsh','tclsh','php','sh','bash','py','pytest'})
_OPERATORS=frozenset({'&','\n','|','||','&&',';'})
_SKIP_VALUE=frozenset({'-m','-p','--module','-X','-c','-e'})
_ARITHMETIC=('+','-','*','/')
_OP_ALTS={'+':'-','-':'+','*':'/','/':'*','>':'<','<':'>','>=':'<','<=':'>','==':'!=','!=':'=='}
_OP_KIND={}; _WORD_ALTS={'True':'False','False':'True'}
_STRING_LITERAL=re.compile(r'".*?"')
def gate_deciders(cmd):
    if isinstance(cmd,dict): return {s['output']:gate_deciders(s['run']) for s in cmd.get('step',[]) if s['kind']=='gate'}
    out=[]
    for part in re.split(r'&&|\|\||;|\n|\|',cmd):
        try: ts=shlex.split(part)
        except ValueError: continue
        if not ts: continue
        tool=os.path.basename(ts[0])
        if ts[0].startswith('./'): out.append(ts[0][2:]); continue
        if tool not in _INTERPRETERS: continue
        if '-c' in ts or '-e' in ts: continue
        if '-m' in ts:
            idx=ts.index('-m')
            if idx+1<len(ts) and ts[idx+1] not in ('pytest','unittest'): continue
            ts=ts[idx+2:]
        else: ts=ts[1:]
        out.extend(t for t in ts if not t.startswith('-') and t not in ('>','2>') )
    return list(dict.fromkeys(out))
def vacuous_gates(r):
    gens=set(generated_outputs(r)); result=[]
    for g in r.get('step',[]):
        if g['kind']=='gate':
            ds=gate_deciders(g['run'])
            if ds and all(p in gens for p in ds): result.append(g['output'])
    return result
def sign_node(root,build,links): return digest([root,build,sorted(links)])
def _machine(p):
    if os.path.isfile(p):
        r=record_read(p); return {'root':r['root'],'build':r['build_digest'],'ok':all(g['status']=='ok' for g in r['gates']),'cost':r.get('cost'),'claim':r.get('claim'),'producer':r.get('producer',{})}
    v=verify(p); a=audit(p)
    return {'root':v['root'],'build':build_digest(p),'ok':a['ok'],'cost':cost(p),'claim':load_recipe(p)['claim'],'producer':independence(p)}
def crosscheck(m1,m2,m3,tolerance=None,mutants=None,**kw):
    paths=[m1,m2,m3]
    if len(set(map(os.path.realpath,paths)))<3: raise ClaimError('crosscheck needs distinct paths')
    ms={k:_machine(p) for k,p in zip(('M1','M2','M3'),paths)}; a,b,c=ms.values()
    eq=len({m['root'] for m in ms.values()})==1; reuse=a['build']==b['build']; audited={k:m['ok'] for k,m in ms.items()}
    rejected=[]; incomplete=[]
    if not eq: rejected.append('roots')
    if not reuse: rejected.append('reuse')
    if not all(audited.values()): rejected.append('audit')
    declared=a['claim']
    if declared is None: incomplete.append('declared conditions'); declared={}
    dt=declared.get('tolerance'); tol=min(dt,tolerance) if dt is not None and tolerance is not None else dt if dt is not None else tolerance or 2.0
    c1=a['cost'] or {}; c3=c['cost'] or {}; unit=next((k for k in COST_LADDER if k in c1 and k in c3),None)
    comparable=_in_band(c3[unit],c1[unit],tol) if unit else None
    if dt is not None:
        if comparable is False: rejected.append('tolerance')
        elif comparable is None: incomplete.append('tolerance')
    cr={'comparable':comparable,'unit':unit,'tolerance':tol,'declared_tolerance':dt,'tightened':dt is not None and tol<dt,'M1':c1,'M3':c3,'envelope':{}}
    for k,v in declared.get('envelope',{}).items():
        within=c3[k]<=v if k in c3 else None
        cr['envelope'][k]={'ceiling':v,'measured':c3.get(k),'within':within}
        if within is False: rejected.append('envelope '+k)
        if within is None: incomplete.append('envelope '+k)
    score=None
    if mutants and os.path.isdir(m3): score=mutation_score(m3,max_mutants=mutants)
    if 'mutation_floor' in declared:
        if score is None: incomplete.append('mutation_floor')
        else:
            score['ok']=score['rate']>=declared['mutation_floor']
            if not score['ok']: rejected.append('mutation_floor')
    verdict='reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied':verdict=='accept','verdict':verdict,'rejected':rejected,'incomplete':incomplete,'roots':{k:m['root'] for k,m in ms.items()},'equivalence':eq,'reuse':reuse,'audited':audited,'cost':cr,'mutation_score':score,'independence':_independence_line(c['producer'])}
def record_proof(m1,m2,m3,**kw):
    if not os.path.isdir(m1): raise ClaimError('proof needs directory M1')
    records=[]
    for p in (m2,m3):
        if os.path.isfile(p):
            signer=record_signer(p)
            if not signer: raise ClaimError('record needs anchored signature')
            records.append({'digest':record_digest(record_read(p)),'signer':signer})
    r=crosscheck(m1,m2,m3,**kw); r['proof_recorded']=r['satisfied']
    if r['satisfied']: seal(m1,proof={**r,'records':records})
    return r

def _token_mutants(text):
    lines=text.splitlines(keepends=True); offsets=[0]
    for line in lines: offsets.append(offsets[-1]+len(line))
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            alt=_OP_ALTS.get(t.string) if t.type==tokenize.OP else _WORD_ALTS.get(t.string) if t.type==tokenize.NAME else None
            if t.type==tokenize.NUMBER:
                try: alt=str(int(t.string)+1)
                except ValueError: pass
            if alt is not None:
                start=offsets[t.start[0]-1]+t.start[1]; end=offsets[t.end[0]-1]+t.end[1]
                changed=text[:start]+alt+text[end:]
                try: ast.parse(changed)
                except SyntaxError: continue
                yield changed
    except (tokenize.TokenError,IndentationError): return

def mutation_score(d,max_mutants=10,**kw):
    r=load_recipe(d); candidates=[]
    for s in produces(r):
        p=s['output']
        if step_class(s)=='generated' and p.endswith('.py') and os.path.isfile(_safe(d,p)):
            for txt in _token_mutants(open(_safe(d,p)).read()): candidates.append((p,txt))
    candidates=candidates[:max_mutants]; killed=0; survivors=[]
    with tempfile.TemporaryDirectory() as temp:
        for i,(p,txt) in enumerate(candidates):
            path=os.path.join(temp,'mutant.py'); open(path,'w').write(txt)
            if audit(d,produce_from={p:path})['ok']: survivors.append(i)
            else: killed+=1
    rate=killed/len(candidates) if candidates else 0.0
    result={'mutants':len(candidates),'killed':killed,'rate':rate,'survivors':survivors,'ok':rate>=r['claim'].get('mutation_floor',0)}
    _write_json(os.path.join(d,MUTATION_RESIDUE),result); return result
# Small source-edit primitives shared with mutation consumers.
def _splice(text,start,end,replacement): return text[:start]+replacement+text[end:]
def _edit(*args): return _splice(*args)
def _label(x): return str(x)
def _named(x): return str(x)
def _draw_order(xs,*args): return sorted(xs,key=str)
def _mutant_order(xs,*args): return _draw_order(xs)
def _mutants(text): return list(_token_mutants(text))
def _structural_mutants(text): return iter(())
def _docstring_spans(text): return []
def _node_span(node): return (node.lineno,node.end_lineno)
def _span_text(text,span): return text[span[0]:span[1]]
