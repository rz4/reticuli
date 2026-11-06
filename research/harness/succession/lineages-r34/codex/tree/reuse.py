import os, sys, tempfile, shutil
from . import kernel
from ._kernel.core import digest, _write_json, _read_json, _now, dump_recipe

def fingerprint(d):return {'root':kernel.verify(d)['root'],'build':kernel.build_digest(d),'platform':sys.platform,'python':sys.version}
def _cache():return os.environ.get('RETICULI_CACHE',os.path.join(tempfile.gettempdir(),'reticuli-earned'))
def _path(fp):return os.path.join(_cache(),digest(fp)+'.json')
def remember(d,verdict):
    if verdict.get('ok'):_write_json(_path(fingerprint(d)),{'verdict':verdict,'when':_now(),'source':'self','fingerprint':fingerprint(d)})
def lookup(d):
    p=_path(fingerprint(d));return _read_json(p) if os.path.isfile(p) else None

def layered_audit(spec):
    rows=[]
    for layer in spec:
        with tempfile.TemporaryDirectory() as d:
            files=layer['files'];check,src=layer['check']
            for n,p in dict(files,**{check:src}).items():
                dst=os.path.join(d,n);os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copy2(p,dst)
            r={'claim':{'name':layer['name'],'format':3,'inputs':[check]},'step':[{'kind':'produce','output':n,'class':'generated'} for n in files]+[{'kind':'gate','output':layer['verdict'],'class':'validated','run':layer['gate']+' && printf ok > '+layer['verdict']}]}
            open(os.path.join(d,kernel.RECIPE),'w').write(dump_recipe(r))
            # Cache key includes criteria and implementation, without executing a gate.
            open(os.path.join(d,layer['verdict']),'w').write('ok');kernel.seal(d)
            cached=lookup(d)
            if cached:rows.append({'name':layer['name'],'status':'reused','ok':True,'reused':cached['when'],'source':cached['source']})
            else:
                a=kernel.audit(d);remember(d,a);rows.append({'name':layer['name'],'status':'earned' if a['ok'] else 'failed','ok':a['ok']})
    return {'ok':all(x['ok'] for x in rows),'layers':rows}
