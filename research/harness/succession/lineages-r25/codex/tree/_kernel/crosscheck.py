"""Compare three claim realizations and measure their generated-code tests."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shlex
import tempfile

from . import attest, core, identity, recipe, run, seal

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = (('+', '-'), ('-', '+'), ('*', '/'), ('/', '*'))
_OP_ALTS = {'>': '<', '<': '>', '>=': '<=', '<=': '>=', '==': '!=', '!=': '=='}
_OP_KIND = {ast.Gt: ast.Lt, ast.Lt: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
_STRING_LITERAL = re.compile(r"(['\"])(.*?)\1")
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}


def _named(path):
    return os.path.basename(os.fspath(path))


def _machine(source):
    path = os.fspath(source)
    if os.path.isfile(path):
        doc = attest.record_read(path)
        return {'root': doc['root'], 'digest': doc['build_digest'],
                'audited': all(g['status'] == 'ok' for g in doc['gates']),
                'cost': doc.get('cost'), 'claim': doc.get('claim'),
                'version': doc['record'], 'record': True, 'doc': doc}
    checked = seal.verify(path)
    from reticuli import kernel
    audit = kernel.audit(path)
    return {'root': checked['root'], 'digest': identity.build_digest(path),
            'audited': checked['ok'] and audit['ok'], 'cost': run.cost(path),
            'claim': recipe.load_recipe(path)['claim'], 'version': 2,
            'record': False}


def _label(source):
    return 'record' if os.path.isfile(os.fspath(source)) else 'directory'


def _draw_order(root, items):
    return sorted(items, key=lambda x: hashlib.sha256((root + repr(x)).encode()).hexdigest())


def _mutant_order(root, items):
    return _draw_order(root, items)


def _node_span(node):
    return (getattr(node, 'lineno', 0), getattr(node, 'col_offset', 0),
            getattr(node, 'end_lineno', 0), getattr(node, 'end_col_offset', 0))


def _span_text(source, span):
    lines = source.splitlines(True)
    a, b, c, d = span
    if not a or not c:
        return ''
    return ''.join(lines[a-1:c])[b:d] if a == c else lines[a-1][b:] + ''.join(lines[a:c-1]) + lines[c-1][:d]


def _splice(source, span, replacement):
    lines = source.splitlines(True)
    a, b, c, d = span
    return ''.join(lines[:a-1]) + lines[a-1][:b] + replacement + lines[c-1][d:] + ''.join(lines[c:])


def _edit(source, old, new):
    return source.replace(old, new, 1)


def _docstring_spans(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [_node_span(n.value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str)]


def _structural_mutants(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    edits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            old = _span_text(source, _node_span(node))
            for a, b in _OP_ALTS.items():
                if a in old:
                    edits.append(_splice(source, _node_span(node), old.replace(a, b, 1)))
                    break
        if isinstance(node, ast.BinOp):
            old = _span_text(source, _node_span(node))
            for a, b in _ARITHMETIC:
                if a in old:
                    edits.append(_splice(source, _node_span(node), old.replace(a, b, 1)))
                    break
    return edits


def _token_mutants(source):
    return [_edit(source, a, b) for a, b in _WORD_ALTS.items() if a in source]


def _mutants(source):
    return list(dict.fromkeys(x for x in _structural_mutants(source) + _token_mutants(source) if x != source))


def gate_deciders(command):
    try:
        words = shlex.split(command.replace('&&', ' ').replace(';', ' '))
    except ValueError:
        return []
    out = []
    for i, word in enumerate(words):
        base = os.path.basename(word)
        if word.startswith('./'):
            out.append(word[2:])
        elif base in _INTERPRETERS:
            j = i + 1
            while j < len(words) and words[j].startswith('-'):
                if words[j] in _SKIP_VALUE:
                    j += 2
                else:
                    j += 1
            if j < len(words) and words[j] not in ('>', '>>'):
                out.append(words[j])
    return list(dict.fromkeys(out))


def vacuous_gates(parsed):
    generated = set(recipe.generated_outputs(parsed))
    pinned = set(parsed.get('claim', {}).get('inputs', []))
    bad = []
    for gate in recipe.gates(parsed):
        deciders = gate_deciders(gate['run'])
        if deciders and all(d in generated and d not in pinned for d in deciders):
            bad.append(gate['output'])
    return bad


def mutation_score(directory, max_mutants=32):
    from reticuli import kernel
    parsed = recipe.load_recipe(directory)
    root = seal.verify(directory)['root']
    choices = []
    for name in recipe.generated_outputs(parsed):
        path = core._safe(directory, name)
        if not os.path.isfile(path) or not name.endswith('.py'):
            continue
        with open(path, encoding='utf-8') as f:
            original = f.read()
        choices.extend((name, candidate) for candidate in _mutants(original))
    choices = _mutant_order(root, choices)[:max_mutants]
    survivors = []
    for number, (name, content) in enumerate(choices):
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.py', delete=False) as f:
            f.write(content)
            replacement = f.name
        try:
            if kernel.audit(directory, produce_from={name: replacement})['ok']:
                survivors.append(number)
        finally:
            os.unlink(replacement)
    count = len(choices)
    rate = (count - len(survivors)) / count if count else 0.0
    report = {'mutants': count, 'survivors': survivors, 'rate': rate}
    core._write_json(os.path.join(directory, core.MUTATION_RESIDUE), report)
    return report


def independence(directory):
    if os.path.isfile(os.fspath(directory)):
        return attest.record_read(directory).get('producer', {})
    for event in run.ledger_events(directory):
        if event.get('event') == 'producer':
            return {key: event[key] for key in ('vendor', 'model', 'blind') if key in event}
    return {}


def crosscheck(m1, m2, m3, *, mutants=0):
    paths = [os.path.realpath(os.fspath(x)) for x in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise core.ClaimError('three distinct machine paths are required')
    machines = [_machine(x) for x in (m1, m2, m3)]
    roots = dict(zip(('M1', 'M2', 'M3'), (m['root'] for m in machines)))
    audited = dict(zip(('M1', 'M2', 'M3'), (m['audited'] for m in machines)))
    equivalence = len(set(roots.values())) == 1
    reuse = machines[0]['digest'] == machines[1]['digest']
    claim = machines[0]['claim'] or {}
    c1, c3 = machines[0]['cost'] or {}, machines[2]['cost'] or {}
    unit = next((u for u in core.COST_LADDER if u in c1 and u in c3), None)
    tolerance = claim.get('tolerance', core.TOLERANCE)
    comparable = run._in_band(c1[unit], c3[unit], tolerance) if unit else None
    cost = {'comparable': comparable, 'unit': unit, 'M1': c1 or None, 'M3': c3 or None, 'envelope': {}}
    rejected, incomplete = [], []
    if not equivalence: rejected.append('root')
    if not reuse: rejected.append('reuse')
    for label, ok in audited.items():
        if not ok: rejected.append('audit ' + label)
    if 'tolerance' in claim and comparable is False: rejected.append('tolerance')
    for unit, limit in claim.get('envelope', {}).items():
        measured = c3.get(unit)
        within = None if measured is None else measured <= limit
        cost['envelope'][unit] = {'limit': limit, 'measured': measured, 'within': within}
        if within is False: rejected.append('envelope ' + unit)
        if within is None: incomplete.append('envelope ' + unit)
    score = None
    if 'mutation_floor' in claim:
        if mutants:
            if machines[2]['record']:
                incomplete.append('mutation floor')
            else:
                score = mutation_score(m3, mutants)
                score['ok'] = score['rate'] >= claim['mutation_floor']
                if not score['ok']: rejected.append('mutation floor')
        else:
            incomplete.append('mutation floor')
    if machines[0]['version'] == 1:
        incomplete.append('record v1 obligations')
    declared = independence(m3)
    if declared.get('vendor') and declared.get('model'):
        ind = f"declared: {declared['vendor']}/{declared['model']}, " + ('blind workspace' if declared.get('blind') else 'workspace unknown') + '; not proven'
    else:
        ind = 'unestablished (not proven)'
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied': verdict == 'accept', 'verdict': verdict,
            'rejected': rejected, 'incomplete': incomplete,
            'roots': roots, 'audited': audited, 'equivalence': equivalence,
            'reuse': reuse, 'cost': cost, 'mutation_score': score,
            'independence': ind}
