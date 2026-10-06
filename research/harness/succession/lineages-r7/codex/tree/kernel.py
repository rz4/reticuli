"""Public claim kernel: identity, execution, audit, and crosscheck."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

from ._kernel import attest, core, crosscheck as comparison, identity, recipe, run, seal as seal_module

ClaimError = core.ClaimError
NAMESPACE = core.NAMESPACE
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
STORE = core.STORE
MANIFEST = core.MANIFEST
RECIPE = core.RECIPE
LEDGER = core.LEDGER
SIGN_DIR = core.SIGN_DIR
_JAILED = core._JAILED

_strict_load_recipe = recipe.load_recipe


def load_recipe(directory):
    try:
        doc = _strict_load_recipe(directory)
    except ClaimError as error:
        # An untrusted generated path is allowed at parse and seal time; audit
        # refuses it when it would actually copy the output into a room.
        if 'symlink in claim path' not in str(error):
            raise
        with open(recipe.recipe_path(directory), 'rb') as source:
            doc = tomllib.load(source)
        generated = {step.get('output') for step in doc.get('step', [])
                     if step.get('kind') == 'produce' and step.get('class', 'generated') == 'generated'}
        for name in recipe._inputs(doc, directory):
            core._safe(directory, name)
        for step in doc.get('step', []):
            if step.get('output') not in generated:
                core._safe(directory, step.get('output'))
    envelope = doc.get('claim', {}).get('envelope')
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError('envelope must be a nonempty table')
        for key, value in envelope.items():
            if key not in core.COST_KEYS or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ClaimError('invalid envelope ceiling')
    return doc


recipe.load_recipe = load_recipe
root = identity.root
build_digest = identity.build_digest
seal = seal_module.seal
verify = seal_module.verify
read_manifest = seal_module.read_manifest
ledger = run.ledger
ledger_events = run.ledger_events
cost = run.cost
preflight = run.preflight
run_gate = run.run_gate
record_validate = attest.record_validate
record_digest = attest.record_digest
gate_deciders = comparison.gate_deciders
vacuous_gates = comparison.vacuous_gates
mutation_score = comparison.mutation_score
crosscheck = comparison.crosscheck
record_proof = comparison.record_proof
independence = comparison.independence
_hash_file = core._hash_file


def record_read(path):
    doc = attest.record_read(path)
    if Path(path).read_bytes() != attest.record_canonical(doc):
        raise ClaimError('record has noncanonical bytes')
    return doc


def sandbox(command, directory):
    return (command, run.sandbox_backend())


def sign_node(root_value, digest, children):
    data = json.dumps([root_value, digest, sorted(children)], sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def _recipe_for_room(source, room, claim_recipe):
    """At format 3, gates see the guidance-free recipe named by identity."""
    source_path = recipe.recipe_path(source)
    target = core._safe(room, os.path.basename(source_path))
    text = Path(source_path).read_text()
    if claim_recipe['claim'].get('format', 1) >= 3:
        chunks = text.split('[[step]]')
        text = chunks[0] + ''.join('[[step]]' + ''.join(
            line for line in chunk.splitlines(keepends=True)
            if not line.lstrip().startswith(('guidance =', 'request =')))
            for chunk in chunks[1:])
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_text(text)


def _copy_declared(source, room, claim_recipe, *, generated=False,
                   produce_from=None, input_from=None):
    os.makedirs(room, exist_ok=True)
    _recipe_for_room(source, room, claim_recipe)
    for name in recipe._inputs(claim_recipe, source):
        supplied = (input_from or {}).get(name, core._safe(source, name))
        core._copy_into(supplied, core._safe(room, name))
    for step in recipe.produces(claim_recipe):
        name = step['output']
        supplied = (produce_from or {}).get(name)
        if supplied is None and (generated or step.get('class', 'generated') != 'generated'):
            supplied = core._safe(source, name)
        if supplied is not None and os.path.lexists(supplied):
            if supplied == core._safe(source, name):
                core._hash_file(supplied)
            core._copy_into(supplied, core._safe(room, name))


def _gate_rows(source, room, claim_recipe):
    missing = run.preflight(claim_recipe)
    furnished = None
    if not missing:
        try:
            previous = os.getcwd()
            try:
                os.chdir(room)
                furnished = run.furnish(room, claim_recipe)
            finally:
                os.chdir(previous)
        except ClaimError as error:
            missing = [str(error)]
    rows = []
    for step in recipe.gates(claim_recipe):
        name = step['output']
        if missing:
            rows.append({'output': name, 'status': 'environment',
                         'quarantine': None, 'error': ', '.join(missing)})
            continue
        env = {'PATH': os.path.join(furnished, 'bin') + os.pathsep + os.environ.get('PATH', '')} if furnished else None
        result = run.run_gate(step['run'], room, claim_recipe, env=env)
        status = result['status']
        if status == 'ok':
            try:
                status = 'ok' if core._hash_file(core._safe(source, name)) == core._hash_file(core._safe(room, name)) else 'mismatch'
            except ClaimError:
                status = 'mismatch'
        rows.append({'output': name, 'status': status,
                     'quarantine': result['quarantine'],
                     'stdout': result.get('stdout', ''), 'stderr': result.get('stderr', '')})
    return rows, missing


def audit(directory, *, shallow=False, produce_from=None):
    checked = verify(directory)
    if not checked['ok']:
        return {'ok': False, 'root': checked['root'], 'gates': [],
                'environment': [], 'verdict': 'identity mismatch'}
    claim_recipe = recipe.load_recipe(directory)
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        _copy_declared(directory, room, claim_recipe, generated=True,
                       produce_from=produce_from)
        rows, missing = _gate_rows(directory, room, claim_recipe)
    good = all(row['status'] == 'ok' for row in rows)
    return {'ok': good, 'root': checked['root'], 'gates': rows,
            'environment': missing, 'verdict': 'earned' if good else 'carried or broken'}


def rebuild(directory, producer, into, *, produce_from=None, input_from=None,
            guidance=True, producer_env=None):
    source = os.path.abspath(directory)
    target = os.path.abspath(into)
    claim_recipe = recipe.load_recipe(source)
    try:
        sealed = verify(source)
    except ClaimError:
        sealed = None
    if sealed and not sealed['ok']:
        raise ClaimError('cannot rebuild a claim with mismatched identity')
    if os.path.exists(target) and os.listdir(target):
        raise ClaimError('rebuild target is not empty')
    _copy_declared(source, target, claim_recipe, produce_from=produce_from,
                   input_from=input_from)
    for name, supplied in (produce_from or {}).items():
        run.ledger(target, {'event': 'reuse', 'output': name, 'source': os.fspath(supplied)})
    recipe_name = os.path.basename(recipe.recipe_path(source))
    watches = [recipe_name] + recipe._inputs(claim_recipe, target)
    before = {name: core._hash_file(core._safe(target, name)) for name in watches}
    missing = run.preflight(claim_recipe)
    if missing:
        raise ClaimError('environment missing: ' + ', '.join(missing))
    outputs = recipe.generated_outputs(claim_recipe)
    env = {key: os.environ[key] for key in core._KEEP_ENV if key in os.environ}
    env.update({str(k): str(v) for k, v in (producer_env or {}).items()})
    env[core._ENV_CLAIM] = claim_recipe['claim']['name']
    env[core._ENV_OUTPUTS] = os.pathsep.join(outputs)
    env[core._ENV_OUTPUT] = outputs[0] if outputs else ''
    usage_path = core._safe(target, core.USAGE)
    os.makedirs(os.path.dirname(usage_path), exist_ok=True)
    env[core._ENV_USAGE] = usage_path
    if guidance:
        hints = [str(s.get('guidance', s.get('request', ''))) for s in recipe.produces(claim_recipe)]
        env[core._ENV_REQUEST] = '\n'.join(h for h in hints if h)
    else:
        env.pop(core._ENV_REQUEST, None)
    start = time.monotonic()
    produced = run._run([core._SHELL, '-c', producer], target, env, core.PRODUCER_TIMEOUT)
    seconds = time.monotonic() - start
    if produced['status'] != 'ok':
        raise ClaimError('producer ' + produced['status'] + ': ' + produced.get('stderr', ''))
    if any(core._hash_file(core._safe(target, name)) != old for name, old in before.items()):
        raise ClaimError('producer changed pinned input or recipe')
    rows, missing = _gate_rows(source, target, claim_recipe)
    if any(row['status'] not in ('ok', 'mismatch') for row in rows):
        raise ClaimError('rebuilt gates did not pass: ' + repr(rows))
    # The source verdict may be absent in an unsealed draft. For a sealed
    # claim, every gate must reproduce the pinned bytes.
    if sealed and any(row['status'] != 'ok' for row in rows):
        raise ClaimError('rebuilt gates did not reproduce: ' + repr(rows))
    manifest = seal(target)
    if sealed and input_from is None and manifest['root'] != sealed['root']:
        raise ClaimError('rebuilt claim root differs from source')
    backend = run.sandbox_backend()
    run.ledger(target, {'event': 'environment', 'python': os.sys.version.split()[0],
                        'platform': os.sys.platform, 'quarantine': backend})
    for row in rows:
        run.ledger(target, {'event': 'gate', 'output': row['output'],
                            'status': row['status'], 'quarantine': row['quarantine']})
    usage = {}
    try:
        raw = json.loads(Path(usage_path).read_text())
        if isinstance(raw, dict):
            usage = {k: v for k, v in raw.items() if k in ('usd', 'tokens', 'calls')
                     and isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0}
    except (OSError, ValueError):
        pass
    usage.setdefault('calls', 1)
    run.ledger(target, {'event': 'producer', 'seconds': seconds, 'blind': True,
                        'vendor': os.environ.get(core._ENV_VENDOR),
                        'model': os.environ.get(core._ENV_MODEL), **usage})
    return {'root': manifest['root'], 'gates': rows, 'quarantine': backend,
            'build_digest': build_digest(target)}


def phase(directory):
    manifest_path = core._safe(directory, core.MANIFEST)
    if not os.path.exists(manifest_path):
        return 'draft'
    checked = verify(directory)
    if not checked['ok']:
        return 'sealed'
    manifest = read_manifest(directory)
    if not manifest.get('proof'):
        return 'sealed'
    anchor = os.environ.get(core._ENV_SIGNERS)
    if not anchor:
        return 'sealed'
    sign_dir = core._safe(directory, core.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return 'sealed'
    for statement in Path(sign_dir).glob('*.sign.json'):
        packet_path = statement.with_name(statement.name.replace('.sign.json', '.packet.json'))
        try:
            packet = json.loads(packet_path.read_text())
            stmt = json.loads(statement.read_text())
            digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            if packet != {'root': checked['root'], 'build_digest': build_digest(directory),
                          'proof': manifest['proof']}:
                continue
            if stmt.get('packet_digest') != digest or stmt.get('root') != checked['root']:
                continue
            signed = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                                     '-I', stmt['identity'], '-n', SIGN_NAMESPACE,
                                     '-s', str(statement) + '.sig'],
                                    input=statement.read_bytes(), capture_output=True,
                                    timeout=15, check=False)
            if signed.returncode == 0:
                return 'signed'
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            pass
    return 'sealed'
