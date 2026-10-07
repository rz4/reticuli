"""Three-machine comparison and deterministic mutation probes."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import tempfile

from . import core, identity, recipe, run

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = (('+', '-'), ('-', '+'), ('*', '/'), ('/', '*'))
_OP_ALTS = {'>': '<', '<': '>', '>=': '<=', '<=': '>=', '==': '!=', '!=': '=='}
_OP_KIND = {'>': 'comparison', '<': 'comparison', '+': 'arithmetic', '-': 'arithmetic'}
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}
_STRING_LITERAL = re.compile(r'''(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')''')


def gate_deciders(command):
    """Find workspace programs invoked by a gate, including module test dirs."""
    try:
        words = shlex.split(command.replace('&&', ' ').replace('||', ' '))
    except ValueError:
        return []
    found = []
    for i, word in enumerate(words):
        if word.startswith('./'):
            found.append(word[2:])
        if word in _INTERPRETERS:
            tail = words[i + 1:]
            for j, part in enumerate(tail):
                if part == '-m' and j + 1 < len(tail):
                    continue
                if part.startswith('-'):
                    continue
                if part in _INTERPRETERS or part in ('pytest', 'unittest'):
                    continue
                if part.endswith(('.py', '.sh', '.js', '.rb')) or part in ('tests', 'test'):
                    found.append(part)
                    break
    return list(dict.fromkeys(found))


def vacuous_gates(parsed):
    inputs = set(parsed.get('claim', {}).get('inputs', []))
    generated = set(recipe.generated_outputs(parsed))
    result = []
    for gate in recipe.gates(parsed):
        deciders = gate_deciders(gate['run'])
        if deciders and all(x in generated and x not in inputs for x in deciders):
            result.append(gate['output'])
    return result


def _node_span(node):
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def _span_text(source, span):
    lines = source.splitlines(keepends=True)
    a, b, c, d = span
    return ''.join(lines[a - 1:c])[b:d] if a == c else ''.join([lines[a - 1][b:], *lines[a:c - 1], lines[c - 1][:d]])


def _splice(source, span, replacement):
    lines = source.splitlines(keepends=True)
    a, b, c, d = span
    return ''.join(lines[:a - 1]) + lines[a - 1][:b] + replacement + lines[c - 1][d:] + ''.join(lines[c:])


def _edit(source, old, new):
    return source.replace(old, new, 1)


def _label(name, number):
    return f'{name}:{number}'


def _named(items):
    return list(enumerate(items))


def _docstring_spans(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    spans = []
    for node in ast.walk(tree):
        body = getattr(node, 'body', [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            spans.append(_node_span(body[0]))
    return spans


def _structural_mutants(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    variants = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            span = _node_span(node)
            text = _span_text(source, span)
            for before, after in _OP_ALTS.items():
                changed = re.sub(r'(?<![<>=!])' + re.escape(before) + r'(?![=])', after, text, count=1)
                if changed != text:
                    variants.append(_splice(source, span, changed))
                    break
        elif isinstance(node, ast.Return) and node.value is not None:
            variants.append(_splice(source, _node_span(node.value), 'None'))
    return list(dict.fromkeys(v for v in variants if v != source))


def _token_mutants(source):
    variants = []
    for before, after in list(_OP_ALTS.items()) + list(_WORD_ALTS.items()):
        changed = re.sub(r'\b' + re.escape(before) + r'\b', after, source, count=1) if before.isalpha() else source.replace(before, after, 1)
        if changed != source:
            variants.append(changed)
    return list(dict.fromkeys(variants))


def _draw_order(count, seed):
    return sorted(range(count), key=lambda i: hashlib.sha256(f'{seed}:{i}'.encode()).digest())


def _mutant_order(items, seed):
    return [items[i] for i in _draw_order(len(items), seed)]


def _mutants(source):
    return list(dict.fromkeys(_structural_mutants(source) + _token_mutants(source)))


def _machine(leg):
    from reticuli import kernel
    if os.path.isfile(leg):
        doc = kernel.record_read(leg)
        return {'root': doc['root'], 'digest': doc['build_digest'],
                'audited': all(g['status'] == 'ok' for g in doc['gates']),
                'cost': doc.get('cost'), 'claim': doc.get('claim'),
                'producer': doc.get('producer'), 'record': doc}
    checked = kernel.verify(leg)
    audit = kernel.audit(leg)
    parsed = kernel.load_recipe(leg)
    return {'root': checked['root'], 'digest': kernel.build_digest(leg),
            'audited': checked['ok'] and audit['ok'], 'cost': kernel.cost(leg),
            'claim': parsed['claim'], 'producer': kernel.independence(leg),
            'record': None}


def mutation_score(directory, max_mutants=core.MUTANT_CEILING):
    from reticuli import kernel
    parsed = recipe.load_recipe(directory)
    seed = identity.root(parsed, directory)
    choices = []
    for name in recipe.generated_outputs(parsed):
        path = core._safe(directory, name)
        if not os.path.isfile(path) or not name.endswith('.py'):
            continue
        with open(path, encoding='utf-8') as f:
            source = f.read()
        choices.extend((name, variant) for variant in _mutants(source))
    choices = _mutant_order(choices, seed)[:max_mutants]
    survivors = []
    for index, (name, variant) in enumerate(choices):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as tmp:
            path = os.path.join(tmp, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(variant)
            try:
                if kernel.audit(directory, produce_from={name: path})['ok']:
                    survivors.append(index)
            except core.ClaimError:
                pass
    count = len(choices)
    result = {'mutants': count, 'survivors': survivors,
              'killed': count - len(survivors),
              'rate': (count - len(survivors)) / count if count else None}
    core._write_json(core._safe(directory, core.MUTATION_RESIDUE), result)
    return result


def crosscheck(m1, m2, m3, *, mutants=None):
    paths = [os.path.realpath(os.fspath(x)) for x in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise core.ClaimError('three distinct machines are required')
    machines = [_machine(x) for x in paths]
    roots = dict(zip(('M1', 'M2', 'M3'), (m['root'] for m in machines)))
    audited = dict(zip(('M1', 'M2', 'M3'), (m['audited'] for m in machines)))
    equivalence = len(set(roots.values())) == 1
    reuse = machines[0]['digest'] == machines[1]['digest']
    first, third = machines[0]['cost'], machines[2]['cost']
    obligations = machines[0]['claim']
    tolerance = (obligations or {}).get('tolerance', core.TOLERANCE)
    shared = next((key for key in core.COST_LADDER if first and third and key in first and key in third), None)
    comparable = run._in_band(first[shared], third[shared], tolerance) if shared else None
    cost = {'M1': first, 'M3': third, 'unit': shared, 'comparable': comparable, 'envelope': {}}
    rejected, incomplete = [], []
    if not equivalence: rejected.append('root')
    if not reuse: rejected.append('reuse')
    if not all(audited.values()): rejected.append('audit')
    if obligations is None:
        incomplete.append('declared conditions')
    else:
        if 'tolerance' in obligations and comparable is False:
            rejected.append('tolerance')
        for unit, ceiling in obligations.get('envelope', {}).items():
            amount = third.get(unit) if third else None
            within = amount <= ceiling if amount is not None else None
            cost['envelope'][unit] = {'measured': amount, 'ceiling': ceiling, 'within': within}
            if within is False: rejected.append('envelope ' + unit)
            if within is None: incomplete.append('envelope ' + unit)
    score = None
    if obligations and 'mutation_floor' in obligations:
        if mutants is None or os.path.isfile(paths[2]):
            incomplete.append('mutation floor')
        else:
            score = mutation_score(paths[2], max_mutants=mutants)
            score['ok'] = score['rate'] is not None and score['rate'] >= obligations['mutation_floor']
            if not score['ok']: rejected.append('mutation floor')
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    prod = machines[2]['producer'] or {}
    independence = ('declared: ' + str(prod.get('vendor')) + '/' + str(prod.get('model')) +
                    ', blind workspace (not proven)' if prod.get('vendor') and prod.get('model') and prod.get('blind')
                    else 'unestablished (not proven)')
    return {'satisfied': verdict == 'accept', 'verdict': verdict,
            'rejected': rejected, 'incomplete': incomplete,
            'roots': roots, 'equivalence': equivalence, 'reuse': reuse,
            'audited': audited, 'cost': cost, 'mutation_score': score,
            'independence': independence}
