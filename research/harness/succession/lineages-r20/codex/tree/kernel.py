"""Public claim kernel: identities, cold verdicts, and three-machine evidence."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import venv
import platform
import tomllib
from pathlib import Path

from ._kernel import core, recipe, identity, seal as seals, run, build, attest, crosscheck as mutations

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
load_recipe = recipe.load_recipe
read_manifest = seals.read_manifest
preflight = run.preflight
ledger = run.ledger
ledger_events = run.ledger_events
record_validate = attest.record_validate
record_canonical = attest.record_canonical
record_digest = attest.record_digest


def seal(directory):
    parsed = _load(directory)
    manifest = {'name': parsed['claim']['name'], 'root': root(parsed, directory)}
    core._write_json(core._safe(directory, MANIFEST), manifest)
    return manifest


def verify(directory):
    manifest = read_manifest(directory)
    parsed = _load(directory)
    recomputed = root(parsed, directory)
    return {'ok': manifest['root'] == recomputed and manifest['name'] == parsed['claim']['name'],
            'root': manifest['root'], 'name': manifest['name'], 'recomputed': recomputed}


def sandbox(command='true', directory='.'):
    return (command, run.sandbox_backend())


def run_gate(command, directory, parsed=None):
    missing = preflight(parsed or {})
    if missing:
        return {'status': 'environment', 'quarantine': None, 'detail': 'missing requirements: ' + ', '.join(missing)}
    backend = run.sandbox_backend()
    env = run._scrub_env(directory, parsed, backend)
    if backend in ('seatbelt', 'bubblewrap'):
        env[_JAILED] = backend
    result = run._run(run._sandbox_argv(command, directory, backend), directory, env, run.gate_timeout(parsed))
    result['quarantine'] = backend
    return result


def cost(directory):
    totals = {}
    for event in ledger_events(directory):
        if event.get('kind') not in (None, 'producer') and event.get('event') not in ('oracle', 'producer'):
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _obligations(parsed):
    claim = parsed['claim']
    return {key: claim[key] for key in ('tolerance', 'envelope', 'mutation_floor') if key in claim}


def _check_envelope(parsed):
    claim = parsed['claim']
    if 'envelope' not in claim:
        return
    envelope = claim['envelope']
    if not isinstance(envelope, dict) or not envelope:
        raise ClaimError('envelope must be a nonempty table')
    for unit, value in envelope.items():
        if unit not in core.COST_KEYS or type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ClaimError('invalid envelope ceiling')


def _load(directory):
    path = recipe.recipe_path(directory)
    try:
        with open(path, 'rb') as f:
            parsed = tomllib.load(f)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ClaimError('cannot parse recipe: ' + str(exc)) from exc
    claim = parsed.get('claim')
    if not isinstance(claim, dict) or not isinstance(claim.get('name'), str):
        raise ClaimError('recipe needs [claim] with a string name')
    version = claim.get('format', 1)
    if type(version) is not int or version < 1 or version > core.FORMAT:
        raise ClaimError('unsupported claim format')
    recipe._inputs(parsed, directory)
    for index, step in enumerate(recipe._steps(parsed), 1):
        kind = step.get('kind')
        if kind not in core.KINDS:
            raise ClaimError(f'step {index} has invalid kind')
        output = step.get('output')
        if not isinstance(output, str) or not output or os.path.isabs(output) or any(x in ('', '.', '..') for x in output.split('/')):
            raise ClaimError(f'step {index} has invalid output')
        cls = step.get('class', 'generated' if kind == 'produce' else 'pinned')
        if cls not in ('generated', 'free', 'pinned', 'exact', 'validated'):
            raise ClaimError(f'step {index} has invalid class')
        if cls not in ('generated', 'free'):
            core._safe(directory, output)
        if kind == 'gate' and not isinstance(step.get('run'), str):
            raise ClaimError(f'gate step {index} needs a run command')
        if 'from' in step and not isinstance(step['from'], str):
            raise ClaimError(f'step {index} has invalid from value')
    _check_envelope(parsed)
    return parsed


load_recipe = _load


def _room(source, target, parsed, generated):
    build._materialize(source, target, parsed, include_generated=generated)


def _judge(room, source, parsed, venv=None):
    rows = []
    missing = preflight(parsed)
    for step in recipe.gates(parsed):
        name = step['output']
        if missing:
            rows.append({'output': name, 'status': 'environment', 'quarantine': None,
                         'detail': 'missing requirements: ' + ', '.join(missing)})
            continue
        output = core._safe(room, name)
        if os.path.lexists(output):
            os.unlink(output)
        if venv:
            # run_gate builds a scrubbed environment, so prepend the furnished
            # interpreter to the allowlisted PATH only around this invocation.
            original = os.environ.get('PATH')
            os.environ['PATH'] = os.path.join(venv, 'bin') + os.pathsep + (original or os.defpath)
        try:
            result = run_gate(step['run'], room, parsed)
        finally:
            if venv:
                if original is None:
                    os.environ.pop('PATH', None)
                else:
                    os.environ['PATH'] = original
        row = {'output': name, 'status': result['status'],
               'quarantine': result.get('quarantine')}
        if result['status'] == 'ok':
            source_path = core._safe(source, name)
            if os.path.lexists(source_path):
                row['status'] = 'ok' if build._compare_pin(source, room, name) else 'mismatch'
            elif not os.path.isfile(output):
                row['status'] = 'mismatch'
        if result.get('stderr'):
            row['detail'] = result['stderr'][-500:]
        rows.append(row)
    return rows


def _furnish(room, parsed):
    name = parsed['claim'].get('environment')
    if not name:
        return None
    source = core._safe(room, name)
    digest = core._hash_file(source)
    cache = os.environ.get(core._ENV_CACHE, os.path.join(os.path.expanduser('~'), '.cache', 'reticuli', 'env'))
    key = hashlib.sha256(f'{digest}:{sys.executable}:{platform.platform()}'.encode()).hexdigest()
    target = os.path.join(cache, key)
    python = os.path.join(target, 'bin', 'python')
    if os.path.isfile(python):
        return target
    os.makedirs(cache, exist_ok=True)
    venv.EnvBuilder(with_pip=True).create(target)
    done = subprocess.run([python, '-m', 'pip', 'install', '--require-hashes',
                           '--only-binary=:all:', '-r', source], cwd=room,
                          capture_output=True, text=True, timeout=core.FURNISH_TIMEOUT)
    if done.returncode:
        shutil.rmtree(target, ignore_errors=True)
        raise ClaimError('cannot furnish environment: ' + done.stderr[-500:])
    return target


def audit(directory, shallow=False, produce_from=None):
    parsed = _load(directory)
    verified = verify(directory)
    if not verified['ok']:
        return {'ok': False, 'root': verified['root'], 'gates': [],
                'environment': [], 'verdict': 'identity mismatch'}
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        _room(directory, room, parsed, True)
        if produce_from:
            for name, source in produce_from.items():
                if name not in [s['output'] for s in recipe.produces(parsed)]:
                    raise ClaimError('unknown substituted output: ' + name)
                core._copy_into(source, core._safe(room, name))
        try:
            venv = _furnish(room, parsed)
            gates = _judge(room, directory, parsed, venv)
        except ClaimError as exc:
            gates = [{'output': s['output'], 'status': 'environment', 'quarantine': None,
                      'detail': str(exc)} for s in recipe.gates(parsed)]
    missing = preflight(parsed)
    ok = all(g['status'] == 'ok' for g in gates)
    return {'ok': ok, 'root': verified['root'], 'gates': gates,
            'environment': missing, 'verdict': 'earned' if ok else 'carried or broken'}


def _produce(command, room, parsed, step, guidance, producer_env):
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.setdefault('PATH', os.defpath)
    env[core._ENV_CLAIM] = parsed['claim']['name']
    env[core._ENV_OUTPUT] = os.path.abspath(core._safe(room, step['output']))
    env[core._ENV_OUTPUTS] = json.dumps(recipe.generated_outputs(parsed))
    env[core._ENV_USAGE] = os.path.abspath(core._safe(room, core.USAGE))
    os.makedirs(os.path.dirname(env[core._ENV_USAGE]), exist_ok=True)
    if guidance:
        env[core._ENV_REQUEST] = build._step_guidance(step)
    if producer_env:
        env.update({str(key): str(value) for key, value in producer_env.items()})
    return run._run([core._SHELL, '-c', command], room, env, core.PRODUCER_TIMEOUT)


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    parsed = _load(directory)
    if os.path.exists(os.path.join(directory, MANIFEST)) and not verify(directory)['ok']:
        raise ClaimError('source identity mismatch')
    if preflight(parsed):
        raise ClaimError('environment missing: ' + ', '.join(preflight(parsed)))
    into = os.path.abspath(into)
    if os.path.exists(into) and os.listdir(into):
        raise ClaimError('rebuild target is not empty: ' + into)
    os.makedirs(into, exist_ok=True)
    _room(directory, into, parsed, False)
    if input_from:
        for name, source in input_from.items():
            core._copy_into(source, core._safe(into, name))
    if produce_from:
        for name, source in produce_from.items():
            core._copy_into(source, core._safe(into, name))
            ledger(into, {'event': 'reuse', 'output': name})
    watch = {}
    recipe_name = os.path.basename(recipe.recipe_path(into))
    for name in [recipe_name] + recipe._inputs(parsed, into):
        watch[name] = core._hash_file(core._safe(into, name))
    outputs = recipe.generated_outputs(parsed)
    started = time.monotonic()
    outcomes = []
    to_make = [s for s in recipe.produces(parsed) if s['output'] in outputs and not (produce_from and s['output'] in produce_from)]
    for step in to_make:
        outcome = _produce(producer, into, parsed, step, guidance, producer_env)
        outcomes.append(outcome)
        if outcome['status'] != 'ok':
            raise ClaimError('producer failed: ' + (outcome.get('stderr') or outcome['status'])[-500:])
        if not os.path.isfile(core._safe(into, step['output'])):
            raise ClaimError('producer did not write ' + step['output'])
    for name, digest in watch.items():
        if core._hash_file(core._safe(into, name)) != digest:
            raise ClaimError('producer changed pinned bytes: ' + name)
    try:
        venv = _furnish(into, parsed)
    except ClaimError as exc:
        raise ClaimError('environment: ' + str(exc)) from exc
    gates = _judge(into, directory, parsed, venv)
    for row in gates:
        ledger(into, {'event': 'gate', 'output': row['output'], 'status': row['status'],
                      'quarantine': row['quarantine']})
    if not all(g['status'] == 'ok' for g in gates):
        raise ClaimError('rebuild gates did not reproduce: ' + repr(gates))
    manifest = seal(into)
    if not input_from and os.path.exists(os.path.join(directory, MANIFEST)) and manifest['root'] != read_manifest(directory)['root']:
        raise ClaimError('rebuilt root differs from source')
    usage = build._read_usage(into)
    event = {'event': 'oracle', 'kind': 'producer', 'calls': 1,
             'seconds': time.monotonic() - started,
             'quarantine': run.sandbox_backend()}
    for key in ('usd', 'tokens', 'calls'):
        value = usage.get(key)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            event[key] = value
    ledger(into, event)
    ledger(into, {'event': 'environment', 'python': sys.version.split()[0],
                  'platform': sys.platform, 'quarantine': run.sandbox_backend()})
    vendor, model = os.environ.get(core._ENV_VENDOR), os.environ.get(core._ENV_MODEL)
    if vendor or model:
        ledger(into, {'event': 'producer', 'vendor': vendor, 'model': model, 'blind': True})
    return {'root': manifest['root'], 'gates': gates, 'quarantine': run.sandbox_backend(),
            'build_digest': build_digest(into)}


def _trusted_statement(directory):
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):
        return False
    folder = os.path.join(directory, SIGN_DIR)
    if not os.path.isdir(folder):
        return False
    manifest = read_manifest(directory)
    proof = manifest.get('proof')
    if not proof:
        return False
    current = {'root': manifest['root'], 'build_digest': build_digest(directory), 'proof': proof}
    for file in sorted(os.listdir(folder)):
        if not file.endswith('.sign.json'):
            continue
        statement_path = os.path.join(folder, file)
        packet_path = os.path.join(folder, file[:-10] + '.packet.json')
        signature_path = statement_path + '.sig'
        try:
            with open(statement_path, 'rb') as f:
                statement_bytes = f.read()
            with open(packet_path, encoding='utf-8') as f:
                packet = json.load(f)
            statement = json.loads(statement_bytes)
            if packet != current or statement.get('root') != manifest['root'] or not statement.get('proof_recorded'):
                continue
            if statement.get('packet_digest') != hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest():
                continue
            ident = statement.get('identity')
            if not isinstance(ident, str):
                continue
            done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                                   '-I', ident, '-n', SIGN_NAMESPACE, '-s', signature_path],
                                  input=statement_bytes, capture_output=True, timeout=10)
            if done.returncode == 0:
                return True
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    return False


def phase(directory):
    if not os.path.exists(os.path.join(directory, MANIFEST)):
        _load(directory)
        return 'draft'
    checked = verify(directory)
    if not checked['ok']:
        raise ClaimError('claim identity mismatch')
    return 'signed' if _trusted_statement(directory) else 'sealed'


def sign_node(root_value, digest, links):
    return hashlib.sha256(json.dumps({'root': root_value, 'build_digest': digest,
                                      'links': sorted(links)}, sort_keys=True).encode()).hexdigest()


def record_read(path):
    doc = attest.record_read(path)
    with open(path, 'rb') as f:
        raw = f.read()
    if raw != record_canonical(doc):
        raise ClaimError('record bytes are not canonical')
    return doc


def gate_deciders(command):
    result = []
    for match in re.finditer(r'(?:^|[;&|]\s*|\s)(?:python(?:\d+(?:\.\d+)?)?|pytest|py\.test)\s+(?:-m\s+pytest\s+)?(?:-q\s+)?([^\s;&|]+)', command):
        token = match.group(1)
        if token not in ('-c', '-m'):
            result.append(token)
    result += re.findall(r'(?<!\w)\./([\w./-]+)', command)
    return result


def vacuous_gates(parsed):
    generated = {s['output'] for s in recipe.produces(parsed)
                 if s.get('class', 'generated') in ('generated', 'free')}
    claimed = set(parsed.get('claim', {}).get('inputs', []))
    return [s['output'] for s in recipe.gates(parsed)
            if (deciders := gate_deciders(s['run'])) and all(d in generated and d not in claimed for d in deciders)]


def mutation_score(directory, max_mutants=core.MUTANT_CEILING):
    parsed = _load(directory)
    files = recipe.generated_outputs(parsed)
    candidates = []
    for name in files:
        path = core._safe(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                original = f.read()
        except UnicodeError:
            continue
        for changed in mutations._mutants(original):
            candidates.append((name, changed))
    # The sample is tied to generated bytes, so changing only the check leaves
    # the number and order of mutants fixed.
    candidates = mutations._mutant_order(candidates, build_digest(directory))[:max_mutants]
    killed = 0
    survivors = []
    for index, (name, changed) in enumerate(candidates):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as room:
            _room(directory, room, parsed, True)
            with open(core._safe(room, name), 'w', encoding='utf-8') as f:
                f.write(changed)
            rows = _judge(room, directory, parsed)
            if all(row['status'] == 'ok' for row in rows):
                survivors.append(index)
            else:
                killed += 1
    result = {'mutants': len(candidates), 'killed': killed, 'survivors': survivors,
              'rate': killed / len(candidates) if candidates else 0.0}
    core._write_json(core._safe(directory, core.MUTATION_RESIDUE), result)
    return result


def independence(directory):
    declaration = {}
    for event in ledger_events(directory):
        if event.get('event') == 'producer' and ('vendor' in event or 'model' in event):
            declaration.update({k: event[k] for k in ('vendor', 'model', 'blind') if k in event})
    return declaration


def _leg(path):
    if os.path.isfile(path):
        doc = record_read(path)
        return {'root': doc['root'], 'name': doc['name'], 'digest': doc['build_digest'],
                'audited': all(g['status'] == 'ok' for g in doc['gates']),
                'gates': doc['gates'], 'cost': doc.get('cost'),
                'claim': doc.get('claim'), 'record_version': doc['record'],
                'producer': doc.get('producer', {}), 'record': True}
    checked = verify(path)
    audited = audit(path)
    parsed = _load(path)
    return {'root': checked['root'], 'name': checked['name'], 'digest': build_digest(path),
            'audited': checked['ok'] and audited['ok'], 'gates': audited['gates'],
            'cost': cost(path), 'claim': _obligations(parsed), 'record_version': None,
            'producer': independence(path), 'record': False}


def _cost_comparison(original, redo, tolerance):
    selected = next((key for key in core.COST_LADDER
                     if original and redo and key in original and key in redo), None)
    if selected is None:
        return {'unit': None, 'comparable': None, 'M1': original, 'M3': redo}
    one, three = original[selected], redo[selected]
    if one == 0 or three == 0:
        comparable = one == three
    else:
        comparable = 1 / tolerance <= three / one <= tolerance
    return {'unit': selected, 'comparable': comparable, 'M1': original, 'M3': redo}


def crosscheck(m1, m2, m3, *, mutants=None):
    paths = [os.path.realpath(os.fspath(p)) for p in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise ClaimError('three machines must be distinct paths')
    legs = {role: _leg(path) for role, path in zip(('M1', 'M2', 'M3'), paths)}
    roots = {role: leg['root'] for role, leg in legs.items()}
    audited = {role: leg['audited'] for role, leg in legs.items()}
    equivalent = len(set(roots.values())) == 1
    reuse = legs['M1']['digest'] == legs['M2']['digest']
    claim = legs['M1']['claim']
    tolerance = claim.get('tolerance', core.TOLERANCE) if claim is not None else core.TOLERANCE
    comparison = _cost_comparison(legs['M1']['cost'], legs['M3']['cost'], tolerance)
    rejected = []
    incomplete = []
    if not equivalent:
        rejected.append('root')
    if not reuse:
        rejected.append('reuse')
    for role, ok in audited.items():
        if not ok:
            rejected.append('audit ' + role)
    if claim is None:
        incomplete.append('declared conditions')
        claim = {}
    if 'tolerance' in claim and comparison['comparable'] is False:
        rejected.append('tolerance')
    envelope_report = {}
    for key, ceiling in claim.get('envelope', {}).items():
        measured = (legs['M3']['cost'] or {}).get(key)
        within = None if measured is None else measured <= ceiling
        envelope_report[key] = {'ceiling': ceiling, 'measured': measured, 'within': within}
        if within is False:
            rejected.append('envelope ' + key)
        elif within is None:
            incomplete.append('envelope ' + key)
    comparison['envelope'] = envelope_report
    score = None
    if 'mutation_floor' in claim:
        if mutants is None or legs['M3']['record']:
            incomplete.append('mutation floor')
        else:
            score = mutation_score(m3, max_mutants=mutants)
            score['ok'] = score['rate'] >= claim['mutation_floor']
            if not score['ok']:
                rejected.append('mutation floor')
    producer = legs['M3']['producer']
    if producer.get('vendor') and producer.get('model') and producer.get('blind'):
        independent = f"declared: {producer['vendor']}/{producer['model']}, blind workspace (not proven)"
    else:
        independent = 'unestablished (not proven)'
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied': verdict == 'accept', 'verdict': verdict,
            'rejected': rejected, 'incomplete': incomplete,
            'roots': roots, 'equivalence': equivalent, 'reuse': reuse,
            'audited': audited, 'cost': comparison, 'mutation_score': score,
            'independence': independent}


def _record_signer(path, anchor):
    doc = record_read(path)
    signature = os.fspath(path) + '.sig'
    if not os.path.isfile(signature):
        raise ClaimError('record has no signature')
    with open(anchor, encoding='utf-8') as f:
        identities = [line.split()[0] for line in f if line.strip() and not line.lstrip().startswith('#')]
    for ident in identities:
        try:
            done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                                   '-I', ident, '-n', RECORD_NAMESPACE, '-s', signature],
                                  input=record_canonical(doc), capture_output=True, timeout=10)
            if done.returncode == 0:
                return ident
        except (OSError, subprocess.TimeoutExpired):
            pass
    raise ClaimError('record signature does not match a trusted signer')


def record_proof(m1, m2, m3, *, mutants=None):
    if os.path.isfile(m1):
        raise ClaimError('proof requires a directory for M1')
    result = crosscheck(m1, m2, m3, mutants=mutants)
    result['proof_recorded'] = False
    if not result['satisfied']:
        return result
    references = []
    for role, path in (('M2', m2), ('M3', m3)):
        if os.path.isfile(path):
            anchor = os.environ.get(core._ENV_SIGNERS)
            if not anchor or not os.path.isfile(anchor):
                raise ClaimError('record proof requires trusted signer anchor')
            signer = _record_signer(path, anchor)
            references.append({'role': role, 'digest': record_digest(record_read(path)),
                               'signer': signer})
    manifest = read_manifest(m1)
    manifest['proof'] = {'kind': 'crosscheck', 'roots': result['roots'],
                         'records': references}
    core._write_json(core._safe(m1, MANIFEST), manifest)
    result['proof_recorded'] = True
    return result
