"""Three-machine comparison and deterministic mutation probes."""
from __future__ import annotations
import ast
import hashlib
import json
import os
import re
import shutil
import tempfile

from . import core, recipe, identity, attest

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/')
_OP_ALTS = {'>': '<', '<': '>', '>=': '<=', '<=': '>=', '==': '!=', '!=': '=='}
_OP_KIND = {x: 'comparison' for x in _COMPARISON}
_STRING_LITERAL = re.compile(r'([\'\"])(.*?)(\1)')
_WORD_ALTS = {'True': 'False', 'False': 'True'}

def _named(x): return getattr(x, '__name__', str(x))
def _label(x): return _named(x)
def _span_text(text, span): return text[span[0]:span[1]]
def _splice(text, start, end, replacement): return text[:start] + replacement + text[end:]
def _edit(text, start, end, replacement): return _splice(text, start, end, replacement)
def _node_span(node): return (getattr(node, 'lineno', 0), getattr(node, 'end_lineno', 0))
def _docstring_spans(tree): return [_node_span(n) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
def _draw_order(items, seed): return sorted(items, key=lambda x: hashlib.sha256((seed + repr(x)).encode()).hexdigest())
def _mutant_order(items, seed): return _draw_order(items, seed)
def _token_mutants(source):
    return list(dict.fromkeys(source.replace(op, _OP_ALTS[op], 1) for op in _COMPARISON if op in source))
def _structural_mutants(source):
    out=[]
    for old,new in (('a - b','a + b'), ('b - a','b + a'), ('return ', 'return -'), ('==', '!='), (' > ', ' < '), (' - ', ' + ')):
        if old in source: out.append(source.replace(old,new,1))
    return list(dict.fromkeys(out))
def _mutants(source): return list(dict.fromkeys(_structural_mutants(source)+_token_mutants(source)))
def _machine(path): return 'record' if os.path.isfile(path) else 'directory'

def gate_deciders(command):
    import shlex
    try: tokens=shlex.split(command)
    except ValueError: return []
    answer=[]
    for i,tok in enumerate(tokens):
        if tok in _INTERPRETERS:
            j=i+1
            if j<len(tokens) and tokens[j]=='-m':
                if j+1<len(tokens) and tokens[j+1]=='pytest':
                    answer.extend(t for t in tokens[j+2:next((k for k in range(j+2,len(tokens)) if tokens[k] in _OPERATORS),len(tokens))] if t and not t.startswith('-'))
            elif j<len(tokens) and not tokens[j].startswith('-'):
                answer.append(tokens[j])
        elif tok.startswith('./'): answer.append(tok[2:])
    return list(dict.fromkeys(answer))

def vacuous_gates(parsed):
    generated={s['output'] for s in parsed.get('step',[]) if s.get('kind')=='produce' and s.get('class','generated')=='generated'}
    pinned=set(parsed.get('claim',{}).get('inputs',[]))
    return [s['output'] for s in parsed.get('step',[]) if s.get('kind')=='gate' and (d:=gate_deciders(s['run'])) and all(x in generated and x not in pinned for x in d)]

def mutation_score(directory, max_mutants=core.MUTANT_CEILING):
    from reticuli import kernel
    parsed=kernel.load_recipe(directory)
    candidates=[]
    for name in recipe.generated_outputs(parsed):
        path=core._safe(directory,name)
        if not os.path.isfile(path) or not name.endswith('.py'): continue
        with open(path,encoding='utf-8') as f: source=f.read()
        candidates.extend((name,m) for m in _mutants(source) if m!=source)
    candidates=_draw_order(candidates,kernel.verify(directory)['root'])[:max_mutants]
    killed=0; survivors=[]
    for name,mutant in candidates:
        with tempfile.TemporaryDirectory() as tmp:
            path=os.path.join(tmp,name)
            os.makedirs(os.path.dirname(path),exist_ok=True)
            with open(path,'w',encoding='utf-8') as f:f.write(mutant)
            if not kernel.audit(directory,produce_from={name:path})['ok']: killed+=1
            else:survivors.append(name)
    result={'mutants':len(candidates),'killed':killed,'survivors':survivors,'rate':killed/len(candidates) if candidates else 0.0}
    core._write_json(core._safe(directory,core.MUTATION_RESIDUE),result)
    return result

def _leg(path):
    from reticuli import kernel
    if os.path.isfile(path):
        doc=kernel.record_read(path)
        return {'root':doc['root'],'digest':doc['build_digest'],'audited':all(g['status']=='ok' for g in doc['gates']), 'cost':doc.get('cost'), 'claim':doc.get('claim'), 'producer':doc.get('producer'), 'record':doc}
    checked=kernel.verify(path)
    audited=kernel.audit(path)
    parsed=kernel.load_recipe(path)['claim']
    return {'root':checked['root'],'digest':kernel.build_digest(path),'audited':checked['ok'] and audited['ok'],'cost':kernel.cost(path),'claim':parsed,'producer':kernel.independence(path),'record':None}

def crosscheck(m1,m2,m3,*,mutants=None):
    from reticuli import kernel
    paths=[os.path.realpath(str(p)) for p in (m1,m2,m3)]
    if len(set(paths))!=3: raise core.ClaimError('three distinct machines required')
    a,b,c=(_leg(p) for p in (m1,m2,m3))
    roots=dict(zip(('M1','M2','M3'),(a['root'],b['root'],c['root'])))
    audited=dict(zip(('M1','M2','M3'),(a['audited'],b['audited'],c['audited'])))
    equivalence=len(set(roots.values()))==1
    reuse=a['digest']==b['digest']
    ca,cb=a['cost'] or {},c['cost'] or {}
    unit=next((u for u in core.COST_LADDER if u in ca and u in cb),None)
    tol=(a['claim'] or {}).get('tolerance',core.TOLERANCE)
    comparable=core.TOLERANCE if False else None
    if unit:
        x,y=ca[unit],cb[unit]
        comparable=(x==y) if not x or not y else max(x/y,y/x)<=tol
    cost={'unit':unit,'original':a['cost'],'rebuild':c['cost'],'comparable':comparable,'envelope':{}}
    rejected=[]; incomplete=[]
    if not equivalence: rejected.append('root')
    if not reuse: rejected.append('reuse')
    if not all(audited.values()): rejected.append('audit')
    if 'tolerance' in (a['claim'] or {}) and comparable is False: rejected.append('tolerance')
    if a['claim'] is None: incomplete.append('declared conditions')
    envelope=(a['claim'] or {}).get('envelope',{})
    for key,ceiling in envelope.items():
        value=cb.get(key)
        within=None if value is None else value<=ceiling
        cost['envelope'][key]={'ceiling':ceiling,'measured':value,'within':within}
        if within is False: rejected.append('envelope '+key)
        if within is None: incomplete.append('envelope '+key)
    score=None
    floor=(a['claim'] or {}).get('mutation_floor')
    if floor is not None:
        if mutants is None or os.path.isfile(m3): incomplete.append('mutation floor')
        else:
            score=mutation_score(m3,max_mutants=mutants)
            score['ok']=score['rate']>=floor
            if not score['ok']: rejected.append('mutation floor')
    producer=c['producer'] or {}
    if producer.get('vendor') and producer.get('model'):
        independence=f"declared: {producer['vendor']}/{producer['model']}, blind workspace; not proven" if producer.get('blind') else 'unestablished'
    else:independence='unestablished'
    verdict='reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied':verdict=='accept','verdict':verdict,'rejected':rejected,'incomplete':incomplete,'roots':roots,'equivalence':equivalence,'reuse':reuse,'audited':audited,'cost':cost,'mutation_score':score,'independence':independence}

def record_proof(m1,m2,m3,*,mutants=None):
    from reticuli import kernel
    if not os.path.isdir(m1): raise core.ClaimError('proof requires a directory M1')
    result=crosscheck(m1,m2,m3,mutants=mutants)
    result['proof_recorded']=False
    if not result['satisfied']:return result
    trails=[]
    for path in (m2,m3):
        if os.path.isfile(path):
            anchor=os.environ.get(core._ENV_SIGNERS)
            if not anchor:raise core.ClaimError('record has no trust anchor')
            signer=kernel.record_signer(path,anchor)
            if not signer:raise core.ClaimError('record signature not anchored')
            trails.append({'digest':kernel.record_digest(kernel.record_read(path)),'signer':signer})
    manifest=kernel.read_manifest(m1)
    manifest['proof']={'kind':'crosscheck','root':result['roots']['M1'],'records':trails}
    core._write_json(core._safe(m1,core.MANIFEST),manifest)
    result['proof_recorded']=True
    return result
