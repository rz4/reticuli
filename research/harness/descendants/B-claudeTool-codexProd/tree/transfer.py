import os,tarfile,tempfile,io,sys
from . import kernel,registry
from ._kernel.core import _safe

def export(d,path,blind=False):
    if not kernel.verify(d)['ok']: raise kernel.ClaimError('broken claim')
    with tempfile.TemporaryDirectory() as room:
        registry.copy_closure(d,room,blind=blind,dependency_blind=True)
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w',format=tarfile.PAX_FORMAT) as t:
            for base,dirs,files in os.walk(room):
                dirs.sort()
                for fn in sorted(files):
                    p=os.path.join(base,fn); rel=os.path.relpath(p,room); info=t.gettarinfo(p,rel)
                    info.uid=info.gid=0; info.uname=info.gname=''; info.mtime=0
                    with open(p,'rb') as f: t.addfile(info,f)
        raw=buffer.getvalue()
        if path=='-': sys.stdout.buffer.write(raw)
        else:
            with open(path,'wb') as f: f.write(raw)
    return {'ok':True,'root':kernel.verify(d)['root'],'path':path}
def import_(path,into):
    if path!='-' and not os.path.isfile(path): raise kernel.ClaimError('no archive: '+path)
    if os.path.exists(into) and os.listdir(into): raise kernel.ClaimError('target occupied')
    os.makedirs(into,exist_ok=True)
    try:
        raw=sys.stdin.buffer.read() if path=='-' else open(path,'rb').read()
        with tarfile.open(fileobj=io.BytesIO(raw)) as t:
            for m in t.getmembers():
                dest=_safe(into,m.name)
                if not m.isfile(): raise kernel.ClaimError('archive member not regular')
                os.makedirs(os.path.dirname(dest),exist_ok=True)
                with open(dest,'wb') as f: f.write(t.extractfile(m).read())
                os.chmod(dest,m.mode & 0o777)
    except (OSError,tarfile.TarError) as e: raise kernel.ClaimError(str(e)) from e
    v=kernel.verify(into)
    if not v['ok']: raise kernel.ClaimError('archive identity mismatch')
    return v
