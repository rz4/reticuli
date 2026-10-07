"""Host-specific cache of earned verdicts and auditable layer reuse."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import kernel


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _key(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _cache():
    return Path(os.environ.get('RETICULI_CACHE',
                              str(Path.home() / '.cache' / 'reticuli' / 'verdicts')))


def _path(fingerprint):
    return _cache() / (_key(fingerprint) + '.json')


def fingerprint(directory):
    """Identify the exact claim, build, interpreter, and host being judged."""
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    return {'root': verified['root'], 'build': kernel.build_digest(directory),
            'platform': platform.platform(), 'python': sys.version}


def _read(fingerprint):
    try:
        row = json.loads(_path(fingerprint).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if (isinstance(row, dict) and row.get('fingerprint') == fingerprint
            and isinstance(row.get('verdict'), dict)
            and row['verdict'].get('ok') is True):
        return row
    return None


def lookup(directory):
    """Return a passing verdict only for an identical current fingerprint."""
    row = _read(fingerprint(directory))
    return row['verdict'] if row else None


def remember(directory, verdict):
    """Store an earned pass; failures cannot become reusable evidence."""
    if not isinstance(verdict, dict) or verdict.get('ok') is not True:
        return None
    fp = fingerprint(directory)
    row = {'fingerprint': fp, 'verdict': verdict,
           'earned_at': datetime.now(timezone.utc).isoformat(),
           'source': os.path.realpath(directory)}
    target = _path(fp)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent,
                                     delete=False) as stream:
        json.dump(row, stream, sort_keys=True)
        stream.write('\n')
        temporary = stream.name
    os.replace(temporary, target)
    return row


def _layer_fingerprint(layer, inherited):
    files = layer['files']
    check_name, check_path = layer['check']
    sources = dict(files)
    sources[check_name] = check_path
    digests = {}
    for name, source in sources.items():
        digests[name] = kernel._hash_file(source)
    return {'kind': 'layer', 'name': layer['name'], 'files': digests,
            'gate': layer['gate'], 'verdict': layer.get('verdict'),
            'dependencies': inherited, 'platform': platform.platform(),
            'python': sys.version}


def layered_audit(layers):
    """Earn each layer's gate once, recording every later use as reuse."""
    rows = []
    inherited = []
    for layer in layers:
        fp = _layer_fingerprint(layer, inherited)
        key = _key(fp)
        cached = _read(fp)
        if cached is not None:
            row = {'name': layer['name'], 'ok': True, 'status': 'reused',
                   'reused': cached['earned_at'],
                   'source': cached.get('source') or key,
                   'key': key}
        else:
            with tempfile.TemporaryDirectory(prefix='reticuli-layer-audit-') as room:
                sources = dict(layer['files'])
                name, path = layer['check']
                sources[name] = path
                for relative, source in sources.items():
                    destination = Path(room) / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                try:
                    result = subprocess.run(layer['gate'], shell=True, cwd=room,
                                            capture_output=True, text=True, timeout=120)
                    ok = result.returncode == 0
                    detail = result.stderr
                except (OSError, subprocess.TimeoutExpired) as exc:
                    ok, detail = False, str(exc)
            row = {'name': layer['name'], 'ok': ok,
                   'status': 'earned' if ok else 'broken', 'key': key}
            if not ok:
                row['detail'] = detail
            else:
                target = _path(fp)
                target.parent.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).isoformat()
                record = {'fingerprint': fp, 'verdict': {'ok': True},
                          'earned_at': stamp, 'source': layer['name']}
                with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent,
                                                 delete=False) as stream:
                    json.dump(record, stream, sort_keys=True)
                    stream.write('\n')
                    temporary = stream.name
                os.replace(temporary, target)
        rows.append(row)
        inherited.append(key)
        if not row['ok']:
            break
    return {'ok': len(rows) == len(layers) and all(row['ok'] for row in rows),
            'layers': rows}
