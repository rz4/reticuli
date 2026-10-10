"""Deterministic, declared-file claim transport."""
import io
import os
import tarfile

from . import kernel, registry
from ._util import declared_inputs, safe_path
from ._kernel import recipe as kr

def _files(directory, blind=False):
    parsed = kernel.load_recipe(directory)
    names = {os.path.basename(kr.recipe_path(directory)), kernel.MANIFEST}
    names.update(declared_inputs(parsed, directory))
    for step in parsed.get('step', []):
        if not blind or step.get('class', 'generated' if step['kind']=='produce' else 'pinned') not in ('generated', 'free'):
            names.add(step['output'])
    folder = os.path.join(directory, '.reticuli', 'attest')
    if os.path.isdir(folder):
        names.update('.reticuli/attest/' + n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n)))
    for name in sorted(names):
        path = safe_path(directory, name)
        if os.path.isfile(path): yield name, path

def export(directory, destination, blind=False):
    if not kernel.verify(directory)['ok']: raise kernel.ClaimError('source identity mismatch')
    entries = list(_files(directory, blind))
    for component in registry._closure(directory):
        name = kernel.read_manifest(component)['name']
        for rel, path in _files(component, True):
            if rel.startswith('.reticuli/attest/'): continue
            entries.append((f'.reticuli/deps/{name}/{rel}', path))
    with tarfile.open(destination, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, path in sorted(entries):
            with open(path, 'rb') as stream: data = stream.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = info.uid = info.gid = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(data))
    return {'root': kernel.read_manifest(directory)['root'], 'path': destination}

def import_(archive_path, into):
    if os.path.exists(into) and os.listdir(into): raise kernel.ClaimError('import target is not empty')
    os.makedirs(into, exist_ok=True)
    with tarfile.open(archive_path, 'r:*') as archive:
        names = set()
        for entry in archive:
            name = entry.name
            if name in names or not entry.isfile(): raise kernel.ClaimError('unsafe archive entry')
            names.add(name)
            target = safe_path(into, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.extractfile(entry) as source, open(target, 'wb') as output:
                output.write(source.read())
    checked = kernel.verify(into)
    if not checked['ok']: raise kernel.ClaimError('imported identity mismatch')
    return checked
