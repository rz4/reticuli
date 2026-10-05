"""Deterministic, declared-byte claim archives."""
import io
import os
import shutil
import tarfile
import tempfile

from . import kernel
from ._kernel import recipe
from ._util import declared_inputs, safe_path
from . import registry

def _members(directory, blind=False, _seen=None):
    seen = set() if _seen is None else _seen
    parsed = kernel.load_recipe(directory)
    names = [os.path.basename(recipe.recipe_path(directory)), *declared_inputs(parsed, directory)]
    for step in parsed.get('step', []):
        if blind and step['kind'] == 'produce' and step.get('class', 'generated') == 'generated':
            continue
        path = safe_path(directory, step['output'])
        if os.path.isfile(path):
            names.append(step['output'])
    names.append(kernel.MANIFEST)
    att = os.path.join(directory, '.reticuli', 'attest')
    if os.path.isdir(att):
        for root, _, files in os.walk(att):
            for file in files:
                names.append(os.path.relpath(os.path.join(root, file), directory))
    for name in sorted(set(names)):
        yield name, safe_path(directory, name)
    for link in kernel.read_manifest(directory).get('components', []):
        component = registry._component(directory, link['component'])
        prefix = '.reticuli/deps/' + link['component'] + '/'
        for name, path in _members(component, blind=True, _seen=seen):
            yield prefix + name, path

def export(directory, tar_path, *, blind=False):
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    with tarfile.open(tar_path, 'w', format=tarfile.USTAR_FORMAT) as tar:
        for name, path in sorted(_members(directory, blind=blind)):
            with open(path, 'rb') as f:
                data = f.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            tar.addfile(info, io.BytesIO(data))
    return {'root': verified['root'], 'tar': tar_path}

def import_(tar_path, into):
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('import target is not empty')
    with tarfile.open(tar_path, 'r') as tar:
        members = tar.getmembers()
        for member in members:
            if not member.isfile():
                raise kernel.ClaimError('archive contains a non-file')
            safe_path(into, member.name)
        os.makedirs(into, exist_ok=True)
        for member in members:
            path = safe_path(into, member.name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with tar.extractfile(member) as source, open(path, 'wb') as target:
                shutil.copyfileobj(source, target)
    result = kernel.verify(into)
    if not result['ok']:
        raise kernel.ClaimError('imported claim identity mismatch')
    return result
