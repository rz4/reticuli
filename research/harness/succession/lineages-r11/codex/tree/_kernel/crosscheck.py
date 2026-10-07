"""Three-machine comparison and deterministic mutation probes."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import tempfile

from . import core, recipe, identity, run, seal, attest

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<', '<': '>', '>=': '<=', '<=': '>=', '==': '!=', '!=': '==', '+': '-', '-': '+'}
_OP_KIND = dict.fromkeys(_OP_ALTS, 'operator')
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}
_STRING_LITERAL = re.compile(r"(['\"])(?:\\.|(?!\1).)*?\1")


def _label(value):
    return str(value)


def _named(value):
    return getattr(value, 'name', str(value))


def _span_text(source, start, end):
    return source[start:end]


def _splice(source, start, end, replacement):
    return source[:start] + replacement + source[end:]


def _edit(source, start, end, replacement):
    return _splice(source, start, end, replacement)


def _node_span(node, lines):
    start = sum(len(line) for line in lines[:node.lineno - 1]) + node.col_offset
    end = sum(len(line) for line in lines[:node.end_lineno - 1]) + node.end_col_offset
    return start, end


def _docstring_spans(tree, lines):
    spans = []
    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if body and isinstance(body, list) and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            spans.append(_node_span(body[0], lines))
    return spans


def _structural_mutants(source):
    """Small deterministic changes to executable Python expressions."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines(keepends=True)
    edits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and node.ops:
            a, b = _node_span(node, lines)
            segment = source[a:b]
            for old, new in _OP_ALTS.items():
                match = re.search(r'(?<![<>=!])' + re.escape(old) + r'(?![=])', segment)
                if match:
                    edits.append(_splice(source, a + match.start(), a + match.end(), new))
                    break
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.BinOp):
            a, b = _node_span(node.value, lines)
            segment = source[a:b]
            if '-' in segment:
                edits.append(_splice(source, a + segment.index('-'), a + segment.index('-') + 1, '+'))
    return list(dict.fromkeys(edits))


def _token_mutants(source):
    edits = []
    for match in re.finditer(r'\b(?:True|False|and|or)\b', source):
        edits.append(_splice(source, match.start(), match.end(), _WORD_ALTS[match.group()]))
    return edits


def _mutants(source):
    return list(dict.fromkeys(_structural_mutants(source) + _token_mutants(source)))


def _draw_order(items, seed):
    return sorted(items, key=lambda x: hashlib.sha256((seed + repr(x)).encode()).digest())


def _mutant_order(items, seed):
    return _draw_order(items, seed)


def _machine(path):
    path = os.fspath(path)
    if os.path.isfile(path):
        doc = attest.record_read(path)
        return {'path': path, 'record': True, 'root': doc['root'], 'build_digest': doc['build_digest'],
                'audited': all(g['status'] == 'ok' for g in doc['gates']),
                'gates': doc['gates'], 'cost': doc.get('cost'),
                'claim': doc.get('claim') if doc['record'] >= 2 else None}
    checked = seal.verify(path)
    from reticuli import kernel
    audited = kernel.audit(path)
    parsed = recipe.load_recipe(path)
    return {'path': path, 'record': False, 'root': checked['root'],
            'build_digest': identity.build_digest(path),
            'audited': checked['ok'] and audited['ok'], 'gates': audited['gates'],
            'cost': run.cost(path), 'claim': parsed['claim']}


def crosscheck(m1, m2, m3, *, mutants=None):
    paths = [os.path.realpath(os.fspath(p)) for p in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise core.ClaimError('three distinct machine paths are required')
    legs = [_machine(p) for p in paths]
    names = ('M1', 'M2', 'M3')
    roots = dict(zip(names, (l['root'] for l in legs)))
    audited = dict(zip(names, (l['audited'] for l in legs)))
    equivalence = len(set(roots.values())) == 1
    reuse = legs[0]['build_digest'] == legs[1]['build_digest']
    claim = legs[0]['claim']
    rejected = []
    incomplete = []
    if not equivalence: rejected.append('root equivalence')
    if not reuse: rejected.append('byte reuse')
    if not all(audited.values()): rejected.append('audit')
    tolerance = (claim or {}).get('tolerance', core.TOLERANCE)
    first, last = legs[0]['cost'] or {}, legs[2]['cost'] or {}
    unit = next((u for u in core.COST_LADDER if u in first and u in last), None)
    comparable = None
    if unit:
        a, b = first[unit], last[unit]
        comparable = (b <= a * tolerance and a <= b * tolerance) if a and b else a == b
    if claim is None:
        incomplete.append('claim obligations')
    elif 'tolerance' in claim:
        if comparable is False: rejected.append('tolerance')
        if comparable is None: incomplete.append('tolerance')
    envelope = {}
    for unit_name, ceiling in (claim or {}).get('envelope', {}).items():
        measured = last.get(unit_name)
        within = None if measured is None else measured <= ceiling
        envelope[unit_name] = {'ceiling': ceiling, 'measured': measured, 'within': within}
        if within is False: rejected.append('envelope ' + unit_name)
        if within is None: incomplete.append('envelope ' + unit_name)
    mutation = None
    if claim and 'mutation_floor' in claim:
        if mutants is None or legs[2]['record']:
            incomplete.append('mutation floor')
        else:
            from reticuli import kernel
            mutation = kernel.mutation_score(paths[2], max_mutants=mutants)
            mutation['ok'] = mutation['rate'] >= claim['mutation_floor']
            if not mutation['ok']: rejected.append('mutation floor')
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    from reticuli import kernel
    ind = kernel.independence(paths[2]) if not legs[2]['record'] else {}
    if ind.get('vendor') and ind.get('model'):
        independence = f"declared: {ind['vendor']}/{ind['model']}, blind workspace ({'not proven'})"
    else:
        independence = 'unestablished'
    return {'satisfied': verdict == 'accept', 'verdict': verdict, 'rejected': rejected,
            'incomplete': incomplete, 'roots': roots, 'audited': audited,
            'equivalence': equivalence, 'reuse': reuse, 'cost': {'unit': unit,
            'comparable': comparable, 'original': legs[0]['cost'], 'rebuild': legs[2]['cost'],
            'envelope': envelope}, 'mutation_score': mutation, 'independence': independence}
