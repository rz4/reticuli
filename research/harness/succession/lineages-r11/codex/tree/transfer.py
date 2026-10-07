"""Deterministic, declared-content claim transport."""
import io
import os
import tarfile

from . import kernel, registry
from ._kernel import core, recipe

def _files(directory, *, blind=False, seen=None):
    seen = set() if seen is None else seen
    parsed = kernel.load_recipe(directory)
    names = {os.path.basename(recipe.recipe_path(directory)), kernel.MANIFEST}
    names.update(recipe._inputs(parsed, directory))
    for step in parsed.get('step', []):
        classification = step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned')
        if not blind or classification not in ('generated', 'free'):
            names.add(step['output'])
    attdir = os.path.join(directory, '.reticuli', 'attest')
    if os.path.isdir(attdir):
        for name in os.listdir(attdir):
            if os.path.isfile(os.path.join(attdir, name)):
                names.add('.reticuli/attest/' + name)
    for name in sorted(names):
        path = core._safe(directory, name)
        if os.path.isfile(path):
            yield name, path
    for link in kernel.read_manifest(directory).get('components', []):
        name = link['component']
        if name in seen:
            continue
        seen.add(name)
        source = registry._component_path(directory, name)
        prefix = '.reticuli/deps/' + name + '/'
        for child, path in _files(source, blind=True, seen=seen):
            yield prefix + child, path

def export(directory, target, *, blind=False):
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('cannot export a drifted claim')
    with tarfile.open(target, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, path in sorted(_files(directory, blind=blind)):
            data = open(path, 'rb').read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(data))
    return {'root': verified['root'], 'path': target}

def import_(source, into):
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('import destination is not empty')
    os.makedirs(into, exist_ok=True)
    with tarfile.open(source, 'r') as archive:
        for member in archive:
            if not member.isfile():
                raise kernel.ClaimError('transport contains non-file')
            path = core._safe(into, member.name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with archive.extractfile(member) as stream, open(path, 'wb') as output:
                output.write(stream.read())
    result = kernel.verify(into)
    if not result['ok']:
        raise kernel.ClaimError('imported claim identity mismatch')
    return result
