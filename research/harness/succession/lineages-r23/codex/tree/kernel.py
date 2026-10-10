"""Public kernel API for content-addressed claims."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from ._kernel import core, recipe as _recipe, identity as _identity, seal as _seal
from ._kernel import run as _run, build as _build, attest as _attest
from ._kernel import crosscheck as _cross

ClaimError = core.ClaimError
NAMESPACE = core.NAMESPACE
SIGN_NAMESPACE = core.SIGN_NAMESPACE
SIGN_DIR = core.SIGN_DIR
STORE = core.STORE
MANIFEST = core.MANIFEST
LEDGER = core.LEDGER
RECIPE = core.RECIPE
_JAILED = core._JAILED
RECORD_NAMESPACE = _attest.RECORD_NAMESPACE
RECORD_FORMAT = _attest.RECORD_FORMAT
_hash_file = core._hash_file
load_recipe = _recipe.load_recipe
root = _identity.root
build_digest = _identity.build_digest
verify = _seal.verify
read_manifest = _seal.read_manifest
ledger = _run.ledger
ledger_events = _run.ledger_events
preflight = _run.preflight
record_canonical = _attest.record_canonical
record_digest = _attest.record_digest
record_validate = _attest.record_validate
record_signer = _attest.record_signer


def seal(directory):
    # A generated output is outside identity; sealing may therefore encounter
    # an unsafe generated path. Audit will refuse when it tries to copy it.
    original = _recipe._path
    def declared_path(base, name):
        if not isinstance(name, str) or not name or os.path.isabs(name) or '..' in name.split('/'):
            raise ClaimError(f'invalid claim path: {name!r}')
        return os.path.join(os.fspath(base), name)
    try:
        _recipe._path = declared_path
        return _seal.seal(directory)
    finally:
        _recipe._path = original


def record_read(path):
    doc = _attest.record_read(path)
    with open(path, 'rb') as stream:
        raw = stream.read()
    if raw != _attest.record_canonical(doc):
        raise ClaimError('record bytes are not canonical')
    return doc


def sandbox(command, directory):
    backend = _run.sandbox_backend()
    return _run._sandbox_argv(command, directory, backend), backend


def run_gate(command, directory, recipe=None, env=None):
    backend = _run.sandbox_backend()
    variables = _run._scrub_env(directory, env, backend)
    if backend in ('seatbelt', 'bubblewrap'):
        variables[core._JAILED] = backend
    result = _run._run(_run._sandbox_argv(command, directory, backend), directory,
                       variables, min(_run.gate_timeout(recipe), _run.gate_timeout()))
    result['quarantine'] = backend
    return result


def cost(directory):
    totals = {}
    for event in ledger_events(directory):
        for unit in core.COST_KEYS:
            value = event.get(unit)
            if type(value) in (int, float) and value >= 0:
                totals[unit] = totals.get(unit, 0) + value
    return totals or None


def independence(directory):
    for event in ledger_events(directory):
        if event.get('event') == 'producer':
            return {k: event[k] for k in ('vendor', 'model', 'blind', 'cutoff') if k in event}
    return {}


def sign_node(root, digest, links):
    return hashlib.sha256(json.dumps({'root': root, 'build_digest': digest,
                                      'links': sorted(links)}, sort_keys=True).encode()).hexdigest()


def _signed(directory, manifest):
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor or not manifest.get('proof'):
        return False
    signing_dir = core._safe(directory, core.SIGN_DIR)
    if not os.path.isdir(signing_dir):
        return False
    for name in sorted(os.listdir(signing_dir)):
        if not name.endswith('.sign.json'):
            continue
        statement_path = os.path.join(signing_dir, name)
        packet_path = os.path.join(signing_dir, name[:-10] + '.packet.json')
        try:
            with open(statement_path, encoding='utf-8') as stream:
                statement = json.load(stream)
            with open(packet_path, encoding='utf-8') as stream:
                packet = json.load(stream)
            packet_digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            if statement.get('packet_digest') != packet_digest:
                continue
            if packet != {'root': manifest['root'], 'build_digest': build_digest(directory),
                          'proof': manifest.get('proof')}:
                continue
            if not statement.get('proof_recorded') or statement.get('root') != manifest['root']:
                continue
            if not _build._ssh_verify(open(statement_path, 'rb').read(), statement_path + '.sig',
                                      anchor, statement.get('identity', 'reticuli')):
                continue
            return True
        except (OSError, ValueError, ClaimError):
            continue
    return False


def phase(directory):
    load_recipe(directory)
    path = core._safe(directory, core.MANIFEST)
    if not os.path.exists(path):
        return 'draft'
    checked = verify(directory)
    if not checked['ok']:
        raise ClaimError('claim identity mismatch')
    return 'signed' if _signed(directory, read_manifest(directory)) else 'sealed'


def _source_map(source, name, mapping):
    if mapping and name in mapping:
        path = os.fspath(mapping[name])
        core._hash_file(path)
        return path
    return core._safe(source, name)


def _materialize(source, room, recipe, *, generated=False, produce_from=None,
                 input_from=None):
    os.makedirs(room, exist_ok=True)
    recipe_name = os.path.basename(_recipe.recipe_path(source))
    target = core._safe(room, recipe_name)
    if recipe['claim'].get('format', 1) >= 3:
        with open(target, 'w', encoding='utf-8') as out:
            out.write(_build._room_recipe(recipe))
    else:
        core._copy_into(_recipe.recipe_path(source), target)
    for name in _recipe._inputs(recipe, source):
        core._copy_into(_source_map(source, name, input_from), core._safe(room, name))
    for step in _recipe._steps(recipe):
        name = step['output']
        klass = step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned')
        if klass == 'generated':
            src = _source_map(source, name, produce_from) if produce_from and name in produce_from else core._safe(source, name)
            if (generated or produce_from and name in produce_from) and os.path.exists(src):
                core._copy_into(src, core._safe(room, name))
        elif step['kind'] != 'gate':
            core._copy_into(core._safe(source, name), core._safe(room, name))


def _judge(source, room, recipe):
    missing = preflight(recipe)
    furnished = None
    if not missing:
        try:
            previous = os.getcwd()
            try:
                os.chdir(room)
                furnished = _run.furnish(room, recipe)
            finally:
                os.chdir(previous)
        except ClaimError as exc:
            missing = [str(exc)]
    rows = []
    for step in _recipe.gates(recipe):
        name = step['output']
        if missing:
            result = {'status': 'environment', 'stderr': ', '.join(missing), 'quarantine': None}
        else:
            env = {}
            if furnished:
                env['PATH'] = os.path.join(furnished, 'bin') + os.pathsep + os.environ.get('PATH', os.defpath)
            result = run_gate(step['run'], room, recipe, env)
        status = result['status']
        if status == 'ok':
            source_pin = core._safe(source, name)
            if os.path.exists(source_pin):
                try:
                    status = 'ok' if core._hash_file(source_pin) == core._hash_file(core._safe(room, name)) else 'mismatch'
                except ClaimError:
                    status = 'mismatch'
        rows.append({'output': name, 'status': status, 'quarantine': result['quarantine'],
                     'stderr': result.get('stderr', '')})
        if not missing:
            ledger(room, {'event': 'gate', 'gate': name, 'status': status,
                          'quarantine': result['quarantine'], 'seconds': result.get('seconds', 0)})
    return rows, missing


def audit(directory, *, produce_from=None, **_):
    checked = verify(directory)
    recipe = load_recipe(directory)
    if not checked['ok']:
        return {'ok': False, 'root': checked['root'], 'gates': [], 'verdict': 'identity mismatch'}
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        _materialize(directory, room, recipe, generated=True, produce_from=produce_from)
        rows, missing = _judge(directory, room, recipe)
    ok = all(row['status'] == 'ok' for row in rows)
    return {'ok': ok, 'name': recipe['claim']['name'], 'root': checked['root'],
            'gates': rows, 'environment': missing,
            'verdict': 'earned' if ok else 'carried or broken'}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    if os.path.exists(core._safe(directory, core.MANIFEST)):
        checked = verify(directory)
        if not checked['ok']:
            raise ClaimError('source claim identity mismatch')
    recipe = load_recipe(directory)
    missing = preflight(recipe)
    if missing:
        raise ClaimError('environment missing: ' + ', '.join(missing))
    if os.path.exists(into) and os.listdir(into):
        raise ClaimError('rebuild target is not empty')
    into = os.path.abspath(into)
    _materialize(directory, into, recipe, produce_from=produce_from, input_from=input_from)
    recipe_name = os.path.basename(_recipe.recipe_path(into))
    frozen = {recipe_name: core._hash_file(core._safe(into, recipe_name))}
    frozen.update({name: core._hash_file(core._safe(into, name)) for name in _recipe._inputs(recipe, into)})
    ledger(into, {'event': 'environment', 'python': sys.version.split()[0],
                  'platform': sys.platform, 'quarantine': _run.sandbox_backend()})
    for step in _recipe.produces(recipe):
        if step.get('class', 'generated') != 'generated' or 'from' in step:
            continue
        name = step['output']
        if produce_from and name in produce_from:
            ledger(into, {'event': 'reuse', 'output': name})
            continue
        outputs = _recipe.generated_outputs(recipe)
        extra = {core._ENV_CLAIM: recipe['claim']['name'],
                 core._ENV_OUTPUT: core._safe(into, name),
                 core._ENV_OUTPUTS: json.dumps(outputs),
                 core._ENV_USAGE: core._safe(into, core.USAGE)}
        if guidance:
            extra[core._ENV_REQUEST] = step.get('guidance', step.get('request', ''))
        if producer_env:
            extra.update(producer_env)
        env = _run._scrub_env(extra=extra)
        if 'HOME' in os.environ:
            env['HOME'] = os.environ['HOME']
        result = _run._run(['/bin/sh', '-c', producer], into, env, core.PRODUCER_TIMEOUT)
        event = {'event': 'producer', 'output': name, 'calls': 1,
                 'seconds': result['seconds'], 'status': result['status'],
                 'quarantine': _run.sandbox_backend(), 'blind': True}
        for key, variable in (('vendor', core._ENV_VENDOR), ('model', core._ENV_MODEL)):
            if os.environ.get(variable):
                event[key] = os.environ[variable]
        try:
            with open(core._safe(into, core.USAGE), encoding='utf-8') as stream:
                usage = json.load(stream)
            if isinstance(usage, dict):
                for key in ('usd', 'tokens', 'calls'):
                    if type(usage.get(key)) in (int, float) and usage[key] >= 0:
                        event[key] = usage[key]
        except (OSError, ValueError, ClaimError):
            pass
        ledger(into, event)
        if result['status'] != 'ok':
            raise ClaimError(f"producer failed for {name}: {result['stderr']}")
    for name, digest in frozen.items():
        if core._hash_file(core._safe(into, name)) != digest:
            raise ClaimError(f'producer rewrote pinned bytes: {name}')
    rows, missing = _judge(directory, into, recipe)
    if missing:
        raise ClaimError('environment missing: ' + ', '.join(missing))
    if not all(row['status'] == 'ok' for row in rows):
        raise ClaimError(f'rebuild gates did not reproduce: {rows}')
    manifest = seal(into)
    return {'root': manifest['root'], 'name': manifest['name'], 'gates': rows,
            'quarantine': rows[0]['quarantine'] if rows else _run.sandbox_backend(),
            'build_digest': build_digest(into)}


def gate_deciders(command):
    parts = re.findall(r'[^\s;&|]+', command)
    result = []
    for i, part in enumerate(parts):
        if part in ('python', 'python3', 'pytest', 'py.test'):
            if i + 2 < len(parts) and parts[i+1] == '-m':
                if parts[i+2] == 'pytest':
                    for p in parts[i+3:]:
                        if p in ('printf', '>', '<'):
                            break
                        if not p.startswith('-'):
                            result.append(p)
            elif i + 1 < len(parts) and not parts[i+1].startswith('-'):
                result.append(parts[i+1])
        elif part.startswith('./'):
            result.append(part[2:])
    return result


def vacuous_gates(recipe):
    generated = set(_recipe.generated_outputs(recipe))
    pinned = set(recipe.get('claim', {}).get('inputs', []))
    bad = []
    for step in _recipe.gates(recipe):
        deciders = gate_deciders(step['run'])
        if deciders and all(d in generated and d not in pinned for d in deciders):
            bad.append(step['output'])
    return bad


def mutation_score(directory, *, max_mutants=core.MUTANT_CEILING):
    recipe = load_recipe(directory)
    mutations = []
    for step in _recipe.produces(recipe):
        name = step['output']
        if not name.endswith('.py') or step.get('class', 'generated') != 'generated':
            continue
        path = core._safe(directory, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8') as stream:
            source = stream.read()
        for changed in _cross._mutants(source):
            mutations.append((name, changed))
    seed = verify(directory)['root']
    mutations = _cross._mutant_order(mutations, seed)[:max_mutants]
    survivors = []
    for index, (name, changed) in enumerate(mutations):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as room:
            _materialize(directory, room, recipe, generated=True)
            with open(core._safe(room, name), 'w', encoding='utf-8') as stream:
                stream.write(changed)
            rows, _ = _judge(directory, room, recipe)
            if all(row['status'] == 'ok' for row in rows):
                survivors.append(index)
    count = len(mutations)
    result = {'mutants': count, 'survivors': survivors,
              'rate': (count - len(survivors)) / count if count else 0.0}
    core._write_json(core._safe(directory, core.MUTATION_RESIDUE), result)
    return result


crosscheck = _cross.crosscheck
record_proof = _cross.record_proof
