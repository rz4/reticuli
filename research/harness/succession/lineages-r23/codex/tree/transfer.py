"""Deterministic transfer of declared claim bytes and compact claim closure."""
import io
import os
import tarfile

from . import kernel, registry


def export(directory, archive, *, blind=False):
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    files = {}
    for name in registry._claim_files(directory, generated=not blind):
        files[name] = os.path.join(directory, name)
    files[kernel.MANIFEST] = os.path.join(directory, kernel.MANIFEST)
    adir = os.path.join(directory, '.reticuli', 'attest')
    if os.path.isdir(adir):
        for name in os.listdir(adir):
            path = os.path.join(adir, name)
            if os.path.isfile(path):
                files['.reticuli/attest/' + name] = path
    closure = registry._closure(directory)
    for root, path in closure.items():
        label = kernel.read_manifest(path)['name']
        for name in registry._claim_files(path, generated=False):
            files[f'.reticuli/deps/{label}/{name}'] = os.path.join(path, name)
        files[f'.reticuli/deps/{label}/{kernel.MANIFEST}'] = os.path.join(path, kernel.MANIFEST)
    with tarfile.open(archive, 'w', format=tarfile.USTAR_FORMAT) as tar:
        for name, path in sorted(files.items()):
            with open(path, 'rb') as stream:
                data = stream.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            tar.addfile(info, io.BytesIO(data))
    return {'root': verified['root'], 'archive': archive}


def import_(archive, into):
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('import target is not empty')
    os.makedirs(into, exist_ok=True)
    with tarfile.open(archive, 'r') as tar:
        for member in tar:
            if not member.isfile() or member.issym() or member.islnk():
                raise kernel.ClaimError('invalid archive member')
            name = member.name
            if name.startswith('/') or any(x in ('', '.', '..') for x in name.split('/')):
                raise kernel.ClaimError('unsafe archive path')
            path = os.path.join(into, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as out:
                out.write(tar.extractfile(member).read())
    checked = kernel.verify(into)
    if not checked['ok']:
        raise kernel.ClaimError('imported identity mismatch')
    return checked
