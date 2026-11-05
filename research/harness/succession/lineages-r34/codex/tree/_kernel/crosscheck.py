import os, re, shlex, ast, json, tempfile, hashlib, random
from .core import *
from .core import _hash_file, _safe, _write_json, _now
from .recipe import load_recipe, produces, gates, step_class
from .identity import build_digest
from .seal import verify, seal, read_manifest
from .build import audit
from .run import cost, independence, _independence_line, _in_band
from .attest import record_read, record_digest, record_signer
_COMPARISON=('>','<','>=','<=','==','!=')
_INTERPRETERS=frozenset({'Rscript','awk','lua','python','python3','python2','node','ruby','perl','dash','deno','py.test','zsh','tclsh','php','sh','bash','py','pytest'})
_OPERATORS=frozenset({'&','\n','|','||','&&',';'})
_SKIP_VALUE=frozenset({'-m','-p','--module','-X','-c','-e'})
_ARITHMETIC=('+','-','*','/')
_OP_ALTS={'+':'-','-':'+','*':'+'}
_OP_KIND={}
_STRING_LITERAL=re.compile(r'([\"\']).*?\1')
_WORD_ALTS={'True':'False','False':'True'}

def gate_deciders(command):
    if isinstance(command,dict):return {g['output']:gate_deciders(g['run']) for g in gates(command)}
    out=[]
    for segment in re.split(r'&&|\|\||[;|\n]',command):
        try:tokens=shlex.split(segment)
        except ValueError:continue
        if not tokens:continue
        cmd=os.path.basename(tokens[0])
        if tokens[0].startswith('./'):out.append(tokens[0][2:]);continue
        if cmd not in _INTERPRETERS:continue
        i=1
        while i<len(tokens):
            t=tokens[i]
            if t in ('-c','-e'):break
            if t in ('-m','--module'):
                i+=2
                while i<len(tokens) and tokens[i].startswith('-'):i+=1
                if i<len(tokens):out.append(tokens[i])
                break
            if t in ('-X','-p'):i+=2;continue
            if t.startswith('-'):i+=1;continue
            out.append(t);break
    return list(dict.fromkeys(out))
def vacuous_gates(r):
    generated={s['output'] for s in produces(r) if step_class(s)=='generated'}
    inputs=set(r.get('claim',{}).get('inputs',[]))
    return [g['output'] for g in gates(r) if gate_deciders(g['run']) and all(p in generated and p not in inputs for p in gate_deciders(g['run']))]

def _machine(d):
    if os.path.isfile(d):
        x=record_read(d);return dict(x,ok=True,audited=all(g['status']=='ok' for g in x['gates']))
    v=verify(d);a=audit(d)
    return dict(v,build_digest=build_digest(d),audited=a['ok'],cost=cost(d) or {},producer=independence(d),claim={k:v for k,v in load_recipe(d).get('claim',{}).items() if k in ('tolerance','envelope','mutation_floor')})

def crosscheck(m1,m2,m3,tolerance=None,mutants=None,**kwargs):
    paths=[m1,m2,m3]
    if len(set(map(os.path.realpath,paths)))!=3:raise ClaimError('three machines require distinct paths')
    ms=[_machine(d) for d in paths];a,b,c=ms
    roots=dict(zip(('M1','M2','M3'),[x['root'] for x in ms]));aud=dict(zip(roots,[x['audited'] for x in ms]))
    eq=len(set(roots.values()))==1 and all(x['ok'] for x in ms);reuse=a['build_digest']==b['build_digest']
    rej=[];inc=[]
    if not eq:rej.append('identity')
    if not reuse:rej.append('reuse')
    if not all(aud.values()):rej.append('audit')
    declared=a.get('claim')
    if declared is None:inc.append('declared conditions');declared={}
    dt=declared.get('tolerance');tol=min(dt,tolerance) if dt is not None and tolerance is not None else dt if dt is not None else tolerance or TOLERANCE
    ca=a.get('cost',{});cc=c.get('cost',{});unit=next((k for k in COST_LADDER if k in ca and k in cc),None)
    comp=_in_band(cc[unit],ca[unit],tol) if unit else None
    co={'M1':ca,'M3':cc,'unit':unit,'comparable':comp,'tolerance':tol,'declared_tolerance':dt,'tightened':dt is not None and tol<dt,'envelope':{}}
    if dt is not None:
        if comp is None:inc.append('tolerance unmeasured')
        elif not comp:rej.append('tolerance')
    for k,ceiling in declared.get('envelope',{}).items():
        w=cc[k]<=ceiling if k in cc else None;co['envelope'][k]={'ceiling':ceiling,'paid':cc.get(k),'within':w}
        if w is None:inc.append('envelope '+k)
        elif not w:rej.append('envelope '+k)
    score=None
    if mutants and os.path.isdir(m3):score=mutation_score(m3,max_mutants=mutants)
    if 'mutation_floor' in declared:
        if score is None or score['rate'] is None:inc.append('mutation_floor')
        else:
            score['ok']=score['rate']>=declared['mutation_floor']
            if not score['ok']:rej.append('mutation_floor')
    verdict='reject' if rej else 'incomplete' if inc else 'accept'
    return {'satisfied':verdict=='accept','verdict':verdict,'rejected':rej,'incomplete':inc,'roots':roots,'root':roots['M1'],'equivalence':eq,'reuse':reuse,'audited':aud,'cost':co,'independence':_independence_line(c.get('producer',{})),'mutation_score':score}

