"""Public kernel API for content-addressed claims."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import tomllib
import venv

from ._kernel import attest, build, core, crosscheck as compare, identity, recipe, run, seal as sealing

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
record_validate = attest.record_validate
record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_signer = attest.record_signer
root = identity.root
build_digest = identity.build_digest
read_manifest = sealing.read_manifest
_hash_file = core._hash_file
ledger = run.ledger
ledger_events = run.ledger_events
preflight = run.preflight
mutation_score = compare.mutation_score


def load_recipe(claim_dir):
    document = recipe.load_recipe(claim_dir)
    claim = document['claim']
    if 'envelope' in claim:
        envelope = claim['envelope']
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError('envelope must be a nonempty table')
        for unit, value in envelope.items():
            if unit not in core.COST_KEYS or type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ClaimError('invalid envelope ceiling')
    return document


def verify(claim_dir):
    result = sealing.verify(claim_dir)
    result['name'] = read_manifest(claim_dir)['name']
    return result


def seal(claim_dir):
    try:
        return sealing.seal(claim_dir)
    except ClaimError as exc:
        # Generated files are outside identity. A link there may be sealed,
        # although copying it into a judging room is refused by audit.
        if 'symbolic link in claim path' not in str(exc):
            raise
        path = recipe.recipe_path(claim_dir)
        with open(path, 'rb') as source:
            document = tomllib.load(source)
        manifest = {'name': document['claim']['name'],
                    'root': identity.root(document, claim_dir)}
        core._write_json(os.path.join(claim_dir, MANIFEST), manifest)
        return manifest


def record_read(path):
    doc = attest.record_read(path)
    if open(path, 'rb').read() != attest.record_canonical(doc):
        raise ClaimError('record is not in canonical form')
    return doc


def sandbox(command='true', workspace='.'):
    backend = run.sandbox_backend()
    return run._sandbox_argv(command, workspace, backend), backend


def run_gate(command, workspace, document=None, extra_env=None):
    backend = run.sandbox_backend()
    extra = dict(extra_env or {})
    if backend in ('seatbelt', 'bubblewrap'):
        extra[core._JAILED] = backend
    result = run.run_gate(command, workspace, document, extra)
    run.ledger(workspace, {'gate': command, 'quarantine': result['quarantine'], 'status': result['status']})
    return result


def cost(workspace):
    totals = {}
    for event in run.ledger_events(workspace):
        if not (event.get('kind') in ('producer', 'production') or event.get('event') == 'oracle'):
            continue
        for key in core.COST_KEYS:
            value = event.get(key)
            if type(value) in (int, float):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def independence(workspace):
    for event in run.ledger_events(workspace):
        if event.get('event') == 'producer':
            return {k: event[k] for k in ('vendor', 'model', 'blind') if k in event}
    return {}


def _materialized_judge(source, room, document, *, unsealed=False):
    missing = run.preflight(document)
    furnished = None
    if not missing:
        try:
            furnished = _furnish(room, document)
        except ClaimError as exc:
            missing.append(str(exc))
    gates = []
    for step in recipe.gates(document):
        name = step['output']
        if missing:
            gates.append({'output': name, 'status': 'environment', 'quarantine': None,
                          'detail': ', '.join(missing)})
            continue
        env = {'PATH': furnished + os.pathsep + os.environ.get('PATH', os.defpath)} if furnished else None
        outcome = run_gate(step['run'], room, document, env)
        status = outcome['status']
        if status == 'ok':
            try:
                original = core._safe(source, name)
                generated = core._safe(room, name)
                status = 'ok' if core._hash_file(original) == core._hash_file(generated) else 'mismatch'
            except ClaimError:
                status = 'ok' if unsealed and os.path.isfile(core._safe(room, name)) else 'mismatch'
        gates.append({'output': name, 'status': status, 'quarantine': outcome['quarantine'],
                      'stdout': outcome.get('stdout', ''), 'stderr': outcome.get('stderr', '')})
    return gates, missing


def _furnish(room, document):
    name = document['claim'].get('environment')
    if not name:
        return None
    path = core._safe(room, name)
    digest = core._hash_file(path)
    cache = os.environ.get(core._ENV_CACHE, os.path.join(os.path.expanduser('~'), '.cache', 'reticuli', 'env'))
    destination = os.path.join(cache, hashlib.sha256((digest + os.sys.executable).encode()).hexdigest())
    python = os.path.join(destination, 'bin', 'python')
    if not os.path.isfile(python):
        os.makedirs(cache, exist_ok=True)
        venv.create(destination, with_pip=True)
        done = subprocess.run([python, '-m', 'pip', 'install', '--require-hashes',
                               '--only-binary=:all:', '-r', path], cwd=room,
                              capture_output=True, text=True, check=False,
                              timeout=core.FURNISH_TIMEOUT)
        if done.returncode:
            shutil.rmtree(destination, ignore_errors=True)
            raise ClaimError('cannot furnish environment: ' + done.stderr.strip())
    return os.path.join(destination, 'bin')


def audit(claim_dir, *, shallow=False, produce_from=None):
    source = os.fspath(claim_dir)
    checked = verify(source)
    if not checked['ok']:
        return {'ok': False, 'root': checked['root'], 'gates': [], 'environment': [],
                'verdict': 'identity mismatch'}
    document = load_recipe(source)
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        build._materialize(source, room, document)
        if produce_from:
            for name, path in produce_from.items():
                if name not in recipe.generated_outputs(document):
                    raise ClaimError(f'not a generated output: {name}')
                core._copy_into(path, core._safe(room, name))
        gates, missing = _materialized_judge(source, room, document)
    ok = all(g['status'] == 'ok' for g in gates)
    return {'ok': ok, 'root': checked['root'], 'gates': gates, 'environment': missing,
            'verdict': 'earned' if ok else 'carried or broken'}


def _snapshots(room, document):
    names = [os.path.basename(recipe.recipe_path(room)), *recipe._inputs(document, room)]
    return {name: core._hash_file(core._safe(room, name)) for name in names}


def rebuild(claim_dir, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    source, room = os.fspath(claim_dir), os.fspath(into)
    document = load_recipe(source)
    expected = None
    if os.path.exists(os.path.join(source, MANIFEST)):
        checked = verify(source)
        if not checked['ok']:
            raise ClaimError('source claim identity mismatch')
        expected = checked['root']
    if os.path.exists(room) and os.listdir(room):
        raise ClaimError(f'rebuild target is not empty: {room}')
    missing = preflight(document)
    if missing:
        raise ClaimError('environment missing: ' + ', '.join(missing))
    build._materialize(source, room, document, generated=True)
    if input_from:
        for name, path in input_from.items():
            if name not in recipe._inputs(document, source):
                raise ClaimError(f'not a pinned input: {name}')
            core._copy_into(path, core._safe(room, name))
    if produce_from:
        for name, path in produce_from.items():
            if name not in recipe.generated_outputs(document):
                raise ClaimError(f'not a generated output: {name}')
            core._copy_into(path, core._safe(room, name))
            run.ledger(room, {'event': 'reuse', 'output': name})
    pinned_before = _snapshots(room, document)
    backend = run.sandbox_backend()
    run.ledger(room, {'event': 'environment', 'python': os.sys.version.split()[0],
                      'platform': os.sys.platform, 'quarantine': backend})
    productions = []
    produces = [step for step in recipe.produces(document)
                if step.get('class', 'generated') == 'generated'
                and 'from' not in step and not (produce_from and step['output'] in produce_from)]
    outputs = recipe.generated_outputs(document)
    for step in produces:
        result = build._produce(producer, room, document, step, outputs,
                                guidance=guidance, producer_env=producer_env)
        if result['status'] != 'ok':
            raise ClaimError(f"producer {result['status']}: {result.get('stderr', '')[-300:]}")
        productions.append(result)
    if _snapshots(room, document) != pinned_before:
        raise ClaimError('producer rewrote pinned bytes')
    gates, missing = _materialized_judge(source, room, document, unsealed=expected is None)
    if missing:
        raise ClaimError('environment missing: ' + ', '.join(missing))
    if any(g['status'] != 'ok' for g in gates):
        raise ClaimError('gates failed: ' + repr(gates))
    if _snapshots(room, document) != pinned_before:
        raise ClaimError('producer rewrote pinned bytes')
    manifest = seal(room)
    if expected is not None and not input_from and manifest['root'] != expected:
        raise ClaimError('rebuilt root mismatch')
    usage = build._read_usage(room)
    for result in productions:
        event = {'kind': 'producer', 'event': 'producer', 'calls': 1,
                 'seconds': result['seconds'], 'blind': True}
        for key, var in (('vendor', core._ENV_VENDOR), ('model', core._ENV_MODEL)):
            if os.environ.get(var):
                event[key] = os.environ[var]
        for key in ('usd', 'tokens', 'calls'):
            value = usage.get(key)
            if type(value) in (int, float):
                event[key] = value
        run.ledger(room, event)
    return {'ok': True, 'root': manifest['root'], 'gates': gates,
            'quarantine': backend, 'build_digest': build_digest(room)}


def crosscheck(m1, m2, m3, *, mutants=None):
    return compare.crosscheck(m1, m2, m3, mutants=mutants, audit_fn=audit)


def record_proof(m1, m2, m3, *, mutants=None):
    return compare.record_proof(m1, m2, m3, mutants=mutants, audit_fn=audit)


def sign_node(root_value, digest, links):
    return hashlib.sha256(json.dumps([root_value, digest, sorted(links)], sort_keys=True).encode()).hexdigest()


def _authorized(claim_dir):
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):
        return False
    manifest = read_manifest(claim_dir)
    proof = manifest.get('proof')
    if not proof:
        return False
    folder = os.path.join(claim_dir, SIGN_DIR)
    if not os.path.isdir(folder):
        return False
    with open(anchor, encoding='utf-8') as source:
        principals = [line.split()[0] for line in source if line.strip() and not line.lstrip().startswith('#')]
    for name in os.listdir(folder):
        if not name.endswith('.sign.json'):
            continue
        statement_path = os.path.join(folder, name)
        packet_path = statement_path[:-10] + '.packet.json'
        try:
            statement = json.load(open(statement_path, encoding='utf-8'))
            packet = json.load(open(packet_path, encoding='utf-8'))
            digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            if (statement.get('packet_digest') != digest or not statement.get('proof_recorded')
                    or packet.get('root') != manifest['root']
                    or packet.get('build_digest') != build_digest(claim_dir)
                    or packet.get('proof') != proof):
                continue
            for principal in principals:
                checked = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                    '-I', principal, '-n', SIGN_NAMESPACE, '-s', statement_path + '.sig'],
                    input=open(statement_path, 'rb').read(), capture_output=True, check=False)
                if checked.returncode == 0:
                    return True
        except (OSError, ValueError, KeyError):
            continue
    return False


def phase(claim_dir):
    load_recipe(claim_dir)
    if not os.path.isfile(os.path.join(claim_dir, MANIFEST)):
        return 'draft'
    checked = verify(claim_dir)
    if not checked['ok']:
        raise ClaimError('claim identity mismatch')
    return 'signed' if _authorized(claim_dir) else 'sealed'


def gate_deciders(command):
    import shlex
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    found = []
    for index, token in enumerate(tokens):
        if token in ('-m', '--module') and index + 1 < len(tokens):
            module = tokens[index + 1]
            if module in ('pytest', 'py.test'):
                for following in tokens[index + 2:]:
                    if following in ('&&', ';', '||', '|'):
                        break
                    if not following.startswith('-'):
                        found.append(following)
                        break
            else:
                found.append(module)
        elif token.startswith('./'):
            found.append(token[2:])
        elif token in ('python', 'python3', 'bash', 'sh') and index + 1 < len(tokens):
            following = tokens[index + 1]
            if not following.startswith('-'):
                found.append(following)
    return found


def vacuous_gates(document):
    inputs = set(document.get('claim', {}).get('inputs', []))
    generated = set(recipe.generated_outputs(document))
    result = []
    for step in recipe.gates(document):
        deciders = gate_deciders(step['run'])
        if deciders and all(decider in generated and decider not in inputs for decider in deciders):
            result.append(step['output'])
    return result
