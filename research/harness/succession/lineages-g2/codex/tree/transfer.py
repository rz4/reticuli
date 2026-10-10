"""Deterministic transport of a claim and its component criteria."""
import io
import os
import tarfile
from . import kernel, registry
from ._kernel import core, recipe

def _files(source, prefix='', *, blind=False, component=False):
    parsed = kernel.load_recipe(source)
    names = {os.path.basename(recipe.recipe_path(source)), kernel.MANIFEST}
    names.update(recipe._inputs(parsed, source))
    for step in parsed.get('step', []):
        cls = step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned')
        if cls not in ('generated', 'free') or (not blind and not component):
            names.add(step['output'])
    for residue in ('.reticuli/attest', kernel.SIGN_DIR):
        folder = os.path.join(source, residue)
        if not component and os.path.isdir(folder):
            for name in os.listdir(folder):
                if os.path.isfile(os.path.join(folder, name)):
                    names.add(residue + '/' + name)
    for name in names:
        path = core._safe(source, name)
        if os.path.isfile(path):
            core._hash_file(path)
            yield prefix + name, path

def export(directory, path, *, blind=False):
    if not kernel.verify(directory)['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    items = dict(_files(directory, blind=blind))
    for child in registry._closure(directory).values():
        name = kernel.read_manifest(child)['name']
        items.update(dict(_files(child, '.reticuli/deps/' + name + '/', component=True)))
    with tarfile.open(path, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, source in sorted(items.items()):
            with open(source, 'rb') as stream:
                data = stream.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    return path

def import_(path, into):
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('import destination is not empty')
    os.makedirs(into, exist_ok=True)
    with tarfile.open(path, 'r') as archive:
        for member in archive:
            if not member.isfile() or member.name.startswith('/') or '..' in member.name.split('/'):
                raise kernel.ClaimError('unsafe archive member')
            target = core._safe(into, member.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.extractfile(member) as source, open(target, 'wb') as destination:
                destination.write(source.read())
    verified = kernel.verify(into)
    return {'ok': verified['ok'], 'root': verified['root'], 'path': into}
