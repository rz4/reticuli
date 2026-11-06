import os,sys,tempfile,shutil,json,platform
from . import kernel
from ._kernel.core import digest,_write_json,_now

def fingerprint(d): return {'root':kernel.verify(d)['root'],'build':kernel.build_digest(d),'platform':platform.platform(),'python':sys.version}
def _cache(): return os.environ.get('RETICULI_CACHE',os.path.join(tempfile.gettempdir(),'reticuli-earned'))
def remember(d,result):
    if result.get('ok'): _write_json(os.path.join(_cache(),digest(fingerprint(d))+'.json'),{'result':result,'when':_now(),'source':'self'})
def lookup(d):
    try: return json.load(open(os.path.join(_cache(),digest(fingerprint(d))+'.json')))
    except OSError: return None
def layered_audit(spec):
    rows=[]
    for layer in spec:
        with tempfile.TemporaryDirectory() as room:
            files=layer['files']; check,source=layer['check']; paths={**files,check:source}
            for p,src in paths.items():
                dest=os.path.join(room,p); os.makedirs(os.path.dirname(dest),exist_ok=True); shutil.copy2(src,dest)
            key=digest({p:kernel._hash_file(src) for p,src in paths.items()}|{'gate':layer['gate']})
            cache=os.path.join(_cache(),key+'.json')
            if os.path.isfile(cache): row={'name':layer['name'],'ok':True,'status':'reused','reused':True,'source':'self'}
            else:
                result=kernel.run_gate(layer['gate'],room,None); row={'name':layer['name'],'ok':result['status']=='ok','status':'earned','reused':False}
                if row['ok']: _write_json(cache,{'when':_now(),'source':'self'})
            rows.append(row)
    return {'ok':all(r['ok'] for r in rows),'layers':rows}
