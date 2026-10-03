"""Deterministic declared-content transport for sealed claims."""
from __future__ import annotations

import io
import os
import tarfile

from . import kernel, registry
from ._kernel import core, recipe

def _files(directory, *, blind=False, dependent=False):
    parsed = kernel.load_recipe(directory)
    result = {os.path.basename(recipe.recipe_path(directory)), kernel.MANIFEST}
    result.update(recipe._inputs(parsed, directory))
    for step in recipe._steps(parsed):
        kind = step['kind']
        cls = step.get('class', 'generated' if kind == 'produce' else 'pinned')
        if cls not in ('generated', 'free') or (not blind and not dependent):
            result.add(step['output'])
    if not dependent:
        att = os.path.join(directory, '.reticuli', 'attest')
        if os.path.isdir(att):
            for base, _, names in os.walk(att):
                for name in names:
                    result.add(os.path.relpath(os.path.join(base, name), directory))
        for link in kernel.read_manifest(directory).get('components', []):
            child = registry._component(directory, link['component'])
            if not child:
                raise kernel.ClaimError('missing declared component: ' + link['component'])
            prefix = '.reticuli/deps/' + link['component'] + '/'
            result.update(prefix + name for name in _files(child, blind=True, dependent=True))
    return result

def export(directory, target, *, blind=False):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('cannot export an unverified claim')
    files = sorted(_files(directory, blind=blind))
    with tarfile.open(target, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name in files:
            if name.startswith('.reticuli/deps/'):
                bits = name.split('/')
                child = registry._component(directory, bits[2])
                source = core._safe(child, '/'.join(bits[3:]))
            else:
                source = core._safe(directory, name)
            core._hash_file(source)
            data = open(source, 'rb').read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return {'root': checked['root'], 'files': files}

def import_(source, into):
    os.makedirs(into, exist_ok=True)
    if os.listdir(into):
        raise kernel.ClaimError('import target is not empty')
    with tarfile.open(source, 'r') as archive:
        for item in archive:
            if not item.isfile():
                raise kernel.ClaimError('tar contains a non-file member')
            destination = core._safe(into, item.name)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, 'wb') as stream:
                stream.write(archive.extractfile(item).read())
    checked = kernel.verify(into)
    if not checked['ok']:
        raise kernel.ClaimError('imported claim identity mismatch')
    return checked
