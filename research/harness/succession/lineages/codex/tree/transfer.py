"""Deterministic, declared-content claim transport."""
from __future__ import annotations
import io
import os
import tarfile
from pathlib import Path
from . import kernel, registry
from ._util import copy_into, safe_path

def _files(d, blind=False):
    names=set(registry._claim_files(d,blind))
    names.add(kernel.core.MANIFEST)
    att=safe_path(d,'.reticuli/attest')
    if os.path.isdir(att):
        for p in Path(att).rglob('*'):
            if p.is_file(): names.add(os.path.relpath(str(p), os.path.realpath(d)))
    for link in registry._components(d):
        source=registry._resolve(d,link['component'])
        if source is None: raise kernel.ClaimError(f"missing component: {link['component']}")
        prefix=f".reticuli/deps/{link['component']}"
        for name in registry._claim_files(source,blind=True): names.add(prefix+'/'+name)
        names.add(prefix+'/'+kernel.core.MANIFEST)
    return sorted(names)

def _source(d,name):
    if name.startswith('.reticuli/deps/'):
        parts=name.split('/',3)
        component=parts[2]; child=parts[3]
        source=registry._resolve(d,component)
        if source is None: raise kernel.ClaimError('missing component')
        return safe_path(source,child)
    return safe_path(d,name)

def export(d,path,blind=False):
    checked=kernel.verify(d)
    if not checked['ok']: raise kernel.ClaimError('claim identity changed')
    with tarfile.open(path,'w',format=tarfile.USTAR_FORMAT) as archive:
        for name in _files(d,blind):
            data=Path(_source(d,name)).read_bytes()
            info=tarfile.TarInfo(name); info.size=len(data); info.mode=0o644
            info.uid=info.gid=0; info.uname=info.gname=''; info.mtime=0
            archive.addfile(info,io.BytesIO(data))
    return {'root':checked['root'],'path':path}

def import_(path,into):
    if os.path.exists(into) and os.listdir(into): raise kernel.ClaimError('import target contains bytes')
    os.makedirs(into,exist_ok=True)
    try:
        with tarfile.open(path,'r:*') as archive:
            seen=set()
            for member in archive:
                if not member.isfile() or member.name in seen: raise kernel.ClaimError('unsafe archive member')
                seen.add(member.name)
                dest=safe_path(into,member.name)
                os.makedirs(os.path.dirname(dest),exist_ok=True)
                with archive.extractfile(member) as source, open(dest,'wb') as output:
                    output.write(source.read())
        result=kernel.verify(into)
        if not result['ok']: raise kernel.ClaimError('import identity mismatch')
        return result
    except (OSError,tarfile.TarError) as exc:
        raise kernel.ClaimError(f'cannot import archive: {exc}') from exc
