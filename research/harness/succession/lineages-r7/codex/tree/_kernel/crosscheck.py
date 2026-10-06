"""Compare live and frozen machines, and measure the teeth of their gates."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path

from . import attest, core, identity, recipe, run, seal

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'+': '-', '-': '+', '*': '//', '//': '*'}
_OP_KIND = {'+': 'arithmetic', '-': 'arithmetic', '*': 'arithmetic'}
_STRING_LITERAL = re.compile(r'''(?P<quote>['"])(?P<value>.*?)(?P=quote)''')
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}


def _docstring_spans(source):
    return []


def _draw_order(items, seed):
    return sorted(items, key=lambda item: hashlib.sha256((seed + repr(item)).encode()).hexdigest())


def _edit(source, start, end, replacement):
    return source[:start] + replacement + source[end:]


def _label(value):
    return str(value)


def _machine(path):
    if os.path.isdir(path):
        verified = seal.verify(path)
        claim = recipe.load_recipe(path)['claim']
        from .. import kernel
        audited = kernel.audit(path)
        return {'root': verified['root'], 'verified': verified['ok'],
                'build_digest': identity.build_digest(path),
                'audited': audited['ok'], 'cost': run.cost(path),
                'claim': {k: claim[k] for k in ('tolerance', 'envelope', 'mutation_floor') if k in claim},
                'gates': audited['gates'], 'version': 2, 'record': False}
    doc = attest.record_read(path)
    return {'root': doc['root'], 'verified': True,
            'build_digest': doc['build_digest'],
            'audited': all(g['status'] == 'ok' for g in doc['gates']),
            'cost': doc.get('cost'), 'claim': doc.get('claim', {}),
            'gates': doc['gates'], 'version': doc['record'], 'record': True}


def _mutant_order(items, root):
    return _draw_order(items, root)


def _mutants(source):
    return _structural_mutants(source) + _token_mutants(source)


def _named(value):
    return getattr(value, 'name', str(value))


def _node_span(node):
    return (getattr(node, 'lineno', 0), getattr(node, 'col_offset', 0))


def _span_text(source, span):
    return source


def _splice(source, start, end, replacement):
    return _edit(source, start, end, replacement)


def _structural_mutants(source):
    mutants = []
    lines = source.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if re.search(r'\breturn\b', line):
            for replacement in ('return 0', 'return -1', 'return None'):
                new = lines.copy()
                new[i] = re.sub(r'\breturn\b.*', replacement, line.rstrip('\n')) + '\n'
                mutants.append(''.join(new))
    return mutants


def _token_mutants(source):
    mutants = []
    for old, new in [('>', '<'), ('<', '>'), ('+', '-'), ('-', '+'), ('==', '!='), ('abs(', '(')]:
        if old in source:
            mutants.append(source.replace(old, new, 1))
    return mutants


def gate_deciders(command):
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    if '-m' in tokens:
        i = tokens.index('-m')
        if i + 1 < len(tokens) and tokens[i + 1] in ('pytest', 'unittest'):
            args = []
            for item in tokens[i + 2:]:
                if item in _OPERATORS:
                    break
                if not item.startswith('-'):
                    args.append(item)
            return args
    deciders = []
    for i, token in enumerate(tokens):
        if token.startswith('./'):
            deciders.append(token[2:])
        elif i and tokens[i - 1] in _INTERPRETERS and not token.startswith('-'):
            deciders.append(token)
    return deciders


def vacuous_gates(claim_recipe):
    inputs = set(claim_recipe.get('claim', {}).get('inputs', []))
    generated = set(recipe.generated_outputs(claim_recipe))
    return [step['output'] for step in recipe.gates(claim_recipe)
            if (deciders := gate_deciders(step['run']))
            and all(d in generated and d not in inputs for d in deciders)]


def mutation_score(directory, *, max_mutants=core.MUTANT_CEILING):
    from .. import kernel
    claim = recipe.load_recipe(directory)
    candidates = []
    for name in recipe.generated_outputs(claim):
        path = core._safe(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            source = Path(path).read_text()
        except UnicodeError:
            continue
        for variant in dict.fromkeys(_mutants(source)):
            if variant != source:
                candidates.append((name, variant))
    chosen = _mutant_order(candidates, seal.verify(directory)['root'])[:max_mutants]
    killed = 0
    survivors = []
    for i, (name, content) in enumerate(chosen):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as temp:
            path = os.path.join(temp, os.path.basename(name))
            Path(path).write_text(content)
            try:
                result = kernel.audit(directory, produce_from={name: path})
                alive = result['ok']
            except core.ClaimError:
                alive = False
        if alive:
            survivors.append(i)
        else:
            killed += 1
    rate = killed / len(chosen) if chosen else 0.0
    result = {'mutants': len(chosen), 'killed': killed, 'survivors': survivors, 'rate': rate}
    core._write_json(core._safe(directory, core.MUTATION_RESIDUE), result)
    return result


def independence(directory):
    if not os.path.isdir(directory):
        doc = attest.record_read(directory)
        data = doc.get('producer', {})
    else:
        data = {}
        for event in run.ledger_events(directory):
            if event.get('event') == 'producer':
                data = event
    return {'vendor': data.get('vendor'), 'model': data.get('model'),
            'blind': data.get('blind', False)}


def crosscheck(m1, m2, m3, *, mutants=None):
    paths = [os.fspath(x) for x in (m1, m2, m3)]
    if len({os.path.realpath(x) for x in paths}) != 3:
        raise core.ClaimError('three distinct machines required')
    machines = [_machine(x) for x in paths]
    roots = dict(zip(('M1', 'M2', 'M3'), (x['root'] for x in machines)))
    audited = dict(zip(('M1', 'M2', 'M3'), (x['audited'] and x['verified'] for x in machines)))
    equivalence = len(set(roots.values())) == 1
    reuse = machines[0]['build_digest'] == machines[1]['build_digest']
    first, third = machines[0]['cost'], machines[2]['cost']
    unit = next((key for key in core.COST_LADDER if first and third and key in first and key in third), None)
    comparable = run._in_band(first[unit], third[unit], machines[0]['claim'].get('tolerance', core.TOLERANCE)) if unit else None
    cost = {'M1': first, 'M3': third, 'unit': unit, 'comparable': comparable, 'envelope': {}}
    rejected, incomplete = [], []
    if not equivalence:
        rejected.append('root')
    if not reuse:
        rejected.append('reuse')
    if not all(audited.values()):
        rejected.append('audit')
    declared = machines[0]['claim']
    if machines[0]['version'] == 1:
        incomplete.append('declared conditions')
    if 'tolerance' in declared and comparable is False:
        rejected.append('tolerance')
    for key, ceiling in declared.get('envelope', {}).items():
        measured = third.get(key) if third else None
        within = measured <= ceiling if measured is not None else None
        cost['envelope'][key] = {'ceiling': ceiling, 'measured': measured, 'within': within}
        if within is False:
            rejected.append('envelope ' + key)
        elif within is None:
            incomplete.append('envelope ' + key)
    score = None
    if 'mutation_floor' in declared:
        if mutants is None:
            incomplete.append('mutation floor')
        elif not os.path.isdir(m1):
            incomplete.append('mutation floor')
        else:
            score = mutation_score(m1, max_mutants=mutants)
            score['ok'] = score['rate'] >= declared['mutation_floor']
            if not score['ok']:
                rejected.append('mutation floor')
    vendor = independence(m3)
    if vendor['vendor']:
        ind = f"declared: {vendor['vendor']}/{vendor['model']}, blind workspace; not proven"
    else:
        ind = 'unestablished: producer independence not proven'
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied': verdict == 'accept', 'verdict': verdict,
            'rejected': rejected, 'incomplete': incomplete,
            'equivalence': equivalence, 'reuse': reuse, 'audited': audited,
            'roots': roots, 'cost': cost, 'mutation_score': score,
            'independence': ind}


def record_proof(m1, m2, m3, *, mutants=None):
    if not os.path.isdir(m1):
        raise core.ClaimError('M1 proof requires a directory')
    records = []
    for path in (m2, m3):
        if not os.path.isdir(path):
            anchor = os.environ.get(core._ENV_SIGNERS)
            signer = attest.record_signer(path, anchor) if anchor else None
            if not signer:
                raise core.ClaimError('record is not anchored by a trusted signer')
            records.append({'digest': attest.record_digest(attest.record_read(path)), 'signer': signer})
    result = crosscheck(m1, m2, m3, mutants=mutants)
    result['proof_recorded'] = result['satisfied']
    if result['satisfied']:
        manifest = seal.read_manifest(m1)
        manifest['proof'] = {'kind': 'crosscheck', 'roots': result['roots'], 'records': records}
        core._write_json(core._safe(m1, core.MANIFEST), manifest)
    return result
