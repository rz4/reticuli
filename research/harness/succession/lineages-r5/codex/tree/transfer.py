"""Portable, deterministic claim archives with declared content only."""
import io
import os
import shutil
import tarfile

from . import kernel
from ._util import copy_into, declared_inputs


def _declared(directory, prefix='', blind=False):
    parsed = kernel.load_recipe(directory)
    recipe_name = 'reticuli.toml' if os.path.isfile(os.path.join(directory, 'reticuli.toml')) else 'claim.toml'
    names = [recipe_name, *declared_inputs(parsed, directory), kernel.MANIFEST]
    for step in parsed.get('step', []):
        cls = step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned')
        if not blind or cls != 'generated':
            names.append(step['output'])
    attest_dir = os.path.join(directory, '.reticuli', 'attest')
    if os.path.isdir(attest_dir):
        names.extend(os.path.join('.reticuli', 'attest', n) for n in os.listdir(attest_dir))
    sign_dir = os.path.join(directory, kernel.SIGN_DIR)
    if os.path.isdir(sign_dir):
        names.extend(os.path.join(kernel.SIGN_DIR, n) for n in os.listdir(sign_dir))
    result = {}
    for name in names:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            result[prefix + name] = path
    manifest = kernel.read_manifest(directory)
    for component in sorted({x['component'] for x in manifest.get('components', [])}):
        candidate = None
        for base in ('sealed', 'deps'):
            path = os.path.join(directory, '.reticuli', base, component)
            if os.path.isdir(path):
                candidate = path
                break
        if candidate is None:
            raise kernel.ClaimError('missing component for export: ' + component)
        result.update(_declared(candidate, prefix + '.reticuli/deps/' + component + '/', True))
    return result


def export(directory, archive, blind=False):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    files = _declared(directory, blind=blind)
    with tarfile.open(archive, 'w', format=tarfile.USTAR_FORMAT) as tar:
        for name, path in sorted(files.items()):
            data = open(path, 'rb').read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            tar.addfile(info, io.BytesIO(data))
    return {'root': checked['root'], 'files': sorted(files)}


def import_(archive, into):
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('import target is not empty')
    os.makedirs(into, exist_ok=True)
    with tarfile.open(archive, 'r') as tar:
        for member in tar:
            if not member.isfile() or member.name.startswith('/') or any(p in ('', '.', '..') for p in member.name.split('/')):
                raise kernel.ClaimError('unsafe archive member')
            path = os.path.join(into, member.name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with tar.extractfile(member) as source, open(path, 'wb') as output:
                shutil.copyfileobj(source, output)
    checked = kernel.verify(into)
    if not checked['ok']:
        raise kernel.ClaimError('imported claim identity mismatch')
    return checked
