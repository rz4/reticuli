"""Deterministic transfer of declared claim bytes and component criteria."""
import io
import os
import tarfile
from . import kernel
from ._util import safe_path, declared_inputs
from . import registry

def _files(directory, blind, prefix='', seen=None):
    seen=set() if seen is None else seen
    recipe=kernel.load_recipe(directory)
    recipe_name=os.path.basename(next(p for p in ('reticuli.toml','claim.toml') if os.path.isfile(os.path.join(directory,p))))
    names=[recipe_name,kernel.MANIFEST]+declared_inputs(directory)
    for step in recipe.get('step',[]):
        cls=step.get('class','generated' if step['kind']=='produce' else 'pinned')
        if not blind or cls not in ('generated','free'):
            names.append(step['output'])
    for residue in ('.reticuli/attest','.reticuli/mint'):
        root=os.path.join(directory,residue)
        if os.path.isdir(root):
            for base,_,files in os.walk(root):
                for f in files: names.append(os.path.relpath(os.path.join(base,f),directory))
    for name in names:
        source=safe_path(directory,name)
        if os.path.isfile(source):
            key=prefix+name
            if key not in seen:
                seen.add(key)
                yield key,source
    for link in kernel.read_manifest(directory).get('components',[]):
        name=link['component']
        component=registry._component(directory,name)
        if not component: raise kernel.ClaimError(f'missing component {name}')
        yield from _files(component,True,prefix+f'.reticuli/deps/{name}/',seen)

def export(directory, path, *, blind=False):
    if not kernel.verify(directory)['ok']: raise kernel.ClaimError('claim identity mismatch')
    files=sorted(_files(directory,blind))
    with tarfile.open(path,'w',format=tarfile.USTAR_FORMAT) as archive:
        for name,source in files:
            data=open(source,'rb').read()
            info=tarfile.TarInfo(name)
            info.size=len(data); info.mode=0o644; info.mtime=0
            info.uid=info.gid=0; info.uname=info.gname=''
            archive.addfile(info,io.BytesIO(data))
    return {'path':path,'files':len(files)}

def import_(path, into):
    os.makedirs(into,exist_ok=True)
    with tarfile.open(path,'r') as archive:
        for member in archive:
            if not member.isfile(): raise kernel.ClaimError('unexpected archive member')
            target=safe_path(into,member.name)
            os.makedirs(os.path.dirname(target),exist_ok=True)
            with archive.extractfile(member) as source, open(target,'wb') as dest:
                dest.write(source.read())
    checked=kernel.verify(into)
    if not checked['ok']: raise kernel.ClaimError('import identity mismatch')
    return checked
