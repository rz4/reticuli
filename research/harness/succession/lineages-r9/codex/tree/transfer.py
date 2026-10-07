"""Deterministic, declared-content claim transfer."""
import io
import os
import tarfile
from . import kernel
from ._kernel import recipe as kr
from .registry import _component, _links
from ._util import copy_into, declared_inputs


def _files(source, *, blind=False, dependency=False, prefix='', seen=None):
    seen = set() if seen is None else seen
    parsed = kernel.load_recipe(source)
    names = [os.path.basename(kr.recipe_path(source)), *declared_inputs(parsed, source)]
    for step in parsed.get('step', []):
        kind = step['kind']
        cls = step.get('class', 'generated' if kind == 'produce' else 'pinned')
        if cls != 'generated' or (not blind and not dependency):
            name = step['output']
            if os.path.isfile(os.path.join(source, name)):
                names.append(name)
    names.append(kernel.MANIFEST)
    if not dependency:
        attest_dir = os.path.join(source, '.reticuli', 'attest')
        if os.path.isdir(attest_dir):
            for base, _, files in os.walk(attest_dir):
                for file in files:
                    names.append(os.path.relpath(os.path.join(base, file), source))
    for name in dict.fromkeys(names):
        path = os.path.join(source, name)
        if os.path.isfile(path):
            yield prefix + name, path
    for name in sorted({x['component'] for x in _links(source)}):
        if name in seen:
            continue
        seen.add(name)
        child = _component(source, name)
        yield from _files(child, dependency=True, prefix=prefix+'.reticuli/deps/'+name+'/', seen=seen)


def export(directory, archive, *, blind=False):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    members = sorted(_files(directory, blind=blind))
    with tarfile.open(archive, 'w', format=tarfile.USTAR_FORMAT) as tar:
        for name, path in members:
            with open(path, 'rb') as f:
                data = f.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
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
            name = member.name
            if not member.isfile() or name.startswith('/') or '..' in name.split('/') or not name:
                raise kernel.ClaimError('unsafe transfer member')
            target = os.path.join(into, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with tar.extractfile(member) as src, open(target, 'wb') as dst:
                dst.write(src.read())
    checked = kernel.verify(into)
    if not checked['ok']:
        raise kernel.ClaimError('imported claim identity mismatch')
    return checked
