"""Public claim kernel: identity, execution, audit, and three-machine proof."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import venv

from ._kernel import attest, build, core, crosscheck as checking, identity, recipe, run, seal as sealing

ClaimError = core.ClaimError
STORE, MANIFEST, RECIPE, LEDGER = core.STORE, core.MANIFEST, core.RECIPE, core.LEDGER
SIGN_DIR, NAMESPACE, SIGN_NAMESPACE = core.SIGN_DIR, core.NAMESPACE, core.SIGN_NAMESPACE
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
_JAILED = core._JAILED
_hash_file = core._hash_file
load_recipe = recipe.load_recipe
root = identity.root
build_digest = identity.build_digest
read_manifest = sealing.read_manifest
ledger = run.ledger
ledger_events = run.ledger_events
cost = run.cost
preflight = run.preflight
record_validate = attest.record_validate
record_read = attest.record_read
record_digest = attest.record_digest
gate_deciders = checking.gate_deciders
vacuous_gates = checking.vacuous_gates
mutation_score = checking.mutation_score
crosscheck = checking.crosscheck
independence = checking.independence


def verify(directory):
    result = sealing.verify(directory)
    result['name'] = read_manifest(directory)['name']
    return result


def seal(directory):
    try:
        return sealing.seal(directory)
    except ClaimError as exc:
        if 'symlink in claim path' not in str(exc):
            raise
        # A generated output is outside identity; sealing need not read it.
        with open(recipe.recipe_path(directory), 'rb') as stream:
            parsed = tomllib.load(stream)
        generated = set(recipe.generated_outputs(parsed))
        if not generated or not any(os.path.islink(os.path.join(directory, n)) for n in generated):
            raise
        manifest = {'name': parsed['claim']['name'], 'root': identity.root(parsed, directory)}
        core._write_json(os.path.join(directory, MANIFEST), manifest)
        return manifest


def sandbox(command, directory):
    return run._sandbox_argv(command, os.fspath(directory)), run.sandbox_backend()


def run_gate(command, directory, parsed=None):
    if run.preflight(parsed):
        return {'status': 'environment', 'quarantine': None,
                'stderr': 'missing requirements: ' + ', '.join(run.preflight(parsed))}
    backend = run.sandbox_backend()
    directory = os.path.realpath(directory)
    env = run._scrub_env(directory, backend)
    if backend in ('seatbelt', 'bubblewrap'):
        env[core._JAILED] = backend
    result = run._run(run._sandbox_argv(command, directory, backend), directory,
                      env, run.gate_timeout(parsed))
    result['quarantine'] = backend
    return result


def _room(source, target, parsed, generated=False, produce_from=None, input_from=None):
    build._materialize(source, target, parsed, generated=generated)
    for mapping in (input_from or {}, produce_from or {}):
        for name, path in mapping.items():
            core._copy_into(path, core._safe(target, name))


def _judge(source, room, parsed):
    missing = preflight(parsed)
    if missing:
        return ([{'output': step['output'], 'status': 'environment',
                  'quarantine': None, 'stderr': 'missing requirements: ' + ', '.join(missing)}
                 for step in recipe.gates(parsed)], missing)
    try:
        bin_dir = _furnish(source, parsed)
    except ClaimError as exc:
        return ([{'output': step['output'], 'status': 'environment',
                  'quarantine': None, 'stderr': str(exc)} for step in recipe.gates(parsed)], [str(exc)])
    rows = []
    for step in recipe.gates(parsed):
        name = step['output']
        command = step['run']
        if bin_dir:
            command = 'PATH=' + __import__('shlex').quote(bin_dir + ':' + os.environ.get('PATH', os.defpath)) + ' ' + command
        row = run_gate(command, room, parsed)
        if row['status'] == 'ok' and os.path.isfile(os.path.join(source, name)) and not build._compare_pin(source, room, name):
            row['status'] = 'mismatch'
        row['output'] = name
        rows.append(row)
        run.ledger(room, {'event': 'gate', 'gate': name, 'status': row['status'],
                          'quarantine': row.get('quarantine')})
    return rows, []


def _furnish(source, parsed):
    environment = parsed['claim'].get('environment')
    if not environment:
        return None
    lock = core._safe(source, environment)
    digest = core._hash_file(lock)
    target = os.path.join(run._env_cache_dir(), digest,
                          f'py{sys.version_info.major}.{sys.version_info.minor}-{sys.platform}')
    marker = os.path.join(target, '.ready')
    if not os.path.isfile(marker):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        done = subprocess.run([os.path.join(target, 'bin', 'pip'), 'install',
                               '--require-hashes', '--only-binary=:all:', '-r', lock],
                              cwd=source, capture_output=True, text=True,
                              timeout=core.FURNISH_TIMEOUT, check=False)
        if done.returncode:
            raise ClaimError('cannot furnish environment: ' + done.stderr[-1000:])
        with open(marker, 'w') as stream:
            stream.write('ready\n')
    return os.path.join(target, 'bin')


def audit(directory, *, produce_from=None, shallow=False):
    manifest = read_manifest(directory)
    parsed = load_recipe(directory)
    checked = verify(directory)
    if not checked['ok']:
        return {'ok': False, 'root': manifest['root'], 'gates': [],
                'verdict': 'identity mismatch', 'environment': []}
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        _room(directory, room, parsed, generated=True, produce_from=produce_from)
        rows, missing = _judge(directory, room, parsed)
    ok = all(row['status'] == 'ok' for row in rows)
    return {'ok': ok, 'root': manifest['root'], 'gates': rows,
            'environment': missing, 'verdict': 'earned' if ok else 'carried or broken'}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    into = os.path.abspath(into)
    original = read_manifest(directory) if os.path.isfile(os.path.join(directory, MANIFEST)) else None
    parsed = load_recipe(directory)
    if original and not verify(directory)['ok']:
        raise ClaimError('cannot rebuild changed claim')
    missing = preflight(parsed)
    if missing:
        raise ClaimError('environment missing: ' + ', '.join(missing))
    if os.path.isdir(into) and os.listdir(into):
        raise ClaimError('rebuild target contains bytes')
    if os.path.exists(into) and not os.path.isdir(into):
        raise ClaimError('rebuild target is not a directory')
    _room(directory, into, parsed, input_from=input_from, produce_from=produce_from)
    pin_names = recipe._inputs(parsed, into)
    snapshot = {name: core._hash_file(core._safe(into, name)) for name in pin_names}
    room_recipe = core._hash_file(recipe.recipe_path(into))
    run.ledger(into, {'event': 'environment', 'python': sys.version.split()[0],
                      'platform': sys.platform, 'quarantine': run.sandbox_backend()})
    vendor, model = os.environ.get(core._ENV_VENDOR), os.environ.get(core._ENV_MODEL)
    if vendor or model:
        run.ledger(into, {'event': 'producer', 'vendor': vendor, 'model': model, 'blind': True})
    outputs = recipe.generated_outputs(parsed)
    for step in recipe.produces(parsed):
        name = step['output']
        if name not in outputs:
            continue
        if produce_from and name in produce_from:
            run.ledger(into, {'event': 'reuse', 'output': name})
            continue
        env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
        env.setdefault('PATH', os.defpath)
        env.update(producer_env or {})
        env[core._ENV_OUTPUT] = core._safe(into, name)
        env[core._ENV_OUTPUTS] = json.dumps(outputs)
        env[core._ENV_USAGE] = os.path.join(into, core.USAGE)
        if guidance:
            env[core._ENV_REQUEST] = step.get('guidance', step.get('request', ''))
        else:
            env.pop(core._ENV_REQUEST, None)
        started = time.monotonic()
        outcome = run._run([core._SHELL, '-c', producer], into, env, core.PRODUCER_TIMEOUT)
        seconds = time.monotonic() - started
        if outcome['status'] != 'ok':
            raise ClaimError('producer failed: ' + outcome['stderr'])
        event = {'event': 'oracle', 'calls': 1, 'seconds': seconds,
                 'quarantine': run.sandbox_backend()}
        try:
            with open(os.path.join(into, core.USAGE), encoding='utf-8') as f:
                usage = json.load(f)
            if isinstance(usage, dict):
                event.update({key: usage[key] for key in ('calls', 'tokens', 'usd') if key in usage})
        except (OSError, ValueError):
            pass
        run.ledger(into, event)
    if core._hash_file(recipe.recipe_path(into)) != room_recipe or any(
            core._hash_file(core._safe(into, name)) != digest for name, digest in snapshot.items()):
        raise ClaimError('producer rewrote pinned claim bytes')
    rows, missing = _judge(directory, into, parsed)
    if missing or any(row['status'] != 'ok' for row in rows):
        raise ClaimError('rebuild gates did not reproduce: ' + repr(rows))
    result = seal(into)
    if original and not input_from and result['root'] != original['root']:
        raise ClaimError('rebuild root mismatch')
    return {'root': result['root'], 'name': result['name'], 'gates': rows,
            'quarantine': run.sandbox_backend(), 'build_digest': build_digest(into)}


def sign_node(root, digest, components):
    return hashlib.sha256(json.dumps([root, digest, sorted(components)], sort_keys=True).encode()).hexdigest()


def _authorized(directory, manifest):
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor) or not manifest.get('proof'):
        return False
    folder = os.path.join(directory, SIGN_DIR)
    if not os.path.isdir(folder):
        return False
    for filename in os.listdir(folder):
        if not filename.endswith('.sign.json'):
            continue
        stem = filename[:-10]
        statement = os.path.join(folder, filename)
        try:
            with open(statement, 'rb') as f: data = f.read()
            doc = json.loads(data)
            with open(os.path.join(folder, stem + '.packet.json'), 'rb') as f: packet = json.load(f)
            digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            expected = {'root': manifest['root'], 'build_digest': build_digest(directory),
                        'proof': manifest['proof']}
            if packet != expected or doc.get('packet_digest') != digest or doc.get('root') != manifest['root'] or not doc.get('proof_recorded'):
                continue
            done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor, '-I', doc['identity'],
                                   '-n', SIGN_NAMESPACE, '-s', statement + '.sig'],
                                  input=data, capture_output=True, check=False)
            if done.returncode == 0:
                return True
        except (OSError, ValueError, KeyError):
            pass
    return False


def phase(directory):
    load_recipe(directory)
    if not os.path.lexists(os.path.join(directory, MANIFEST)):
        return 'draft'
    manifest = read_manifest(directory)
    verify(directory)
    return 'signed' if _authorized(directory, manifest) else 'sealed'


def record_proof(m1, m2, m3, *, mutants=0):
    if os.path.isfile(os.fspath(m1)):
        raise ClaimError('proof must land on a directory')
    records = []
    for path in (m2, m3):
        if os.path.isfile(os.fspath(path)):
            anchor = os.environ.get(core._ENV_SIGNERS)
            if not anchor:
                raise ClaimError('record proof needs an anchor')
            doc = record_read(path)
            signer = None
            with open(anchor, encoding='utf-8') as stream:
                principals = [line.split()[0] for line in stream if line.split()]
            for principal in principals:
                try:
                    done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                                           '-I', principal, '-n', RECORD_NAMESPACE,
                                           '-s', os.fspath(path) + '.sig'],
                                          input=attest.record_canonical(doc),
                                          capture_output=True, check=False)
                    if done.returncode == 0:
                        signer = principal
                        break
                except OSError:
                    pass
            if not signer:
                raise ClaimError('record signature is not anchored')
            records.append({'digest': record_digest(record_read(path)), 'signer': signer})
    result = crosscheck(m1, m2, m3, mutants=mutants)
    result['proof_recorded'] = result['satisfied']
    if result['satisfied']:
        manifest = read_manifest(m1)
        manifest['proof'] = {'kind': 'crosscheck', 'roots': result['roots'], 'records': records}
        core._write_json(os.path.join(m1, MANIFEST), manifest)
    return result
