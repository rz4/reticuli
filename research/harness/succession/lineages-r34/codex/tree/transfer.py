import os, tarfile, tempfile, shutil, sys, io
from . import kernel, registry
from ._kernel.core import _safe

def export(d,path,blind=False):
    v=kernel.verify(d)
    if not v['ok']:raise kernel.ClaimError('broken claim')
    with tempfile.TemporaryDirectory() as tmp:
        registry._copy_claim(d,tmp,blind)
        for p in registry._closure(d):registry._copy_claim(p,os.path.join(tmp,kernel.STORE,'deps',kernel.read_manifest(p)['name']),True)
        stream=sys.stdout.buffer if path=='-' else None
        with tarfile.open(fileobj=stream,name=None if stream else path,mode='w| ' .strip() if stream else 'w',format=tarfile.PAX_FORMAT) as t:
            for base,dirs,files in os.walk(tmp):
                dirs.sort()
                for fn in sorted(files):
                    p=os.path.join(base,fn);n=os.path.relpath(p,tmp);info=t.gettarinfo(p,arcname=n)
                    info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
                    with open(p,'rb') as f:t.addfile(info,f)
    return dict(v,path=path)

def import_(path,into):
    if path!='-' and not os.path.isfile(path):raise kernel.ClaimError('no archive: '+path)
    if os.path.exists(into) and os.listdir(into):raise kernel.ClaimError('target holds bytes')
    os.makedirs(into,exist_ok=True)
    try:
        stream=io.BytesIO(sys.stdin.buffer.read()) if path=='-' else None
        with tarfile.open(fileobj=stream,name=None if stream else path,mode='r:*') as t:
            for m in t.getmembers():
                p=_safe(into,m.name)
                if not m.isfile():raise kernel.ClaimError('archive entry is not a regular file')
                os.makedirs(os.path.dirname(p),exist_ok=True)
                with t.extractfile(m) as src,open(p,'wb') as dst:shutil.copyfileobj(src,dst)
                os.chmod(p,m.mode & 0o777)
    except (tarfile.TarError,OSError) as e:raise kernel.ClaimError('archive: '+str(e))
    v=kernel.verify(into)
    if not v['ok']:raise kernel.ClaimError('imported identity mismatch')
    return v
