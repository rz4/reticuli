"""Public kernel API for content-addressed claims."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import venv

from ._kernel import attest, core, crosscheck as comparison, identity, recipe, run, seal as sealing

ClaimError = core.ClaimError
NAMESPACE = core.NAMESPACE
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = 2
RECIPE = core.RECIPE
STORE = core.STORE
MANIFEST = core.MANIFEST
LEDGER = core.LEDGER
SIGN_DIR = core.SIGN_DIR
_JAILED = core._JAILED
_hash_file = core._hash_file
root = identity.root
build_digest = identity.build_digest
load_recipe = recipe.load_recipe
read_manifest = sealing.read_manifest
seal = sealing.seal
verify = sealing.verify
ledger = run.ledger
ledger_events = run.ledger_events
cost = run.cost
preflight = run.preflight
gate_deciders = comparison.gate_deciders
vacuous_gates = comparison.vacuous_gates
mutation_score = comparison.mutation_score
crosscheck = comparison.crosscheck


def sandbox(command='true', directory='.'):
    backend = run.sandbox_backend()
    return run._sandbox_argv(command, directory, backend), backend


def _gate(command, directory, parsed=None, furnished=None):
    missing = preflight(parsed or {})
    if missing:
        return {'status': 'environment', 'quarantine': None, 'missing': missing,
                'stdout': '', 'stderr': ''}
    backend = run.sandbox_backend()
    env = run._scrub_env(directory, backend)
    if backend in ('seatbelt', 'bubblewrap'):
        env[_JAILED] = backend
    if furnished:
        env['PATH'] = os.path.join(furnished, 'bin') + os.pathsep + env['PATH']
    try:
        result = run._run(run._sandbox_argv(command, directory, backend),
                          directory, env, run.gate_timeout(parsed))
    except OSError as exc:
        return {'status': 'environment', 'quarantine': backend,
                'error': str(exc), 'stdout': '', 'stderr': ''}
    result['quarantine'] = backend
    return result


run_gate = _gate


def _copy_named(source, destination, name, replacement=None):
    src = os.fspath(replacement) if replacement is not None else core._safe(source, name)
    core._hash_file(src)
    target = core._safe(destination, name)
    core._copy_into(src, target)


def _room(source, destination, parsed, *, generated=True, produce_from=None,
          input_from=None):
    os.makedirs(destination, exist_ok=True)
    original = recipe.recipe_path(source)
    target = core._safe(destination, os.path.basename(original))
    if parsed['claim'].get('format', 1) < 3:
        core._copy_into(original, target)
    else:
        with open(target, 'w', encoding='utf-8') as f:
            # A TOML representation of the acceptance-bearing recipe. Keep
            # the original syntax to preserve every non-guidance field.
            for line in open(original, encoding='utf-8'):
                if not line.lstrip().startswith(('guidance =', 'request =')):
                    f.write(line)
    for name in recipe._inputs(parsed, source):
        _copy_named(source, destination, name, (input_from or {}).get(name))
    for step in recipe.produces(parsed):
        name = step['output']
        if name in (produce_from or {}):
            _copy_named(source, destination, name, produce_from[name])
        elif step.get('class', 'generated') != 'generated' or 'from' in step or generated:
            path = core._safe(source, name)
            if os.path.exists(path):
                _copy_named(source, destination, name)
            elif step.get('class', 'generated') != 'generated' or 'from' in step:
                raise ClaimError(f'missing declared output: {name}')
    return destination


def _judge(source, room, parsed, furnished=None):
    rows = []
    for step in recipe.gates(parsed):
        name = step['output']
        outcome = _gate(step['run'], room, parsed, furnished)
        row = {'output': name, 'status': outcome['status'],
               'quarantine': outcome['quarantine']}
        if outcome['status'] == 'ok':
            try:
                expected = core._hash_file(core._safe(source, name))
                actual = core._hash_file(core._safe(room, name))
                row['status'] = 'ok' if expected == actual else 'mismatch'
            except ClaimError:
                # An unsealed source can be rebuilt and its gate output earned.
                if os.path.exists(core._safe(source, name)):
                    row['status'] = 'mismatch'
        for key in ('stdout', 'stderr', 'returncode', 'missing', 'error'):
            if key in outcome:
                row[key] = outcome[key]
        rows.append(row)
        if os.path.isdir(room) and os.path.exists(core._safe(room, core.MANIFEST)):
            pass
    return rows


def audit(directory, *, produce_from=None, shallow=False):
    checked = verify(directory)
    parsed = load_recipe(directory)
    if not checked['ok']:
        return {'ok': False, 'name': checked['name'], 'root': checked['root'],
                'gates': [], 'verdict': 'identity mismatch',
                'quarantine': run.sandbox_backend()}
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as tmp:
        _room(directory, tmp, parsed, produce_from=produce_from)
        try:
            furnished = run.furnish(tmp, parsed)
        except ClaimError as exc:
            rows = [{'output': s['output'], 'status': 'environment',
                     'quarantine': None, 'error': str(exc)} for s in recipe.gates(parsed)]
            return {'ok': False, 'root': checked['root'], 'gates': rows,
                    'environment': [str(exc)], 'verdict': 'environment',
                    'quarantine': run.sandbox_backend()}
        rows = _judge(directory, tmp, parsed, furnished)
    missing = [x for row in rows for x in row.get('missing', [])]
    return {'ok': all(r['status'] == 'ok' for r in rows),
            'root': checked['root'], 'name': checked['name'], 'gates': rows,
            'environment': missing, 'quarantine': run.sandbox_backend(),
            'verdict': 'earned' if all(r['status'] == 'ok' for r in rows) else 'carried or broken'}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    parsed = load_recipe(directory)
    try:
        old = verify(directory)
        if not old['ok']:
            raise ClaimError('source claim identity mismatch')
    except ClaimError as exc:
        if 'cannot read manifest' not in str(exc):
            raise
        old = None
    if preflight(parsed):
        raise ClaimError('environment missing: ' + ', '.join(preflight(parsed)))
    destination = os.path.realpath(into)
    if os.path.exists(destination) and os.listdir(destination):
        raise ClaimError('rebuild destination is not empty')
    _room(directory, destination, parsed, generated=False,
          produce_from=produce_from, input_from=input_from)
    pinned = {name: core._hash_file(core._safe(destination, name))
              for name in [os.path.basename(recipe.recipe_path(directory)),
                           *recipe._inputs(parsed, directory)]}
    run.ledger(destination, {'event': 'environment', 'python': sys.version.split()[0],
                             'platform': platform.platform(), 'quarantine': run.sandbox_backend()})
    for step in recipe.produces(parsed):
        name = step['output']
        if name in (produce_from or {}):
            run.ledger(destination, {'event': 'reuse', 'output': name})
            continue
        if step.get('class', 'generated') != 'generated' or 'from' in step:
            continue
        target = core._safe(destination, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        env = run._scrub_env(destination, 'none')
        env.update({core._ENV_OUTPUT: target,
                    core._ENV_OUTPUTS: json.dumps(recipe.generated_outputs(parsed)),
                    core._ENV_CLAIM: destination,
                    core._ENV_USAGE: core._safe(destination, core.USAGE)})
        if guidance:
            env[core._ENV_REQUEST] = step.get('guidance', step.get('request', ''))
        if producer_env:
            env.update(producer_env)
        result = run._run([core._SHELL, '-c', producer], destination,
                          env, core.PRODUCER_TIMEOUT)
        event = {'event': 'oracle', 'seconds': result['seconds'], 'calls': 1,
                 'quarantine': 'none', 'status': result['status'],
                 'vendor': os.environ.get(core._ENV_VENDOR),
                 'model': os.environ.get(core._ENV_MODEL), 'blind': True}
        usage_path = core._safe(destination, core.USAGE)
        try:
            with open(usage_path, encoding='utf-8') as f:
                usage = json.load(f)
            if isinstance(usage, dict):
                event.update({k: v for k, v in usage.items()
                              if k in ('usd', 'tokens', 'calls') and type(v) in (int, float)
                              and v >= 0 and math.isfinite(v)})
        except (OSError, ValueError):
            pass
        run.ledger(destination, event)
        if result['status'] != 'ok':
            raise ClaimError('producer failed: ' + result.get('stderr', ''))
    for name, digest in pinned.items():
        if core._hash_file(core._safe(destination, name)) != digest:
            raise ClaimError('producer changed pinned bytes: ' + name)
    try:
        furnished = run.furnish(destination, parsed)
    except ClaimError as exc:
        raise ClaimError('environment: ' + str(exc)) from exc
    rows = _judge(directory, destination, parsed, furnished)
    for row in rows:
        run.ledger(destination, {'event': 'gate', 'gate': row['output'],
                                 'status': row['status'], 'quarantine': row['quarantine']})
    if any(r['status'] != 'ok' for r in rows):
        raise ClaimError('rebuild gates did not reproduce: ' + repr(rows))
    manifest = seal(destination)
    if old and manifest['root'] != old['root'] and not input_from:
        raise ClaimError('rebuild root differs from source')
    return {'name': manifest['name'], 'root': manifest['root'],
            'build_digest': build_digest(destination), 'gates': rows,
            'quarantine': run.sandbox_backend()}


def independence(directory):
    for event in ledger_events(directory):
        if event.get('event') == 'oracle' and event.get('vendor'):
            return {k: event.get(k) for k in ('vendor', 'model', 'blind')}
    return None


def sign_node(root_value, digest, links):
    payload = {'root': root_value, 'build_digest': digest, 'links': sorted(links)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def record_validate(doc):
    if isinstance(doc, dict) and doc.get('record') == 2:
        base = {k: v for k, v in doc.items() if k != 'claim'}
        base['record'] = 1
        attest.record_validate(base)
    else:
        attest.record_validate(doc)
    if doc['record'] == 2:
        if 'claim' not in doc or not isinstance(doc['claim'], dict):
            raise ClaimError('record version 2 needs claim obligations')
        allowed = {'tolerance', 'mutation_floor', 'envelope'}
        if doc['claim'].keys() - allowed:
            raise ClaimError('unknown claim obligation')
        for key in ('tolerance', 'mutation_floor'):
            if key in doc['claim'] and (type(doc['claim'][key]) not in (int, float)
                                         or not math.isfinite(doc['claim'][key])
                                         or doc['claim'][key] < 0):
                raise ClaimError('invalid claim obligation: ' + key)
        if 'envelope' in doc['claim']:
            _validate_envelope(doc['claim']['envelope'])
    elif 'claim' in doc:
        raise ClaimError('version 1 record cannot carry claim obligations')


def record_canonical(doc):
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode('utf-8')


def record_digest(doc):
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path):
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        doc = json.loads(raw)
        if raw != record_canonical(doc):
            raise ClaimError('record is not canonical bytes')
        return doc
    except (OSError, UnicodeError, ValueError) as exc:
        raise ClaimError('cannot read record: ' + str(exc)) from exc


def record_signer(path, anchor):
    data = record_canonical(record_read(path))
    signature = os.fspath(path) + '.sig'
    try:
        found = subprocess.run(['ssh-keygen', '-Y', 'find-principals', '-f', os.fspath(anchor),
                                '-s', signature], capture_output=True, text=True, check=False)
        if found.returncode:
            return None
        for principal in found.stdout.splitlines():
            principal = principal.strip()
            if not principal:
                continue
            verified = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', os.fspath(anchor),
                                       '-I', principal, '-n', RECORD_NAMESPACE, '-s', signature],
                                      input=data, capture_output=True, check=False)
            if verified.returncode == 0:
                return principal
    except OSError:
        pass
    return None


def _validate_envelope(value):
    if not isinstance(value, dict) or not value or value.keys() - set(core.COST_KEYS):
        raise ClaimError('invalid envelope')
    for amount in value.values():
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
            raise ClaimError('invalid envelope ceiling')


_original_load_recipe = recipe.load_recipe


def _checked_recipe(directory):
    original_safe = core._safe
    def parse_path(base, name):
        if not isinstance(name, str) or not name or os.path.isabs(name) or '..' in name.replace('\\', '/').split('/'):
            raise ClaimError(f'unsafe claim path: {name!r}')
        return os.path.join(os.path.realpath(base), name)
    # Parsing a generated output's declaration does not read its bytes. Its
    # symlink is rejected at the later copy boundary used by audit.
    core._safe = parse_path
    try:
        parsed = _original_load_recipe(directory)
    finally:
        core._safe = original_safe
    for name in recipe._inputs(parsed, directory):
        original_safe(directory, name)
    for step in parsed.get('step', []):
        if step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned') != 'generated':
            original_safe(directory, step['output'])
    if 'envelope' in parsed['claim']:
        _validate_envelope(parsed['claim']['envelope'])
    return parsed


recipe.load_recipe = _checked_recipe
load_recipe = _checked_recipe


def _furnish(directory, parsed):
    name = parsed.get('claim', {}).get('environment')
    if not name:
        return None
    lock = core._safe(directory, name)
    digest = core._hash_file(lock)
    key = hashlib.sha256((digest + sys.executable + platform.platform()).encode()).hexdigest()
    target = os.path.join(run._env_cache_dir(), key)
    python = os.path.join(target, 'bin', 'python')
    if os.path.isfile(python):
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        venv.EnvBuilder(with_pip=True).create(target)
        done = subprocess.run([python, '-m', 'pip', 'install', '--require-hashes',
                               '--only-binary=:all:', '-r', lock], cwd=directory,
                              capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
        if done.returncode:
            raise ClaimError('cannot furnish environment: ' + done.stderr[-500:])
    except (OSError, subprocess.TimeoutExpired, ClaimError) as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise ClaimError('cannot furnish environment: ' + str(exc)) from exc
    return target


run.furnish = _furnish


def record_proof(m1, m2, m3):
    if not os.path.isdir(m1):
        raise ClaimError('proof requires a directory for M1')
    records = []
    for path in (m2, m3):
        if os.path.isfile(path):
            anchor = os.environ.get(core._ENV_SIGNERS)
            if not anchor:
                raise ClaimError('record requires a trust anchor')
            signer = record_signer(path, anchor)
            if not signer:
                raise ClaimError('record has no trusted signer')
            records.append({'digest': record_digest(record_read(path)), 'signer': signer})
    result = crosscheck(m1, m2, m3)
    if result['satisfied']:
        manifest = read_manifest(m1)
        manifest['proof'] = {'kind': 'crosscheck', 'roots': result['roots'],
                             'records': records}
        core._write_json(core._safe(m1, MANIFEST), manifest)
        result['proof_recorded'] = True
    else:
        result['proof_recorded'] = False
    return result


def phase(directory):
    parsed = load_recipe(directory)
    if not os.path.exists(core._safe(directory, MANIFEST)):
        return 'draft'
    try:
        checked = verify(directory)
    except ClaimError as exc:
        raise
    if not checked['ok']:
        raise ClaimError('claim identity mismatch')
    manifest = read_manifest(directory)
    if not manifest.get('proof'):
        return 'sealed'
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor:
        return 'sealed'
    sign_dir = core._safe(directory, SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return 'sealed'
    for filename in os.listdir(sign_dir):
        if not filename.endswith('.sign.json'):
            continue
        stem = filename[:-len('.sign.json')]
        statement_path = os.path.join(sign_dir, filename)
        packet_path = os.path.join(sign_dir, stem + '.packet.json')
        try:
            with open(statement_path, 'rb') as f:
                statement_bytes = f.read()
            with open(statement_path, encoding='utf-8') as f:
                statement = json.load(f)
            with open(packet_path, encoding='utf-8') as f:
                packet = json.load(f)
            want = {'root': checked['root'], 'build_digest': build_digest(directory),
                    'proof': manifest['proof']}
            if packet != want or statement.get('root') != checked['root']:
                continue
            if statement.get('packet_digest') != hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest():
                continue
            if not statement.get('proof_recorded'):
                continue
            verified = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                                       '-I', statement['identity'], '-n', SIGN_NAMESPACE,
                                       '-s', statement_path + '.sig'], input=statement_bytes,
                                      capture_output=True, check=False)
            if verified.returncode == 0:
                return 'signed'
        except (OSError, ValueError, KeyError):
            pass
    return 'sealed'
