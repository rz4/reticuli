import os, tomllib, re, math
from .core import ClaimError, FORMAT, RECIPE, LEGACY_RECIPE, KINDS, COST_KEYS, _safe, _hash_file

def recipe_path(d):
    for n in (RECIPE,LEGACY_RECIPE):
        if os.path.isfile(os.path.join(d,n)): return os.path.join(d,n)
    raise ClaimError(f'no recipe in {d}')
def _steps(r): return r.get('step',[])
def gates(r): return [s for s in _steps(r) if s['kind']=='gate']
def produces(r): return [s for s in _steps(r) if s['kind']=='produce']
def step_class(s): return s.get('class','generated' if s['kind']=='produce' else 'pinned')
def generated_outputs(r): return [s['output'] for s in produces(r) if step_class(s) in ('generated','free')]
def _read_input_manifest(d,p):
    try:
        out=[]
        for line in open(_safe(d,p),encoding='utf8'):
            line=line.strip()
            if not line or line.startswith('#'): continue
            m=re.match(r'^([0-9a-f]{64})\s+(.+)$',line)
            name=m[2] if m else line
            path=_safe(d,name)
            if any(c in name for c in '*?['): raise ClaimError('manifest must list fixed paths')
            got=_hash_file(path)
            if m and got!=m[1]: raise ClaimError(f'manifest digest mismatch: {name}')
            out.append(name)
        return out
    except OSError as e: raise ClaimError(str(e)) from e
def _inputs(r,d=None):
    c=r.get('claim',{}); out=list(c.get('inputs',[]))
    if c.get('environment'): out.append(c['environment'])
    if c.get('inputs_manifest'):
        out.append(c['inputs_manifest'])
        if d is not None: out.extend(_read_input_manifest(d,c['inputs_manifest']))
    return list(dict.fromkeys(out))
def number(v,minimum=0,strict=False):
    return type(v) in (float,int) and math.isfinite(v) and (v>minimum if strict else v>=minimum)
def load_recipe(d):
    try:
        with open(recipe_path(d),'rb') as f: r=tomllib.load(f)
        c=r.get('claim',r.get('record'))
        if not isinstance(c,dict) or not isinstance(c.get('name'),str): raise ClaimError('claim name must be a string')
        fmt=c.get('format',1)
        if type(fmt)!=int or fmt<1: raise ClaimError('invalid claim format')
        if fmt>FORMAT: raise ClaimError(f'claim format {fmt} is newer than this kernel understands (format {FORMAT}); upgrade reticuli')
        if not isinstance(c.get('inputs',[]),list): raise ClaimError('inputs must be a list')
        for p in c.get('inputs',[]): _safe(d,p)
        for key in ('environment','inputs_manifest'):
            if key in c: _safe(d,c[key])
        if 'inputs_manifest' in c and fmt<2: raise ClaimError('inputs_manifest needs format 2')
        for key,minval in [('tolerance',1),('mutation_floor',0)]:
            if key in c and not number(c[key],minval): raise ClaimError(f'invalid {key}')
        if 'envelope' in c:
            e=c['envelope']
            if not isinstance(e,dict) or not e or any(k not in COST_KEYS or not number(v,0,True) for k,v in e.items()): raise ClaimError('invalid envelope')
        if any(k in c for k in ('constrains','assembles')) and fmt<5: raise ClaimError('constrains/assembles need format 5')
        if 'constrains' in c:
            if not isinstance(c['constrains'],dict): raise ClaimError('invalid constrains')
            for k,v in c['constrains'].items():
                if k not in _inputs(r,d) or not isinstance(v,list) or not all(isinstance(a,str) for a in v): raise ClaimError('invalid constrains input')
        if 'assembles' in c:
            if not isinstance(c['assembles'],list) or any(not isinstance(x,str) or not re.fullmatch(r'[^/@]+@[0-9a-f]{64}',x) for x in c['assembles']): raise ClaimError('invalid assembles')
        earlier=[]
        if not isinstance(_steps(r),list): raise ClaimError('invalid steps')
        for s in _steps(r):
            if not isinstance(s,dict) or s.get('kind') not in KINDS: raise ClaimError('unknown step kind')
            _safe('/__reticuli_path_validation__',s.get('output'))
            cl=step_class(s)
            if cl=='carried' and (fmt<5 or s['kind']!='produce'): raise ClaimError('invalid carried class')
            if fmt>=5 and cl not in ('generated','pinned','validated','carried','free','exact'): raise ClaimError('unknown class')
            if s['kind']=='gate':
                if not isinstance(s.get('run'),str): raise ClaimError('gate needs run')
                if fmt in (4,5) and any(re.search(r'(?<![\w.])'+re.escape(p)+r'(?![\w.])',s['run']) for p in earlier): raise ClaimError('gate order dependency: declare format = 6')
                earlier.append(s['output'])
        return r
    except (OSError,ValueError,TypeError,KeyError) as e: raise ClaimError(f'invalid recipe: {e}') from e
