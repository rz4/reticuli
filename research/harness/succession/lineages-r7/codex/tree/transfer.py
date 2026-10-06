"""Deterministic, declared-content claim archives."""
import io
import os
import shutil
import tarfile

from . import kernel, registry
from ._util import declared_inputs, safe_path


def _entries(directory, prefix='', blind=False, seen=None):
    seen = set() if seen is None else seen
    recipe = kernel.load_recipe(directory)
    names = [os.path.basename(registry._recipe_path(directory))] + declared_inputs(recipe, directory)
    names += [s['output'] for s in recipe.get('step', [])
              if not (blind and s['kind'] == 'produce' and s.get('class', 'generated') == 'generated')]
    names.append(kernel.MANIFEST)
    if not blind:
        attest_dir = os.path.join(directory, '.reticuli', 'attest')
        if os.path.isdir(attest_dir):
            for base, _, files in os.walk(attest_dir):
                names += [os.path.relpath(os.path.join(base, f), directory) for f in files]
        mint_dir = os.path.join(directory, kernel.SIGN_DIR)
        if os.path.isdir(mint_dir):
            for base, _, files in os.walk(mint_dir):
                names += [os.path.relpath(os.path.join(base, f), directory) for f in files]
    out = []
    for name in dict.fromkeys(names):
        path = safe_path(directory, name)
        if os.path.isfile(path):
            kernel._hash_file(path)
            out.append((prefix + name, path))
    manifest = kernel.read_manifest(directory)
    for name in dict.fromkeys(x['component'] for x in manifest.get('components', [])):
        if name in seen:
            continue
        component = registry._resolve(directory, name)
        if kernel.verify(component)['root'] != next(x['root'] for x in manifest['components'] if x['component'] == name):
            raise kernel.ClaimError('component root mismatch')
        out += _entries(component, prefix + '.reticuli/deps/' + name + '/', True, seen | {name})
    return out


def export(directory, destination, *, blind=False):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('cannot export a drifted claim')
    entries = _entries(directory, blind=blind)
    with tarfile.open(destination, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, path in sorted(entries):
            data = open(path, 'rb').read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(data))
    return destination


def import_(source, into):
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('import target is not empty')
    os.makedirs(into, exist_ok=True)
    try:
        with tarfile.open(source, 'r') as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    raise kernel.ClaimError('archive contains non-file member')
                target = safe_path(into, member.name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with archive.extractfile(member) as original, open(target, 'wb') as destination:
                    shutil.copyfileobj(original, destination)
    except (OSError, tarfile.TarError) as error:
        raise kernel.ClaimError(f'cannot import archive: {error}') from error
    checked = kernel.verify(into)
    if not checked['ok']:
        raise kernel.ClaimError('imported claim identity mismatch')
    return checked