def record_proof(m1,m2,m3,**kwargs):
    if not os.path.isdir(m1):raise ClaimError('proof needs a directory M1')
    records=[]
    for p in (m2,m3):
        if os.path.isfile(p):
            who=record_signer(p,os.environ.get('RETICULI_SIGNERS'))
            if not who:raise ClaimError('record needs a verified anchor')
            records.append({'digest':record_digest(record_read(p)),'signer':who})
    r=crosscheck(m1,m2,m3,**kwargs);r['proof_recorded']=r['satisfied']
    if r['satisfied']:seal(m1,proof={'kind':'crosscheck','m2':r['roots']['M2'],'m3':r['roots']['M3'],'records':records})
    return r

def _token_mutants(text):
    # Replace one operator or literal at a time, retaining valid syntax.
    for m in re.finditer(r'(?<![<>!=])>=|<=|==|!=|(?<![<>])>|<|\+|(?<!-)-(?!>)|\*|\b\d+\b|\bTrue\b|\bFalse\b',text):
        t=m.group();alts={'>':['<','>='],'<':['>','<='],'>=':['<','>'],'<=':['>','<'],'==':['!='],'!=':['=='],'+':['-'],'-':['+'],'*':['+'],'True':['False'],'False':['True']}.get(t,[str(int(t)+1)] if t.isdigit() else [])
        for v in alts:
            s=text[:m.start()]+v+text[m.end():]
            try:ast.parse(s)
            except SyntaxError:continue
            yield s

def mutation_score(d,max_mutants=20,**kwargs):
    r=load_recipe(d);candidates=[]
    for s in produces(r):
        n=s['output']
        if step_class(s)!='generated' or s.get('from') or not n.endswith('.py'):continue
        p=_safe(d,n)
        if not os.path.isfile(p):continue
        text=open(p,encoding='utf-8').read()
        for mut in _token_mutants(text):candidates.append((n,mut))
    # Stable ordering depends only on the identity and mutant text.
    candidates=sorted(set(candidates),key=lambda x:hashlib.sha256((verify(d)['root']+repr(x)).encode()).hexdigest())[:max_mutants]
    survivors=[];killed=0
    with tempfile.TemporaryDirectory() as tmp:
        for i,(n,mut) in enumerate(candidates):
            p=os.path.join(tmp,'mutant.py');open(p,'w',encoding='utf-8').write(mut)
            if audit(d,produce_from={n:p})['ok']:survivors.append(n+':'+hashlib.sha256(mut.encode()).hexdigest()[:12])
            else:killed+=1
    rate=killed/len(candidates) if candidates else None
    out={'mutants':len(candidates),'killed':killed,'rate':rate,'survivors':survivors,'ok':rate is not None and rate>=r.get('claim',{}).get('mutation_floor',0),'root':verify(d)['root']}
    _write_json(os.path.join(d,MUTATION_RESIDUE),out);return out

def _docstring_spans(text):return [(n.lineno,n.end_lineno) for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)]
def _draw_order(items,seed=''):return sorted(items,key=lambda x:hashlib.sha256((str(seed)+str(x)).encode()).hexdigest())
def _edit(text,start,end,value):return text[:start]+value+text[end:]
def _label(x):return str(x)
def _mutant_order(x,seed=''):return _draw_order(x,seed)
def _mutants(text):return list(_token_mutants(text))
def _named(x):return str(x)
def _node_span(n):return (n.lineno,n.col_offset,n.end_lineno,n.end_col_offset)
def _span_text(text,node):return ast.get_source_segment(text,node)
def _splice(text,start,end,value):return _edit(text,start,end,value)
def _structural_mutants(text):return _token_mutants(text)
