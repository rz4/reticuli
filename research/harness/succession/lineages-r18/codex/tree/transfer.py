"""Deterministic, declared-content claim archives."""
import io
import os
import tarfile

from . import kernel, registry
from ._util import declared_inputs, safe_path


def _files(path, prefix='', blind=False, depth=0):
    if depth > 20:
        raise kernel.ClaimError('component nesting too deep')
    doc = kernel.load_recipe(path)
    recipe = 'reticuli.toml' if os.path.isfile(os.path.join(path, 'reticuli.toml')) else 'claim.toml'
    names = {recipe, *declared_inputs(path), kernel.MANIFEST}
    for step in doc.get('step', []):
        if not blind or step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned') != 'generated':
            names.add(step['output'])
    attest_dir = os.path.join(path, '.reticuli', 'attest')
    if os.path.isdir(attest_dir) and not depth:
        for name in os.listdir(attest_dir):
            names.add('.reticuli/attest/' + name)
    mint_dir = os.path.join(path, kernel.SIGN_DIR)
    if os.path.isdir(mint_dir) and not depth:
        for name in os.listdir(mint_dir):
            names.add(kernel.SIGN_DIR + '/' + name)
    for name in sorted(names):
        source = safe_path(path, name)
        if os.path.isfile(source):
            yield prefix + name, source
    for name in sorted({x['component'] for x in kernel.read_manifest(path).get('components', [])}):
        component = registry._find(path, name)
        yield from _files(component, prefix + '.reticuli/deps/' + name + '/', True, depth + 1)


def export(path, tar_path, *, blind=False):
    if not kernel.verify(path)['ok']:
        raise kernel.ClaimError('source claim identity mismatch')
    with tarfile.open(tar_path, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, source in sorted(_files(path, blind=blind)):
            with open(source, 'rb') as stream:
                data = stream.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(data))
    return tar_path


def import_(tar_path, into):
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('import target is not empty')
    os.makedirs(into, exist_ok=True)
    with tarfile.open(tar_path, 'r:*') as archive:
        for member in archive:
            if not member.isfile():
                raise kernel.ClaimError('archive contains a non-file')
            target = safe_path(into, member.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.extractfile(member) as source, open(target, 'wb') as output:
                output.write(source.read())
    return kernel.verify(into)
