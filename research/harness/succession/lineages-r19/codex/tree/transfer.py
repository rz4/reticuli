"""Deterministic transport of declared claim bytes."""
import io
import os
import tarfile
from . import kernel, _util

def _files(source, *, blind=False):
    parsed = kernel.load_recipe(source)
    names = {os.path.basename('reticuli.toml' if os.path.isfile(os.path.join(source, 'reticuli.toml')) else 'claim.toml'), kernel.MANIFEST}
    names.update(_util.declared_inputs(parsed, source))
    for step in parsed.get('step', []):
        if not blind or step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned') != 'generated':
            names.add(step['output'])
    att = os.path.join(source, '.reticuli', 'attest')
    if os.path.isdir(att):
        for n in os.listdir(att):
            if os.path.isfile(os.path.join(att, n)): names.add('.reticuli/attest/' + n)
    mint = os.path.join(source, kernel.SIGN_DIR)
    if os.path.isdir(mint):
        for n in os.listdir(mint):
            if os.path.isfile(os.path.join(mint, n)): names.add(kernel.SIGN_DIR + '/' + n)
    return sorted(n for n in names if os.path.isfile(os.path.join(source, n)))

def _copy_declared(source, target, *, blind=False, dependencies=True):
    os.makedirs(target, exist_ok=True)
    for name in _files(source, blind=blind): _util.copy_into(os.path.join(source, name), os.path.join(target, name))
    if dependencies:
        from . import registry
        for path in registry._closure(source).values():
            name = kernel.read_manifest(path)['name']
            _copy_declared(path, os.path.join(target, '.reticuli', 'deps', name), blind=True, dependencies=False)

def export(source, path, *, blind=False):
    from . import registry
    members = [(name, os.path.join(source, name)) for name in _files(source, blind=blind)]
    for dep in registry._closure(source).values():
        name = kernel.read_manifest(dep)['name']
        members += [(f'.reticuli/deps/{name}/{n}', os.path.join(dep, n)) for n in _files(dep, blind=True)]
    with tarfile.open(path, 'w') as archive:
        for name, filepath in sorted(members):
            data = open(filepath, 'rb').read()
            info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o644; info.mtime = 0
            info.uid = info.gid = 0; info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(data))
    return path

def import_(path, target):
    if os.path.exists(target) and os.listdir(target): raise kernel.ClaimError('import target is not empty')
    os.makedirs(target, exist_ok=True)
    with tarfile.open(path) as archive:
        for item in archive:
            if not item.isfile(): raise kernel.ClaimError('tar member is not a file')
            dest = _util.safe_path(target, item.name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with archive.extractfile(item) as src, open(dest, 'wb') as dst:
                dst.write(src.read())
    result = kernel.verify(target)
    if not result['ok']: raise kernel.ClaimError('import identity mismatch')
    return result
