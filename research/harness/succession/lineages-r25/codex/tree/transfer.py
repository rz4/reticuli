"""Deterministic, declared-content claim archives."""
import io
import os
import shutil
import tarfile
from . import kernel, registry
from ._kernel import recipe


def _files(directory, blind=False):
    parsed=kernel.load_recipe(directory)
    names={os.path.basename(recipe.recipe_path(directory)),kernel.MANIFEST}
    names.update(recipe._inputs(parsed,directory))
    for step in parsed.get('step',[]):
        name=step['output']
        if step.get('class','generated' if step['kind']=='produce' else 'pinned')!='generated' or (not blind and os.path.isfile(os.path.join(directory,name))):
            names.add(name)
    attest_dir=os.path.join(directory,'.reticuli','attest')
    if os.path.isdir(attest_dir):
        for base,_,files in os.walk(attest_dir):
            for n in files: names.add(os.path.relpath(os.path.join(base,n),directory))
    # The closure carries each component's claim and pins once, flat. Generated
    # component bytes stay in the parent build where they were shipped.
    closure=registry._closure(directory)
    own=kernel.read_manifest(directory)['root']
    for root,path in closure.items():
        if root==own: continue
        stem=os.path.join('.reticuli','deps',kernel.read_manifest(path)['name'])
        cp=kernel.load_recipe(path)
        names.add(os.path.join(stem,os.path.basename(recipe.recipe_path(path))))
        names.add(os.path.join(stem,kernel.MANIFEST))
        names.update(os.path.join(stem,n) for n in recipe._inputs(cp,path))
        for step in cp.get('step',[]):
            if step.get('class','generated' if step['kind']=='produce' else 'pinned')!='generated':
                names.add(os.path.join(stem,step['output']))
    return sorted(names),closure

def export(directory, tar_path, *, blind=False):
    if not kernel.verify(directory)['ok']: raise kernel.ClaimError('cannot export changed claim')
    names,closure=_files(directory,blind)
    with tarfile.open(tar_path,'w',format=tarfile.USTAR_FORMAT) as archive:
        for name in names:
            parts=name.split('/')
            if len(parts)>3 and parts[:2]==['.reticuli','deps']:
                source=next((p for p in closure.values() if kernel.read_manifest(p)['name']==parts[2]),None)
                rel='/'.join(parts[3:])
            else: source=directory; rel=name
            if source is None: raise kernel.ClaimError('missing component in export')
            path=os.path.join(source,rel)
            if not os.path.isfile(path): continue
            with open(path,'rb') as f: data=f.read()
            info=tarfile.TarInfo(name); info.size=len(data); info.mode=0o644
            info.mtime=0; info.uid=info.gid=0; info.uname=info.gname=''
            archive.addfile(info,io.BytesIO(data))
    return {'path':tar_path,'root':kernel.read_manifest(directory)['root']}

def import_(tar_path, into):
    if os.path.exists(into) and os.listdir(into): raise kernel.ClaimError('import target contains bytes')
    os.makedirs(into,exist_ok=True)
    with tarfile.open(tar_path) as archive:
        for member in archive:
            if not member.isfile() or member.name.startswith('/') or any(p in ('','.','..') for p in member.name.split('/')):
                raise kernel.ClaimError('unsafe archive member')
            target=os.path.join(into,member.name)
            os.makedirs(os.path.dirname(target),exist_ok=True)
            with archive.extractfile(member) as src, open(target,'wb') as dst: shutil.copyfileobj(src,dst)
    result=kernel.verify(into)
    if not result['ok']: raise kernel.ClaimError('import identity mismatch')
    return result
