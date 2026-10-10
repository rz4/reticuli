"""Public kernel for content addressed claims."""
from __future__ import annotations
import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import venv
import zipfile

from ._kernel import core, recipe, identity, seal as sealing, run, build, attest, crosscheck as mutation

ClaimError = core.ClaimError
RECIPE = core.RECIPE
STORE = core.STORE
MANIFEST = core.MANIFEST
LEDGER = core.LEDGER
SIGN_DIR = core.SIGN_DIR
NAMESPACE = core.NAMESPACE
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = attest.RECORD_FORMAT
_JAILED = core._JAILED
_hash_file = core._hash_file
root = identity.root
build_digest = identity.build_digest
def load_recipe(directory):
    parsed = recipe.load_recipe(directory)
    envelope = parsed.get('claim', {}).get('envelope')
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError('envelope must be a nonempty table')
        for unit, ceiling in envelope.items():
            if (unit not in core.COST_KEYS or isinstance(ceiling, bool)
                    or not isinstance(ceiling, (int, float)) or ceiling <= 0):
                raise ClaimError('invalid envelope ceiling')
    return parsed

read_manifest = sealing.read_manifest
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
        import tomllib
        with open(recipe.recipe_path(directory), 'rb') as stream:
            parsed = tomllib.load(stream)
        for step in recipe._steps(parsed):
            if step.get('kind') == 'produce' and step.get('class', 'generated') in ('generated', 'free'):
                continue
            core._safe(directory, step.get('output'))
        manifest = {'name': parsed['claim']['name'], 'root': identity.root(parsed, directory)}
        core._write_json(os.path.join(directory, MANIFEST), manifest)
        return manifest

cost = run.cost
ledger = run.ledger
ledger_events = run.ledger_events
preflight = run.preflight
record_validate = attest.record_validate
record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_signer = attest.record_signer


def record_read(path):
    doc = attest.record_read(path)
    with open(path, 'rb') as stream:
        if stream.read() != attest.record_canonical(doc):
            raise ClaimError('record is not canonical bytes')
    return doc


def sandbox(command=None, directory=None):
    backend = run.sandbox_backend()
    return (run._sandbox_argv(command or 'true', directory or '.', backend), backend)


def run_gate(command, directory, parsed=None, *, env_path=None):
    backend = run.sandbox_backend()
    extra = {}
    if env_path:
        extra['PATH'] = os.path.join(env_path, 'bin') + os.pathsep + os.environ.get('PATH', os.defpath)
    env = run._scrub_env(directory, backend, extra)
    if backend in ('seatbelt', 'bubblewrap'):
        env[_JAILED] = backend
    start = time.monotonic()
    try:
        result = run._run(run._sandbox_argv(command, directory, backend), directory,
                          run.gate_timeout(parsed), env)
    except OSError as exc:
        return {'status': 'environment', 'quarantine': backend, 'stdout': '',
                'stderr': str(exc), 'seconds': time.monotonic() - start}
    status = 'timeout' if result.get('timeout') else ('ok' if result['returncode'] == 0 else 'failed')
    return {'status': status, 'quarantine': backend, 'returncode': result['returncode'],
            'stdout': result['stdout'], 'stderr': result['stderr'],
            'seconds': time.monotonic() - start}


