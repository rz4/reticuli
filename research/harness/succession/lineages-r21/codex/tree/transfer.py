"""Deterministic transfer of declared claim bytes and component criteria."""
import io
import os
import tarfile

from . import kernel, registry
from ._util import safe_path

def export(directory, archive, *, blind=False):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity does not match seal')
    names = registry._files(directory, generated=not blind)
    names.append(kernel.MANIFEST)
    attest_dir = os.path.join(directory, '.reticuli', 'attest')
    if os.path.isdir(attest_dir):
        for base, _, files in os.walk(attest_dir):
            for filename in files:
                names.append(os.path.relpath(os.path.join(base, filename), directory))
    content = {name: os.path.join(directory, name) for name in names}
    for source in registry._closure(directory).values():
        cname = kernel.read_manifest(source)['name']
        for name in registry._files(source, generated=False) + [kernel.MANIFEST]:
            content[f'.reticuli/deps/{cname}/{name}'] = os.path.join(source, name)
    with tarfile.open(archive, 'w', format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(content):
            path = content[name]
            if not os.path.isfile(path):
                continue
            with open(path, 'rb') as stream:
                data = stream.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            tar.addfile(info, io.BytesIO(data))
    return {'root': checked['root'], 'archive': archive}

def import_(archive, into):
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('import destination is not empty')
    os.makedirs(into, exist_ok=True)
    with tarfile.open(archive, 'r:*') as tar:
        for member in tar:
            if not member.isfile():
                raise kernel.ClaimError('transfer contains non-file member')
            target = safe_path(into, member.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with tar.extractfile(member) as source, open(target, 'wb') as output:
                output.write(source.read())
    checked = kernel.verify(into)
    if not checked['ok']:
        raise kernel.ClaimError('imported claim identity does not match seal')
    return checked
