"""Deterministic declared-content claim archives."""
from __future__ import annotations

import io
import os
import tarfile
from . import kernel
from ._kernel import recipe
from ._util import copy_into

def _declared(directory, *, generated=True, residue=True):
    parsed = kernel.load_recipe(directory)
    names = [os.path.basename(recipe.recipe_path(directory)), kernel.MANIFEST]
    names += recipe._inputs(parsed, directory)
    for step in parsed.get('step', []):
        classification = step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned')
        if generated or classification not in ('generated', 'free'):
            names.append(step['output'])
    if residue:
        attest_dir = os.path.join(directory, '.reticuli', 'attest')
        if os.path.isdir(attest_dir):
            for base, dirs, files in os.walk(attest_dir):
                dirs.sort()
                for filename in sorted(files):
                    names.append(os.path.relpath(os.path.join(base, filename), directory))
        sign_dir = os.path.join(directory, kernel.SIGN_DIR)
        if os.path.isdir(sign_dir):
            for filename in sorted(os.listdir(sign_dir)):
                names.append(os.path.join(kernel.SIGN_DIR, filename))
    return sorted({n for n in names if os.path.isfile(kernel._safe(directory, n))})

def _copy_claim(source, target, *, generated=True, residue=True):
    os.makedirs(target, exist_ok=True)
    for name in _declared(source, generated=generated, residue=residue):
        copy_into(kernel._safe(source, name), kernel._safe(target, name))

def _members(directory, blind=False):
    names = set(_declared(directory, generated=not blind))
    manifest = kernel.read_manifest(directory)
    for link in manifest.get('components', []):
        from . import registry
        component = registry._resolve(directory, link)
        prefix = '.reticuli/deps/' + link['component'] + '/'
        for name in _declared(component, generated=False, residue=False):
            names.add(prefix + name)
    return sorted(names)

def export(directory, path, *, blind=False):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    with tarfile.open(path, 'w', format=tarfile.USTAR_FORMAT) as tar:
        for name in _members(directory, blind):
            if name.startswith('.reticuli/deps/'):
                _, _, component, relative = name.split('/', 3)
                from . import registry
                link = next(x for x in kernel.read_manifest(directory).get('components', [])
                            if x['component'] == component)
                source = kernel._safe(registry._resolve(directory, link), relative)
            else:
                source = kernel._safe(directory, name)
            data = open(source, 'rb').read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            tar.addfile(info, io.BytesIO(data))
    return {'path': path, 'root': checked['root']}

def import_(path, into):
    if os.path.exists(into) and (not os.path.isdir(into) or os.listdir(into)):
        raise kernel.ClaimError('import target is not empty')
    os.makedirs(into, exist_ok=True)
    with tarfile.open(path, 'r') as tar:
        for member in tar:
            if not member.isfile() or member.name.startswith('/'):
                raise kernel.ClaimError('unsafe archive member')
            dest = kernel._safe(into, member.name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with tar.extractfile(member) as src, open(dest, 'wb') as out:
                out.write(src.read())
    checked = kernel.verify(into)
    if not checked['ok']:
        raise kernel.ClaimError('import identity mismatch')
    return checked