def _furnish(room, parsed):
    lock = parsed.get('claim', {}).get('environment')
    if not lock:
        return None
    path = core._safe(room, lock)
    key = core._hash_file(path) + '-' + str(sys.version_info[:2]).replace(' ', '')
    target = os.path.join(run._env_cache_dir(), key)
    python = os.path.join(target, 'bin', 'python')
    if not os.path.isfile(python):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        try:
            done = subprocess.run([python, '-m', 'pip', 'install', '--require-hashes',
                                   '--only-binary=:all:', '-r', path], cwd=room,
                                  capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ClaimError(f'environment cannot be furnished: {exc}') from exc
        if done.returncode:
            raise ClaimError(f'environment cannot be furnished: {done.stderr[-500:]}')
    return target


def _gate_rows(source, room, parsed):
    missing = preflight(parsed)
    try:
        env_path = None if missing else _furnish(room, parsed)
    except ClaimError as exc:
        missing = [str(exc)]
        env_path = None
    rows = []
    for step in recipe.gates(parsed):
        name = step['output']
        if missing:
            result = {'status': 'environment', 'quarantine': None, 'stderr': '; '.join(missing)}
        else:
            result = run_gate(step['run'], room, parsed, env_path=env_path)
            if result['status'] == 'ok' and os.path.isfile(os.path.join(source, MANIFEST)):
                try:
                    if core._hash_file(core._safe(source, name)) != core._hash_file(core._safe(room, name)):
                        result['status'] = 'mismatch'
                except ClaimError:
                    result['status'] = 'mismatch'
        result['output'] = name
        rows.append(result)
    return rows, missing


def audit(directory, *, produce_from=None, shallow=False):
    checked = verify(directory)
    if not checked['ok']:
        return {'ok': False, 'root': checked['root'], 'gates': [], 'verdict': 'broken'}
    parsed = load_recipe(directory)
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        build._materialize(directory, room, parsed, generated=True)
        if produce_from:
            for name, path in produce_from.items():
                core._copy_into(path, core._safe(room, name))
        rows, missing = _gate_rows(directory, room, parsed)
    ok = all(row['status'] == 'ok' for row in rows) and not missing
    result = {'ok': ok, 'root': checked['root'], 'gates': rows,
              'verdict': 'earned' if ok else 'broken'}
    if missing:
        result['environment'] = missing
    return result


def _snapshot(directory, parsed):
    names = [os.path.basename(recipe.recipe_path(directory))] + recipe._inputs(parsed, directory)
    return {name: core._hash_file(core._safe(directory, name)) for name in names}


def _usage(directory):
    data = build._read_usage(directory)
    return {key: value for key, value in data.items() if key in ('usd', 'tokens', 'calls')
            and isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    parsed = load_recipe(directory)
    if os.path.exists(os.path.join(directory, MANIFEST)):
        checked = verify(directory)
        if not checked['ok']:
            raise ClaimError('source identity does not match seal')
    else:
        checked = {'root': None}
    if preflight(parsed):
        raise ClaimError('environment missing: ' + ', '.join(preflight(parsed)))
    if os.path.exists(into) and os.listdir(into):
        raise ClaimError('rebuild destination is not empty')
    into = os.path.realpath(into)
    build._materialize(directory, into, parsed, generated=False)
    for name, path in (input_from or {}).items():
        if name not in recipe._inputs(parsed, directory):
            raise ClaimError(f'undeclared input: {name}')
        core._copy_into(path, core._safe(into, name))
    for name, path in (produce_from or {}).items():
        if name not in recipe.generated_outputs(parsed):
            raise ClaimError(f'undeclared generated output: {name}')
        core._copy_into(path, core._safe(into, name))
        ledger(into, {'event': 'reuse', 'output': name})
    before = _snapshot(into, parsed)
    backend = run.sandbox_backend()
    ledger(into, {'event': 'environment', 'python': sys.version.split()[0],
                  'platform': sys.platform, 'quarantine': backend})
    producer_info = {}
    for key, env_name in [('vendor', core._ENV_VENDOR), ('model', core._ENV_MODEL)]:
        if os.environ.get(env_name):
            producer_info[key] = os.environ[env_name]
    if producer_info:
        producer_info['blind'] = True
        ledger(into, {'event': 'producer', 'producer': producer_info})
    elapsed = 0.0
    calls = 0
    usage = {}
    for step in recipe.produces(parsed):
        if step.get('class', 'generated') not in ('generated', 'free') or 'from' in step:
            continue
        name = step['output']
        if name in (produce_from or {}):
            continue
        env = run._scrub_env()
        env['HOME'] = os.environ.get('HOME', env.get('HOME', into))
        env[core._ENV_CLAIM] = into
        env[core._ENV_OUTPUT] = core._safe(into, name)
        env[core._ENV_OUTPUTS] = json.dumps(recipe.generated_outputs(parsed))
        env[core._ENV_USAGE] = os.path.join(into, core.USAGE)
        if guidance:
            env[core._ENV_REQUEST] = str(step.get('guidance', step.get('request', '')))
        if producer_env:
            env.update(producer_env)
        start = time.monotonic()
        result = run._run(['/bin/sh', '-c', producer], into, core.PRODUCER_TIMEOUT, env)
        elapsed += time.monotonic() - start
        calls += 1
        if result.get('timeout') or result['returncode']:
            raise ClaimError(f'producer failed for {name}: {result.get("stderr", "")[-500:]}')
        core._hash_file(core._safe(into, name))
        usage.update(_usage(into))
    if _snapshot(into, parsed) != before:
        raise ClaimError('producer changed recipe or pinned input')
    rows, missing = _gate_rows(directory, into, parsed)
    for row in rows:
        ledger(into, {'event': 'gate', 'output': row['output'], 'status': row['status'],
                      'quarantine': row['quarantine']})
    if missing or any(row['status'] != 'ok' for row in rows):
        raise ClaimError(f'rebuild gates did not reproduce: {rows!r}')
    made_root = identity.root(load_recipe(into), into)
    if not input_from and checked['root'] is not None and made_root != checked['root']:
        raise ClaimError('rebuild root does not match source')
    sealing.seal(into)
    event = {'event': 'oracle', 'seconds': elapsed, 'calls': calls, 'quarantine': backend}
    event.update(usage)
    ledger(into, event)
    return {'root': made_root, 'gates': rows, 'quarantine': backend,
            'build_digest': build_digest(into)}


def gate_deciders(command):
    tokens = shlex.split(command)
    result = []
    for i, word in enumerate(tokens):
        if word in ('-m', '--module') and i + 1 < len(tokens):
            if tokens[i+1] == 'pytest':
                for candidate in tokens[i+2:]:
                    if candidate in ('&&', ';', '|'):
                        break
                    if not candidate.startswith('-'):
                        result.append(candidate)
            continue
        if word.startswith('./'):
            result.append(word[2:])
        if word in mutation._INTERPRETERS and i + 1 < len(tokens) and not tokens[i+1].startswith('-'):
            result.append(tokens[i+1])
    return list(dict.fromkeys(result))


def vacuous_gates(parsed):
    generated = set(recipe.generated_outputs(parsed))
    pinned = set(parsed.get('claim', {}).get('inputs', []))
    return [step['output'] for step in recipe.gates(parsed)
            if (deciders := gate_deciders(step['run'])) and all(x in generated and x not in pinned for x in deciders)]


def mutation_score(directory, max_mutants=core.MUTANT_CEILING):
    parsed = load_recipe(directory)
    names = recipe.generated_outputs(parsed)
    candidates = []
    for name in names:
        if not name.endswith('.py'):
            continue
        path = core._safe(directory, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8') as stream:
            source = stream.read()
        candidates.extend((name, content) for content in mutation._mutants(source))
    ordered = mutation._mutant_order(candidates, verify(directory)['root'])[:max_mutants]
    survivors = []
    for index, (name, content) in enumerate(ordered):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', encoding='utf-8', delete=False) as stream:
            stream.write(content)
            path = stream.name
        try:
            result = audit(directory, produce_from={name: path})
            if result['ok']:
                survivors.append(index)
        finally:
            os.unlink(path)
    total = len(ordered)
    rate = (total - len(survivors)) / total if total else 0.0
    result = {'mutants': total, 'survivors': survivors, 'killed': total - len(survivors), 'rate': rate}
    core._write_json(os.path.join(directory, core.MUTATION_RESIDUE), result)
    return result


def sign_node(root_value, digest, links):
    return hashlib.sha256(json.dumps([root_value, digest, sorted(links)], sort_keys=True).encode()).hexdigest()


def independence(directory):
    for event in reversed(ledger_events(directory)):
        if event.get('event') == 'producer' and isinstance(event.get('producer'), dict):
            return event['producer']
    return {}


def _leg(path):
    if os.path.isdir(path):
        checked = verify(path)
        audited = audit(path)
        return {'root': checked['root'], 'digest': build_digest(path),
                'audited': checked['ok'] and audited['ok'], 'cost': cost(path),
                'claim': load_recipe(path).get('claim', {}),
                'producer': independence(path), 'path': path, 'record': False}
    doc = record_read(path)
    return {'root': doc['root'], 'digest': doc['build_digest'],
            'audited': all(row['status'] == 'ok' for row in doc['gates']),
            'cost': doc.get('cost'), 'claim': doc.get('claim'),
            'producer': doc.get('producer', {}), 'path': path, 'record': True}


def crosscheck(m1, m2, m3, *, mutants=None):
    paths = [os.path.realpath(os.fspath(p)) for p in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise ClaimError('three machines must have distinct paths')
    legs = [_leg(p) for p in paths]
    roots = dict(zip(('M1', 'M2', 'M3'), (x['root'] for x in legs)))
    audited = dict(zip(('M1', 'M2', 'M3'), (x['audited'] for x in legs)))
    equivalence = len(set(roots.values())) == 1
    reuse = legs[0]['digest'] == legs[1]['digest']
    declared = legs[0]['claim']
    tolerance = (declared or {}).get('tolerance', core.TOLERANCE)
    one, three = legs[0]['cost'] or {}, legs[2]['cost'] or {}
    common = next((key for key in core.COST_LADDER if key in one and key in three), None)
    comparable = run._in_band(one[common], three[common], tolerance) if common else None
    cost_report = {'unit': common, 'comparable': comparable}
    if common:
        cost_report.update({'M1': one[common], 'M3': three[common]})
    rejected, incomplete = [], []
    if not equivalence:
        rejected.append('root')
    if not reuse:
        rejected.append('reuse')
    for role, value in audited.items():
        if not value:
            rejected.append(role + ' audit')
    if declared is None:
        incomplete.append('claim obligations')
    elif 'tolerance' in declared and comparable is False:
        rejected.append('tolerance')
    envelope = (declared or {}).get('envelope', {})
    if envelope:
        cost_report['envelope'] = {}
        for unit, ceiling in envelope.items():
            actual = three.get(unit)
            within = None if actual is None else actual <= ceiling
            cost_report['envelope'][unit] = {'ceiling': ceiling, 'actual': actual, 'within': within}
            if within is False:
                rejected.append('envelope ' + unit)
            elif within is None:
                incomplete.append('envelope ' + unit)
    score = None
    if declared and 'mutation_floor' in declared:
        if mutants is None or legs[2]['record']:
            incomplete.append('mutation floor')
        else:
            score = mutation_score(m3, max_mutants=mutants)
            score['ok'] = score['rate'] >= declared['mutation_floor']
            if not score['ok']:
                rejected.append('mutation floor')
    producer = legs[2]['producer']
    if producer.get('vendor') and producer.get('model'):
        independence_line = f"declared: {producer['vendor']}/{producer['model']}, " + (
            'blind workspace' if producer.get('blind') else 'workspace blindness unreported') + '; not proven'
    else:
        independence_line = 'unestablished from content'
    verdict = 'reject' if rejected else ('incomplete' if incomplete else 'accept')
    return {'satisfied': verdict == 'accept', 'verdict': verdict, 'rejected': rejected,
            'incomplete': incomplete, 'equivalence': equivalence, 'reuse': reuse,
            'roots': roots, 'audited': audited, 'cost': cost_report,
            'independence': independence_line, 'mutation_score': score}


def record_proof(m1, m2, m3, *, mutants=None):
    if not os.path.isdir(m1):
        raise ClaimError('proof needs a directory for M1')
    trails = []
    for path in (m2, m3):
        if os.path.isdir(path):
            continue
        anchor = os.environ.get(core._ENV_SIGNERS)
        if not anchor:
            raise ClaimError('record proof needs an anchor')
        signer = record_signer(path, anchor)
        if not signer:
            raise ClaimError('record signature is not anchored')
        trails.append({'digest': record_digest(record_read(path)), 'signer': signer})
    result = crosscheck(m1, m2, m3, mutants=mutants)
    result['proof_recorded'] = result['satisfied']
    if result['satisfied']:
        manifest = read_manifest(m1)
        manifest['proof'] = {'kind': 'crosscheck', 'm2': result['roots']['M2'],
                             'm3': result['roots']['M3'], 'records': trails}
        core._write_json(os.path.join(m1, MANIFEST), manifest)
    return result


def _trusted_signature(directory, manifest):
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not manifest.get('proof'):
        return False
    folder = os.path.join(directory, SIGN_DIR)
    if not os.path.isdir(folder):
        return False
    try:
        with open(anchor, encoding='utf-8') as stream:
            principals = [line.split()[0] for line in stream if line.strip() and not line.startswith('#')]
        for filename in os.listdir(folder):
            if not filename.endswith('.sign.json'):
                continue
            statement_path = os.path.join(folder, filename)
            packet_path = statement_path[:-len('.sign.json')] + '.packet.json'
            with open(statement_path, encoding='utf-8') as stream:
                statement = json.load(stream)
            with open(packet_path, encoding='utf-8') as stream:
                packet = json.load(stream)
            digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            if (statement.get('packet_digest') != digest or
                    statement.get('root') != manifest['root'] or
                    not statement.get('proof_recorded') or
                    packet.get('root') != manifest['root'] or
                    packet.get('build_digest') != build_digest(directory) or
                    packet.get('proof') != manifest['proof']):
                continue
            if statement.get('identity') not in principals:
                continue
            done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                                   '-I', statement['identity'], '-n', SIGN_NAMESPACE,
                                   '-s', statement_path + '.sig'],
                                  input=open(statement_path, 'rb').read(),
                                  capture_output=True)
            if done.returncode == 0:
                return True
    except (OSError, ValueError, KeyError):
        return False
    return False


def phase(directory):
    if not os.path.exists(os.path.join(directory, MANIFEST)):
        load_recipe(directory)
        return 'draft'
    checked = verify(directory)
    if not checked['ok']:
        raise ClaimError('claim identity does not match seal')
    return 'signed' if _trusted_signature(directory, read_manifest(directory)) else 'sealed'
