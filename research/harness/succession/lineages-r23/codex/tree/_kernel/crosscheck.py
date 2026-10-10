"""Three-machine comparison and deterministic mutation probes."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import tempfile

from . import core, recipe as recipe_module, attest

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<', '<': '>', '>=': '<=', '<=': '>=', '==': '!=', '!=': '=='}
_OP_KIND = {k: 'comparison' for k in _OP_ALTS}
_STRING_LITERAL = re.compile(r'''(?P<quote>['"])(?:\\.|(?!\1).)*?\1''')
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}


def _named(value, name=None):
    return name or getattr(value, 'name', str(value))


def _label(path, index=0):
    return f'{path}:{index}'


def _draw_order(items, seed):
    return sorted(items, key=lambda item: hashlib.sha256((seed + repr(item)).encode()).hexdigest())


def _mutant_order(items, seed):
    return _draw_order(items, seed)


def _node_span(node):
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def _span_text(source, span):
    lines = source.splitlines(keepends=True)
    a, b, c, d = span
    if a == c:
        return lines[a-1][b:d]
    return lines[a-1][b:] + ''.join(lines[a:c-1]) + lines[c-1][:d]


def _splice(source, span, replacement):
    lines = source.splitlines(keepends=True)
    a, b, c, d = span
    return ''.join(lines[:a-1]) + lines[a-1][:b] + replacement + lines[c-1][d:] + ''.join(lines[c:])


def _edit(source, old, new):
    return source.replace(old, new, 1)


def _docstring_spans(tree):
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                spans.append(_node_span(first))
    return spans


def _structural_mutants(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                for kind, spelling in ((ast.Gt, '>'), (ast.Lt, '<'), (ast.GtE, '>='), (ast.LtE, '<='), (ast.Eq, '=='), (ast.NotEq, '!=')):
                    if isinstance(op, kind):
                        old = _span_text(source, _node_span(node))
                        new = old.replace(spelling, _OP_ALTS[spelling], 1)
                        if new != old:
                            found.append(_splice(source, _node_span(node), new))
                        break
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            old = _span_text(source, _node_span(node))
            op = '+' if isinstance(node.op, ast.Add) else '-'
            new = old.replace(op, '-' if op == '+' else '+', 1)
            if new != old:
                found.append(_splice(source, _node_span(node), new))
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            found.append(_splice(source, _node_span(node), str(node.value + 1)))
    return list(dict.fromkeys(found))


def _token_mutants(source):
    found = []
    for word, alt in _WORD_ALTS.items():
        m = re.search(r'\b' + word + r'\b', source)
        if m:
            found.append(source[:m.start()] + alt + source[m.end():])
    return found


def _mutants(source):
    return list(dict.fromkeys(_structural_mutants(source) + _token_mutants(source)))


def _machine(leg):
    from reticuli import kernel
    path = os.fspath(leg)
    if os.path.isfile(path):
        doc = kernel.record_read(path)
        return {'root': doc['root'], 'digest': doc['build_digest'],
                'audited': all(g['status'] == 'ok' for g in doc['gates']),
                'cost': doc.get('cost'), 'claim': doc.get('claim'),
                'record': doc, 'producer': doc.get('producer')}
    verified = kernel.verify(path)
    aud = kernel.audit(path)
    claim = kernel.load_recipe(path)['claim']
    return {'root': verified['root'], 'digest': kernel.build_digest(path),
            'audited': verified['ok'] and aud['ok'], 'cost': kernel.cost(path),
            'claim': {k: claim[k] for k in ('tolerance', 'envelope', 'mutation_floor') if k in claim},
            'producer': kernel.independence(path)}


def crosscheck(m1, m2, m3, *, mutants=None, tolerance=None):
    from reticuli import kernel
    paths = [os.path.realpath(os.fspath(x)) for x in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise core.ClaimError('three-machine paths must be distinct')
    machines = [_machine(x) for x in (m1, m2, m3)]
    a, b, c = machines
    roots = {name: x['root'] for name, x in zip(('M1', 'M2', 'M3'), machines)}
    audited = {name: x['audited'] for name, x in zip(('M1', 'M2', 'M3'), machines)}
    equivalence = len(set(roots.values())) == 1
    reuse = a['digest'] == b['digest']
    rejected, incomplete = [], []
    if not equivalence:
        rejected.append('roots')
    if not reuse:
        rejected.append('reuse')
    if not all(audited.values()):
        rejected.append('audit')
    declared = a['claim']
    if declared is None:
        incomplete.append('declared conditions')
        declared = {}
    c1, c3 = a['cost'] or {}, c['cost'] or {}
    unit = next((u for u in core.COST_LADDER if u in c1 and u in c3), None)
    band = tolerance or declared.get('tolerance', core.TOLERANCE)
    comparable = None
    ratio = None
    if unit:
        if c1[unit] == c3[unit] == 0:
            ratio = 1.0
        elif not c1[unit] or not c3[unit]:
            ratio = float('inf')
        else:
            ratio = c3[unit] / c1[unit]
        comparable = 1 / band <= ratio <= band
        if not comparable and 'tolerance' in declared:
            rejected.append('tolerance')
    envelope = {}
    for u, ceiling in declared.get('envelope', {}).items():
        measured = c3.get(u)
        within = None if measured is None else measured <= ceiling
        envelope[u] = {'ceiling': ceiling, 'measured': measured, 'within': within}
        if within is False:
            rejected.append('envelope ' + u)
        elif within is None:
            incomplete.append('envelope ' + u)
    mutation = None
    if 'mutation_floor' in declared:
        if mutants is None:
            incomplete.append('mutation floor')
        elif os.path.isdir(os.fspath(m3)):
            mutation = kernel.mutation_score(m3, max_mutants=mutants)
            mutation['ok'] = mutation['rate'] >= declared['mutation_floor']
            if not mutation['ok']:
                rejected.append('mutation floor')
        else:
            incomplete.append('mutation floor')
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    producer = c.get('producer') or {}
    if producer.get('vendor') and producer.get('model') and producer.get('blind'):
        independence = f"declared: {producer['vendor']}/{producer['model']}, blind workspace (not proven)"
    else:
        independence = 'unestablished: producer independence not proven'
    return {'satisfied': verdict == 'accept', 'verdict': verdict,
            'rejected': rejected, 'incomplete': incomplete,
            'equivalence': equivalence, 'reuse': reuse, 'audited': audited,
            'roots': roots, 'cost': {'M1': a['cost'], 'M3': c['cost'],
                                   'unit': unit, 'ratio': ratio, 'comparable': comparable,
                                   'envelope': envelope},
            'mutation_score': mutation, 'independence': independence}


def record_proof(m1, m2, m3, **kwargs):
    from reticuli import kernel
    if not os.path.isdir(m1):
        raise core.ClaimError('proof must land on a claim directory')
    records = []
    for leg in (m2, m3):
        if os.path.isfile(leg):
            anchor = os.environ.get(core._ENV_SIGNERS)
            signer = kernel.record_signer(leg, anchor) if anchor else None
            if not signer:
                raise core.ClaimError('record has no anchored signer')
            records.append({'digest': kernel.record_digest(kernel.record_read(leg)), 'signer': signer})
    result = crosscheck(m1, m2, m3, **kwargs)
    result['proof_recorded'] = result['satisfied']
    if result['satisfied']:
        manifest = kernel.read_manifest(m1)
        manifest['proof'] = {'kind': 'crosscheck', 'roots': result['roots'], 'records': records}
        core._write_json(core._safe(m1, core.MANIFEST), manifest)
    return result
