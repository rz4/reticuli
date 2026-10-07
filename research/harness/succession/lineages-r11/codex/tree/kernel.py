"""Public claim kernel."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import venv

from ._kernel import core, recipe, identity, seal as seal_module, run, build, attest, crosscheck as crosscheck_module

ClaimError = core.ClaimError
NAMESPACE = core.NAMESPACE
SIGN_NAMESPACE = core.SIGN_NAMESPACE
SIGN_DIR = core.SIGN_DIR
STORE = core.STORE
MANIFEST = core.MANIFEST
RECIPE = core.RECIPE
LEDGER = core.LEDGER
_JAILED = core._JAILED
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = attest.RECORD_FORMAT
_hash_file = core._hash_file
def load_recipe(directory):
    parsed = recipe.load_recipe(directory)
    claim = parsed['claim']
    envelope = claim.get('envelope')
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope or any(
                key not in core.COST_KEYS or type(value) not in (int, float)
                or not math.isfinite(value) or value <= 0
                for key, value in envelope.items()):
            raise ClaimError('invalid envelope')
    for key in ('tolerance', 'mutation_floor'):
        if key in claim and (type(claim[key]) not in (int, float)
                             or not math.isfinite(claim[key]) or claim[key] < 0):
            raise ClaimError('invalid ' + key)
    return parsed
read_manifest = seal_module.read_manifest
root = identity.root
build_digest = identity.build_digest
def seal(directory):
    # A generated path is not an identity component. Permit sealing its
    # current alias; subsequent materialization still refuses that alias.
    original = core._safe
    def lexical(base, name):
        if not isinstance(name, str) or not name or os.path.isabs(name) or any(
                part in ('', '.', '..') for part in name.split('/')):
            raise ClaimError(f'unsafe claim path: {name!r}')
        return os.path.join(os.path.realpath(base), *name.split('/'))
    try:
        core._safe = lexical
        parsed = recipe.load_recipe(directory)
    finally:
        core._safe = original
    manifest = {'name': parsed['claim']['name'], 'root': identity.root(parsed, directory)}
    core._write_json(os.path.join(directory, MANIFEST), manifest)
    return manifest
ledger = run.ledger
ledger_events = run.ledger_events
cost = run.cost
preflight = run.preflight
record_validate = attest.record_validate
record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_signer = attest.record_signer


def record_read(path):
    doc = attest.record_read(path)
    with open(path, 'rb') as f:
        raw = f.read()
    if raw != attest.record_canonical(doc):
        raise ClaimError('record is not canonical')
    return doc


def verify(directory):
    result = seal_module.verify(directory)
    result['name'] = read_manifest(directory)['name']
    return result


def sandbox(command=None, directory=None):
    backend = run.sandbox_backend()
    if command is None:
        return {'backend': backend}
    return run._sandbox_argv(command, directory or '.', backend), backend


def _furnish(directory, parsed):
    name = parsed['claim'].get('environment')
    if not name:
        return None
    digest = _hash_file(core._safe(directory, name))
    destination = os.path.join(run._env_cache_dir(), digest + '-' + sys.implementation.cache_tag)
    if not os.path.isfile(os.path.join(destination, 'pyvenv.cfg')):
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(destination)
        pip = os.path.join(destination, 'bin', 'pip')
        subprocess.run([pip, 'install', '--require-hashes', '--only-binary=:all:',
                        '-r', core._safe(directory, name)], cwd=directory, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=core.FURNISH_TIMEOUT)
    return destination


def run_gate(command, directory, claim=None):
    parsed = claim or load_recipe(directory)
    missing = preflight(parsed)
    if missing:
        return {'status': 'environment', 'quarantine': None, 'missing': missing,
                'stdout': '', 'stderr': ''}
    backend = run.sandbox_backend()
    env = run._scrub_env(directory, backend)
    if backend in ('seatbelt', 'bubblewrap'):
        env[_JAILED] = backend
    elif os.environ.get(_JAILED):
        env[_JAILED] = os.environ[_JAILED]
    venv_dir = None
    try:
        venv_dir = _furnish(directory, parsed)
    except (OSError, subprocess.SubprocessError, ClaimError) as exc:
        return {'status': 'environment', 'quarantine': None, 'stdout': '', 'stderr': str(exc)}
    if venv_dir:
        env['PATH'] = os.path.join(venv_dir, 'bin') + os.pathsep + env.get('PATH', os.defpath)
    declared = parsed['claim'].get('gate_timeout', core.GATE_TIMEOUT)
    try:
        host = float(os.environ.get(core._ENV_TIMEOUT, core.GATE_TIMEOUT))
    except ValueError:
        host = core.GATE_TIMEOUT
    timeout = min(float(declared), host)
    result = run._run(run._sandbox_argv(command, directory, backend), directory, env, timeout)
    result['quarantine'] = backend
    return result


def _judge(source, room, parsed):
    rows = []
    missing = preflight(parsed)
    for step in recipe.gates(parsed):
        name = step['output']
        if missing:
            row = {'output': name, 'status': 'environment', 'quarantine': None, 'missing': missing}
        else:
            outcome = run_gate(step['run'], room, parsed)
            status = outcome['status']
            if status == 'ok':
                try:
                    status = 'ok' if (not os.path.exists(os.path.join(source, MANIFEST)) or _hash_file(core._safe(source, name)) == _hash_file(core._safe(room, name))) else 'mismatch'
                except ClaimError:
                    status = 'mismatch'
            row = {'output': name, 'status': status, 'quarantine': outcome['quarantine'],
                   'stderr': outcome.get('stderr', '')}
        rows.append(row)
        ledger(room, {'event': 'gate', 'output': name, 'status': row['status'],
                      'quarantine': row['quarantine']})
    return rows


def _materialize(source, room, parsed, *, generated=False, produce_from=None, input_from=None):
    build._materialize(source, room, parsed, generated=generated)
    for mapping in (input_from or {}, produce_from or {}):
        for name, path in mapping.items():
            core._copy_into(path, core._safe(room, name))


def audit(directory, *, produce_from=None, shallow=False):
    checked = verify(directory)
    if not checked['ok']:
        return {'ok': False, 'root': checked['root'], 'gates': [], 'verdict': 'identity mismatch'}
    parsed = load_recipe(directory)
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        _materialize(directory, room, parsed, generated=True, produce_from=produce_from)
        rows = _judge(directory, room, parsed)
    missing = preflight(parsed)
    ok = all(row['status'] == 'ok' for row in rows)
    return {'ok': ok, 'root': checked['root'], 'gates': rows, 'environment': missing,
            'verdict': 'earned' if ok else 'carried or broken'}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    parsed = load_recipe(directory)
    if os.path.exists(os.path.join(directory, MANIFEST)) and not verify(directory)['ok']:
        raise ClaimError('source claim identity does not verify')
    if preflight(parsed):
        raise ClaimError('environment missing: ' + repr(preflight(parsed)))
    into = os.path.abspath(into)
    if os.path.exists(into) and os.listdir(into):
        raise ClaimError('rebuild target contains bytes')
    os.makedirs(into, exist_ok=True)
    os.makedirs(os.path.join(into, STORE), exist_ok=True)
    _materialize(directory, into, parsed, input_from=input_from)
    for step in recipe.produces(parsed):
        if 'from' in step:
            name = step['output']
            if produce_from and name in produce_from:
                core._copy_into(produce_from[name], core._safe(into, name))
                ledger(into, {'event': 'reuse', 'output': name})
    snapshot = {name: _hash_file(core._safe(into, name)) for name in recipe._inputs(parsed, into)}
    rname = os.path.basename(recipe.recipe_path(into))
    snapshot[rname] = _hash_file(core._safe(into, rname))
    outputs = recipe.generated_outputs(parsed)
    elapsed = 0.0
    calls = 0
    for step in recipe.produces(parsed):
        name = step['output']
        if name not in outputs:
            continue
        if produce_from and name in produce_from:
            core._copy_into(produce_from[name], core._safe(into, name))
            ledger(into, {'event': 'reuse', 'output': name})
            continue
        env = run._scrub_env(into, 'none')
        env.update(producer_env or {})
        env[core._ENV_CLAIM] = into
        env[core._ENV_OUTPUT] = core._safe(into, name)
        env[core._ENV_OUTPUTS] = json.dumps(outputs)
        env[core._ENV_USAGE] = os.path.join(into, core.USAGE)
        if guidance:
            env[core._ENV_REQUEST] = step.get('guidance', step.get('request', ''))
        else:
            env.pop(core._ENV_REQUEST, None)
        result = run._run([core._SHELL, '-c', producer], into, env, core.PRODUCER_TIMEOUT)
        elapsed += result['seconds']
        calls += 1
        if result['status'] != 'ok':
            raise ClaimError('producer failed: ' + result['stderr'])
    for name, digest in snapshot.items():
        if _hash_file(core._safe(into, name)) != digest:
            raise ClaimError('producer changed pinned bytes: ' + name)
    rows = _judge(directory, into, parsed)
    if any(row['status'] != 'ok' for row in rows):
        raise ClaimError('rebuilt gates did not reproduce: ' + repr(rows))
    sealed = seal(into)
    usage = build._read_usage(into)
    ledger(into, {'event': 'producer', 'when': core._now(), 'seconds': elapsed,
                  'calls': calls, **usage})
    ledger(into, {'event': 'environment', 'python': sys.version.split()[0],
                  'platform': sys.platform, 'quarantine': run.sandbox_backend()})
    if os.environ.get(core._ENV_VENDOR) or os.environ.get(core._ENV_MODEL):
        ledger(into, {'event': 'producer_identity', 'vendor': os.environ.get(core._ENV_VENDOR),
                      'model': os.environ.get(core._ENV_MODEL), 'blind': True})
    return {'root': sealed['root'], 'gates': rows, 'build_digest': build_digest(into),
            'quarantine': 'inherited' if os.environ.get(_JAILED) else 'none'}


def crosscheck(m1, m2, m3, *, mutants=None):
    return crosscheck_module.crosscheck(m1, m2, m3, mutants=mutants)


def sign_node(root_value, digest, links):
    payload = {'root': root_value, 'build_digest': digest, 'links': sorted(links)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _signed(directory):
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor:
        return False
    manifest = read_manifest(directory)
    proof = manifest.get('proof')
    if not proof:
        return False
    sign_dir = os.path.join(directory, SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return False
    for filename in os.listdir(sign_dir):
        if not filename.endswith('.sign.json'):
            continue
        statement_path = os.path.join(sign_dir, filename)
        packet_path = os.path.join(sign_dir, filename[:-10] + '.packet.json')
        try:
            with open(statement_path, 'rb') as f: statement_bytes = f.read()
            statement = json.loads(statement_bytes)
            with open(packet_path, 'rb') as f: packet = json.load(f)
            pdig = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            if statement['packet_digest'] != pdig or not statement.get('proof_recorded'):
                continue
            if packet != {'root': manifest['root'], 'build_digest': build_digest(directory), 'proof': proof}:
                continue
            if build._ssh_verify(statement_path + '.sig', statement_bytes, anchor,
                                 statement['identity'], SIGN_NAMESPACE):
                return True
        except (OSError, ValueError, KeyError):
            continue
    return False


def phase(directory):
    recipe.recipe_path(directory)
    if not os.path.exists(os.path.join(directory, MANIFEST)):
        return 'draft'
    verify(directory)
    return 'signed' if _signed(directory) else 'sealed'


def independence(directory):
    for event in reversed(ledger_events(directory)):
        if event.get('event') == 'producer_identity':
            return {k: event.get(k) for k in ('vendor', 'model', 'blind')}
    return {}


def gate_deciders(command):
    words = shlex.split(command.replace('&&', ' && ').replace(';', ' ; '))
    deciders = []
    for index, word in enumerate(words):
        if word.startswith('./'):
            deciders.append(word[2:])
        if word in _INTERPRETER_NAMES and index + 1 < len(words):
            rest = words[index + 1:]
            if rest[0] == '-m' and len(rest) > 1 and rest[1] in ('pytest', 'py.test'):
                candidates = [w for w in rest[2:] if not w.startswith('-') and w not in ('&&', ';')]
                deciders.extend(candidates[:1])
            elif not rest[0].startswith('-'):
                deciders.append(rest[0])
    return list(dict.fromkeys(deciders))

_INTERPRETER_NAMES = crosscheck_module._INTERPRETERS


def vacuous_gates(parsed):
    generated = set(recipe.generated_outputs(parsed))
    pinned = set(parsed['claim'].get('inputs', []))
    result = []
    for gate in recipe.gates(parsed):
        deciders = gate_deciders(gate['run'])
        if deciders and all(d in generated and d not in pinned for d in deciders):
            result.append(gate['output'])
    return result


def mutation_score(directory, *, max_mutants=20):
    parsed = load_recipe(directory)
    candidates = []
    for name in recipe.generated_outputs(parsed):
        path = core._safe(directory, name)
        if not path.endswith('.py') or not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8') as f: source = f.read()
        candidates.extend((name, changed) for changed in crosscheck_module._mutants(source))
    seed = verify(directory)['root']
    candidates = crosscheck_module._mutant_order(candidates, seed)[:max_mutants]
    killed = 0
    survivors = []
    for number, (name, changed) in enumerate(candidates):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as room:
            build._materialize(directory, room, parsed, generated=True)
            with open(core._safe(room, name), 'w', encoding='utf-8') as f: f.write(changed)
            rows = _judge(directory, room, parsed)
            if all(row['status'] == 'ok' for row in rows):
                survivors.append(number)
            else:
                killed += 1
    result = {'mutants': len(candidates), 'killed': killed, 'survivors': survivors,
              'rate': killed / len(candidates) if candidates else 0.0}
    core._write_json(os.path.join(directory, core.MUTATION_RESIDUE), result)
    return result


def record_proof(m1, m2, m3):
    if not os.path.isdir(m1):
        raise ClaimError('proof needs a directory M1')
    trail = []
    for p in (m2, m3):
        if os.path.isfile(p):
            anchor = os.environ.get(core._ENV_SIGNERS)
            signer = record_signer(p, anchor) if anchor else None
            if not signer:
                raise ClaimError('record has no anchored signer')
            trail.append({'digest': record_digest(record_read(p)), 'signer': signer})
    outcome = crosscheck(m1, m2, m3)
    if outcome['satisfied']:
        manifest = read_manifest(m1)
        manifest['proof'] = {'kind': 'crosscheck', 'roots': outcome['roots'], 'records': trail}
        core._write_json(os.path.join(m1, MANIFEST), manifest)
    return {'proof_recorded': outcome['satisfied'], 'crosscheck': outcome}
