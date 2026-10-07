"""Public content-addressed claim kernel."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

from ._kernel import attest, core, crosscheck as comparison, identity, recipe, run, seal as sealing

ClaimError = core.ClaimError
RECIPE = core.RECIPE
STORE = core.STORE
MANIFEST = core.MANIFEST
LEDGER = core.LEDGER
NAMESPACE = core.NAMESPACE
SIGN_DIR = core.SIGN_DIR
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = attest.RECORD_FORMAT
_JAILED = core._JAILED
_hash_file = core._hash_file
root = identity.root
build_digest = identity.build_digest
read_manifest = sealing.read_manifest
record_validate = attest.record_validate
record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_signer = attest.record_signer
preflight = run.preflight
ledger = run.ledger
ledger_events = run.ledger_events
mutation_score = comparison.mutation_score


def load_recipe(directory):
    try:
        document = recipe.load_recipe(directory)
    except ClaimError as exc:
        if 'symlink in claim path' not in str(exc):
            raise
        # A generated output may be present as an unsafe alias at seal time;
        # audit is responsible for refusing to copy that alias into a room.
        try:
            with open(recipe.recipe_path(directory), 'rb') as stream:
                document = tomllib.load(stream)
            for step in recipe._steps(document):
                if step.get('class', 'generated' if step.get('kind') == 'produce' else 'pinned') in ('generated', 'free'):
                    continue
                core._safe(directory, step['output'])
            for name in recipe._inputs(document, directory):
                core._safe(directory, name)
        except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as failure:
            raise ClaimError(f'cannot read recipe: {failure}') from failure
    envelope = document.get('claim', {}).get('envelope')
    if envelope is not None:
        if (not isinstance(envelope, dict) or not envelope or
            any(k not in core.COST_KEYS or type(v) not in (int, float) or v <= 0
                for k, v in envelope.items())):
            raise ClaimError('invalid claim envelope')
    return document


def seal(directory):
    document = load_recipe(directory)
    manifest = {'name': document['claim']['name'], 'root': identity.root(document, directory)}
    core._write_json(core._safe(directory, MANIFEST), manifest)
    return manifest


def verify(directory):
    manifest = read_manifest(directory)
    document = load_recipe(directory)
    computed = identity.root(document, directory)
    return {'ok': manifest['root'] == computed and manifest['name'] == document['claim']['name'],
            'name': manifest['name'], 'root': manifest['root'], 'recomputed': computed}


def record_read(path):
    document = attest.record_read(path)
    raw = Path(path).read_bytes()
    if raw != attest.record_canonical(document):
        raise ClaimError('record bytes are not canonical')
    return document


def sign_node(root_value, digest, links):
    data = {'root': root_value, 'build_digest': digest, 'links': sorted(links)}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def sandbox(command=None, directory=None):
    return command, run.sandbox_backend()


def run_gate(command, directory, claim_recipe=None, env=None):
    # A gate receives only explicitly selected host variables. In particular,
    # caller-defined RETICULI_* values are not a general credential channel.
    backend = run.sandbox_backend()
    environment = {key: value for key, value in os.environ.items()
                   if key in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'TZ', _JAILED)}
    environment.setdefault('PATH', os.defpath)
    if backend in ('seatbelt', 'bubblewrap'):
        scratch = os.path.join(os.path.abspath(directory), STORE, 'tmp')
        os.makedirs(scratch, exist_ok=True)
        environment.update({'HOME': scratch, 'TMPDIR': scratch, _JAILED: backend})
    if env:
        environment.update({str(k): str(v) for k, v in env.items()})
    result = run._run(run._sandbox_argv(command, directory, backend), directory,
                      environment, run.gate_timeout(claim_recipe))
    result['quarantine'] = backend
    return result


def cost(directory):
    totals = {}
    for event in ledger_events(directory):
        if event.get('event') not in ('oracle', 'producer', 'production') and event.get('kind') not in ('producer', 'production'):
            continue
        for unit in core.COST_KEYS:
            value = event.get(unit)
            if type(value) in (int, float) and value >= 0:
                totals[unit] = totals.get(unit, 0) + value
    return totals or None


def _copy(source, destination):
    core._hash_file(source)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copyfile(source, destination)


def _materialize(source, destination, *, generated=False, produce_from=None, input_from=None):
    claim = load_recipe(source)
    os.makedirs(destination, exist_ok=True)
    source_name = recipe.recipe_path(source)
    _copy(source_name, core._safe(destination, os.path.basename(source_name)))
    inputs = recipe._inputs(claim, source)
    if claim['claim'].get('environment'):
        inputs.append(claim['claim']['environment'])
    for step in recipe.produces(claim):
        if step.get('class', 'generated') not in ('generated', 'free') or generated:
            inputs.append(step['output'])
    for name in dict.fromkeys(inputs):
        selected = (input_from or {}).get(name, core._safe(source, name))
        _copy(selected, core._safe(destination, name))
    for name, selected in (produce_from or {}).items():
        if name not in recipe.generated_outputs(claim):
            raise ClaimError(f'undeclared generated output: {name}')
        _copy(selected, core._safe(destination, name))
    if claim['claim'].get('format', 1) >= 3:
        preimage = identity._preimage_recipe(claim)
        # The judging room sees the recipe that its root names.
        with open(core._safe(destination, os.path.basename(source_name)), 'w', encoding='utf-8') as stream:
            stream.write(_toml_recipe(preimage))
    return claim


def _toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return '[' + ', '.join(map(_toml_value, value)) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(f'{k} = {_toml_value(v)}' for k, v in value.items()) + ' }'
    return str(value)


def _toml_recipe(document):
    lines = ['[claim]']
    lines.extend(f'{k} = {_toml_value(v)}' for k, v in document['claim'].items())
    for step in document.get('step', []):
        lines.extend(['', '[[step]]'])
        lines.extend(f'{k} = {_toml_value(v)}' for k, v in step.items())
    return '\n'.join(lines) + '\n'


def _judge(source, room, claim):
    missing = preflight(claim)
    if missing:
        furnished = {'status': 'environment'}
    else:
        previous = os.getcwd()
        try:
            os.chdir(room)
            furnished = run.furnish(room, claim)
        finally:
            os.chdir(previous)
    gates = []
    for step in recipe.gates(claim):
        name = step['output']
        if missing or furnished['status'] != 'ok':
            gates.append({'output': name, 'status': 'environment', 'quarantine': None,
                          'detail': missing or furnished.get('detail')})
            continue
        env = None
        if furnished.get('path'):
            env = {'PATH': os.path.join(furnished['path'], 'bin') + os.pathsep + os.environ.get('PATH', os.defpath)}
        outcome = run_gate(step['run'], room, claim, env)
        status = outcome['status']
        if status == 'ok':
            try:
                expected = core._safe(source, name)
                actual = core._safe(room, name)
                if os.path.exists(expected):
                    status = 'ok' if core._hash_file(expected) == core._hash_file(actual) else 'mismatch'
                else:
                    core._hash_file(actual)
            except ClaimError:
                status = 'mismatch'
        gates.append({'output': name, 'status': status, 'quarantine': outcome['quarantine'],
                      'seconds': outcome['seconds'], 'stderr': outcome['stderr']})
        ledger(room, {'event': 'gate', 'output': name, 'status': status,
                      'quarantine': outcome['quarantine']})
    return gates, missing


def audit(directory, *, deep=True, produce_from=None):
    checked = verify(directory)
    if not checked['ok']:
        return {'ok': False, 'verdict': 'identity mismatch', 'gates': [], 'root': checked['root']}
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        claim = _materialize(directory, room, generated=True, produce_from=produce_from)
        gates, missing = _judge(directory, room, claim)
    ok = all(g['status'] == 'ok' for g in gates)
    result = {'ok': ok, 'verdict': 'earned' if ok else 'carried or broken',
              'gates': gates, 'root': checked['root']}
    if missing:
        result['environment'] = missing
    return result


def _usage(room):
    try:
        document = json.loads(Path(core._safe(room, core.USAGE)).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(document, dict):
        return {}
    return {unit: document[unit] for unit in ('usd', 'tokens', 'calls')
            if type(document.get(unit)) in (int, float) and document[unit] >= 0}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    source = os.path.abspath(directory)
    target = os.path.abspath(into)
    if os.path.isdir(target) and os.listdir(target):
        raise ClaimError(f'rebuild destination is not empty: {into}')
    try:
        checked = verify(source)
    except ClaimError as exc:
        # Some callers provide an unsealed source to exercise gate failure.
        if 'manifest' not in str(exc):
            raise
        checked = None
    if checked is not None and not checked['ok']:
        raise ClaimError('source identity mismatch')
    claim = _materialize(source, target, produce_from=produce_from, input_from=input_from)
    if preflight(claim):
        raise ClaimError(f'environment missing requirements: {preflight(claim)}')
    snapshot = {name: _hash_file(core._safe(target, name)) for name in
                dict.fromkeys(recipe._inputs(claim, target) +
                                   ([claim['claim']['environment']] if claim['claim'].get('environment') else []))}
    recipe_name = os.path.basename(recipe.recipe_path(target))
    recipe_bytes = Path(core._safe(target, recipe_name)).read_bytes()
    outputs = [name for name in recipe.generated_outputs(claim) if name not in (produce_from or {})]
    env = {key: value for key, value in os.environ.items()
           if key in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'TZ', _JAILED)}
    env.setdefault('PATH', os.defpath)
    env['RETICULI_OUTPUTS'] = json.dumps(outputs)
    if len(outputs) == 1:
        env['RETICULI_OUTPUT'] = outputs[0]
    os.makedirs(core._safe(target, STORE), exist_ok=True)
    env['RETICULI_USAGE'] = core._safe(target, core.USAGE)
    if guidance:
        hints = [str(step.get('guidance', step.get('request', ''))) for step in recipe.produces(claim)
                 if step['output'] in outputs]
        if any(hints):
            env['RETICULI_REQUEST'] = '\n'.join(hints)
    if producer_env:
        env.update({str(k): str(v) for k, v in producer_env.items()})
    for name in produce_from or {}:
        ledger(target, {'event': 'reuse', 'output': name})
    env['RETICULI_VENDOR'] = os.environ.get('RETICULI_VENDOR', '')
    env['RETICULI_MODEL'] = os.environ.get('RETICULI_MODEL', '')
    started = time.monotonic()
    produced = run._run([core._SHELL, '-c', producer], target, env, core.PRODUCER_TIMEOUT)
    elapsed = time.monotonic() - started
    ledger(target, {'event': 'producer', 'kind': 'producer', 'calls': 1,
                    'seconds': elapsed, 'status': produced['status'],
                    'vendor': env['RETICULI_VENDOR'], 'model': env['RETICULI_MODEL'],
                    'blind': True, **_usage(target)})
    if produced['status'] != 'ok':
        raise ClaimError(f'producer {produced["status"]}: {produced["stderr"]}')
    if Path(core._safe(target, recipe_name)).read_bytes() != recipe_bytes:
        raise ClaimError('producer changed recipe')
    for name, before in snapshot.items():
        if _hash_file(core._safe(target, name)) != before:
            raise ClaimError(f'producer changed pinned input: {name}')
    gates, missing = _judge(source, target, claim)
    if any(g['status'] != 'ok' for g in gates):
        raise ClaimError(f'rebuild gates failed: {gates}')
    manifest = seal(target)
    if checked and not input_from and manifest['root'] != checked['root']:
        raise ClaimError('rebuilt identity differs from source')
    backend = gates[0]['quarantine'] if gates else run.sandbox_backend()
    ledger(target, {'event': 'environment', 'python': sys.version,
                    'platform': sys.platform, 'quarantine': backend})
    return {'ok': True, 'root': manifest['root'], 'gates': gates,
            'build_digest': build_digest(target), 'quarantine': backend}


def gate_deciders(command):
    found = []
    for segment in re.split(r'&&|\|\||[;|]', command):
        words = segment.split()
        for index, word in enumerate(words):
            if word.startswith('./'):
                found.append(word[2:])
            elif word in ('pytest', 'py.test'):
                found.extend(w for w in words[index + 1:] if not w.startswith('-') and w != 'OK')
                break
            elif word in ('python', 'python3', 'python2') and index + 1 < len(words):
                following = words[index + 1:]
                if len(following) >= 3 and following[0] == '-m' and following[1] in ('pytest', 'unittest'):
                    found.extend(w for w in following[2:] if not w.startswith('-') and w != 'OK')
                    break
                if following[0].endswith('.py'):
                    found.append(following[0])
    return list(dict.fromkeys(found))


def vacuous_gates(claim):
    generated = set(recipe.generated_outputs(claim))
    pinned = set(claim.get('claim', {}).get('inputs', []))
    empty = []
    for gate in recipe.gates(claim):
        deciders = gate_deciders(gate['run'])
        if deciders and all(name in generated and name not in pinned for name in deciders):
            empty.append(gate['output'])
    return empty


def independence(directory):
    for event in reversed(ledger_events(directory)):
        if event.get('event') == 'producer':
            return {'vendor': event.get('vendor') or None,
                    'model': event.get('model') or None,
                    'blind': event.get('blind', False)}
    return {'vendor': None, 'model': None, 'blind': False}


def _leg(path):
    if os.path.isdir(path):
        checked = verify(path)
        earned = audit(path) if checked['ok'] else {'ok': False}
        return {'root': checked['root'], 'digest': build_digest(path),
                'audited': earned['ok'], 'cost': cost(path),
                'claim': load_recipe(path)['claim'], 'producer': independence(path),
                'record': False}
    document = record_read(path)
    return {'root': document['root'], 'digest': document['build_digest'],
            'audited': all(g['status'] == 'ok' for g in document['gates']),
            'cost': document.get('cost'), 'claim': document.get('claim'),
            'producer': document.get('producer'), 'record': True}


def crosscheck(m1, m2, m3, *, mutants=None, tolerance=None):
    paths = [os.path.realpath(os.fspath(p)) for p in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise ClaimError('crosscheck requires three distinct paths')
    legs = [_leg(path) for path in paths]
    roots = {f'M{i}': leg['root'] for i, leg in enumerate(legs, 1)}
    audited = {f'M{i}': leg['audited'] for i, leg in enumerate(legs, 1)}
    equivalent = len(set(roots.values())) == 1
    reuse = legs[0]['digest'] == legs[1]['digest']
    declared = legs[0]['claim']
    rejected, incomplete = [], []
    if not equivalent:
        rejected.append('roots')
    if not reuse:
        rejected.append('reuse')
    if not all(audited.values()):
        rejected.append('audit')
    if declared is None:
        incomplete.append('declared conditions')
        declared = {}
    first_cost, third_cost = legs[0]['cost'] or {}, legs[2]['cost'] or {}
    shared = next((unit for unit in core.COST_LADDER
                   if unit in first_cost and unit in third_cost), None)
    band = None
    if shared:
        a, b = first_cost[shared], third_cost[shared]
        limit = tolerance or declared.get('tolerance', core.TOLERANCE)
        band = (a == b == 0) if a == 0 or b == 0 else a / limit <= b <= a * limit
        if declared.get('tolerance') is not None and not band:
            rejected.append('cost tolerance')
    envelope = {}
    for unit, ceiling in declared.get('envelope', {}).items():
        measured = third_cost.get(unit)
        within = None if measured is None else measured <= ceiling
        envelope[unit] = {'ceiling': ceiling, 'measured': measured, 'within': within}
        if within is False:
            rejected.append(f'envelope {unit}')
        elif within is None:
            incomplete.append(f'envelope {unit}')
    mutation = None
    if 'mutation_floor' in declared:
        if mutants is None:
            incomplete.append('mutation floor')
        elif legs[2]['record']:
            incomplete.append('mutation floor')
        else:
            mutation = mutation_score(m3, max_mutants=mutants)
            mutation['ok'] = mutation['rate'] >= declared['mutation_floor']
            if not mutation['ok']:
                rejected.append('mutation floor')
    producer = legs[2]['producer'] or {}
    if producer.get('vendor'):
        independent = (f"declared: {producer['vendor']}/{producer.get('model') or 'unknown'}, "
                       f"{'blind workspace' if producer.get('blind') else 'unblinded workspace'}; not proven")
    else:
        independent = 'unestablished: producer independence not proven'
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied': verdict == 'accept', 'verdict': verdict,
            'rejected': rejected, 'incomplete': incomplete,
            'roots': roots, 'equivalence': equivalent, 'reuse': reuse,
            'audited': audited, 'cost': {'comparable': band, 'unit': shared,
                                       'M1': legs[0]['cost'], 'M3': legs[2]['cost'],
                                       'envelope': envelope},
            'mutation_score': mutation, 'independence': independent}


def record_proof(m1, m2, m3, **kwargs):
    if not os.path.isdir(m1):
        raise ClaimError('a proof requires a claim directory for M1')
    trail = []
    for path in (m2, m3):
        if os.path.isdir(path):
            continue
        anchor = os.environ.get('RETICULI_SIGNERS')
        signer = record_signer(path, anchor) if anchor else None
        if not signer:
            raise ClaimError('record signature is not anchored')
        trail.append({'digest': record_digest(record_read(path)), 'signer': signer})
    result = crosscheck(m1, m2, m3, **kwargs)
    if result['satisfied']:
        manifest = read_manifest(m1)
        manifest['proof'] = {'kind': 'crosscheck', 'roots': result['roots'],
                             'records': trail}
        core._write_json(core._safe(m1, MANIFEST), manifest)
    result['proof_recorded'] = result['satisfied']
    return result


def phase(directory):
    manifest_path = core._safe(directory, MANIFEST)
    if not os.path.exists(manifest_path):
        load_recipe(directory)
        return 'draft'
    checked = verify(directory)
    if not checked['ok']:
        return 'draft'
    manifest = read_manifest(directory)
    if not manifest.get('proof'):
        return 'sealed'
    anchor = os.environ.get('RETICULI_SIGNERS')
    if not anchor:
        return 'sealed'
    directory_path = core._safe(directory, SIGN_DIR)
    if not os.path.isdir(directory_path):
        return 'sealed'
    for filename in sorted(os.listdir(directory_path)):
        if not filename.endswith('.sign.json'):
            continue
        statement_path = os.path.join(directory_path, filename)
        packet_path = statement_path[:-10] + '.packet.json'
        signature_path = statement_path + '.sig'
        try:
            statement = json.loads(Path(statement_path).read_text())
            packet = json.loads(Path(packet_path).read_text())
            digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            if (digest != statement.get('packet_digest') or
                packet.get('root') != checked['root'] or
                packet.get('build_digest') != build_digest(directory) or
                packet.get('proof') != manifest['proof'] or
                not statement.get('proof_recorded')):
                continue
            completed = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                                        '-I', statement['identity'], '-n', SIGN_NAMESPACE,
                                        '-s', signature_path],
                                       input=Path(statement_path).read_bytes(),
                                       capture_output=True, timeout=10)
            if completed.returncode == 0:
                return 'signed'
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            continue
    return 'sealed'
