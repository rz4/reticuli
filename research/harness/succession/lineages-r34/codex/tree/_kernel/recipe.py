import os, tomllib, math, re
from .core import ClaimError, RECIPE, LEGACY_RECIPE, FORMAT, KINDS, COST_KEYS, _safe

def recipe_path(d):
    for n in (RECIPE,LEGACY_RECIPE):
        p=os.path.join(d,n)
        if os.path.isfile(p):return p
    raise ClaimError('no recipe here: '+str(d))
def _steps(r): return r.get('step',[])
def gates(r):return [s for s in _steps(r) if s['kind']=='gate']
def produces(r):return [s for s in _steps(r) if s['kind']=='produce']
def step_class(s):return {'free':'generated','exact':'pinned'}.get(s.get('class'),s.get('class', 'generated' if s.get('kind')=='produce' else 'pinned'))
def generated_outputs(r):return [s['output'] for s in produces(r) if step_class(s)=='generated']
def _read_input_manifest(d,name):
    try:
        lines=open(_safe(d,name),encoding='utf-8').read().splitlines()
    except (OSError,UnicodeError) as e:raise ClaimError(str(e))
    out=[]
    for l in lines:
        l=l.strip()
        if not l or l.startswith('#'):continue
        m=re.match(r'^[0-9a-fA-F]{64}\s+(.+)$',l); p=m.group(1) if m else l
        _safe(d,p)
        if any(c in p for c in '*?['):raise ClaimError('manifest is a fixed list: '+p)
        out.append(p)
    return out

def _inputs(r,d=None):
    c=r.get('claim',r.get('record',{})); out=list(c.get('inputs',[]) or [])
    if c.get('environment'):out.append(c['environment'])
    if c.get('inputs_manifest'):
        if d is None:raise ClaimError('manifest requires directory')
        out += [c['inputs_manifest']]+_read_input_manifest(d,c['inputs_manifest'])
    return list(dict.fromkeys(out))

def number(v,minimum=0,strict=False):
    return type(v) in (int,float) and math.isfinite(v) and (v>minimum if strict else v>=minimum)
def obligations(c,record=False):
    for k,lower in [('tolerance',0 if record else 1),('mutation_floor',0)]:
        if k in c and not number(c[k],lower):raise ClaimError('invalid '+k)
    if 'envelope' in c:
        e=c['envelope']
        if not isinstance(e,dict) or not e or any(k not in COST_KEYS or not number(v,0,True) for k,v in e.items()):raise ClaimError('invalid envelope')

def load_recipe(d):
    try:
        with open(recipe_path(d),'rb') as f:r=tomllib.load(f)
    except (OSError,ValueError,UnicodeError) as e:raise ClaimError('invalid recipe: '+str(e)) from e
    c=r.get('claim',r.get('record'))
    if not isinstance(c,dict) or not isinstance(c.get('name'),str):raise ClaimError('claim name must be a string')
    fmt=c.get('format',1)
    if type(fmt)!=int or fmt<1:raise ClaimError('invalid claim format')
    if fmt>FORMAT:raise ClaimError(f'claim format {fmt} is newer than this kernel understands (format {FORMAT}); upgrade reticuli')
    obligations(c)
    if not isinstance(c.get('inputs',[]),list):raise ClaimError('inputs must be a list')
    if c.get('inputs_manifest') and fmt<2:raise ClaimError('inputs_manifest needs format 2')
    for p in _inputs(r,d):_safe(d,p)
    if not isinstance(r.get('step',[]),list):raise ClaimError('step must be an array')
    for s in _steps(r):
        if not isinstance(s,dict) or s.get('kind') not in KINDS:raise ClaimError('unknown step kind')
        # Output confinement is checked by each operation before touching it.
        if not isinstance(s.get('output'),str):raise ClaimError('step needs output')
        if s['kind']=='gate' and not isinstance(s.get('run'),str):raise ClaimError('gate needs run')
        cl=step_class(s)
        if cl=='carried' and (fmt<5 or s['kind']!='produce'):raise ClaimError('carried needs format 5 and produce')
        if fmt>=5 and cl not in ('generated','pinned','validated','carried'):raise ClaimError('unknown class '+str(cl))
    for key in ('constrains','assembles'):
        if key in c and fmt<5:raise ClaimError(key+' needs format 5')
    if 'constrains' in c:
        if not isinstance(c['constrains'],dict):raise ClaimError('invalid constrains')
        for p,targets in c['constrains'].items():
            if p not in _inputs(r,d) or not isinstance(targets,list) or not all(isinstance(t,str) for t in targets):raise ClaimError('invalid constrains')
    if 'assembles' in c:
        if not isinstance(c['assembles'],list) or not all(isinstance(x,str) and re.fullmatch(r'[^/@]+@[0-9a-f]{64}',x) for x in c['assembles']):raise ClaimError('invalid assembles')
    if fmt in (4,5):
        earlier=[]
        for g in gates(r):
            for p in earlier:
                if re.search(r'(?<![\w])'+re.escape(p)+r'(?![\w])',g['run']):raise ClaimError('gate reads earlier output '+p+'; declare format = 6')
            earlier.append(g['output'])
    return r
