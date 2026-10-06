"""Three-machine comparison and deterministic mutation probes."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import core

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<', '<': '>', '==': '!=', '!=': '==', '+': '-', '-': '+'}
_OP_KIND = {x: 'operator' for x in _OP_ALTS}
_STRING_LITERAL = re.compile(r'''(["'])(?:\\.|(?!\1).)*?\1''')
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}


def _named(name: str, value: Any) -> dict[str, Any]:
    return {'name': name, 'value': value}


def _label(path: str, number: int) -> str:
    return f'{path}:{number}'


def _draw_order(root: str, items: list[Any]) -> list[Any]:
    return sorted(items, key=lambda item: hashlib.sha256((root + repr(item)).encode()).digest())


def _mutant_order(root: str, items: list[Any]) -> list[Any]:
    return _draw_order(root, items)


def _splice(text: str, start: int, end: int, replacement: str) -> str:
    return text[:start] + replacement + text[end:]


def _edit(text: str, old: str, new: str) -> str:
    return text.replace(old, new, 1)


def _node_span(node: ast.AST, lines: list[str]) -> tuple[int, int]:
    begin = sum(len(line) for line in lines[:node.lineno-1]) + node.col_offset
    end = sum(len(line) for line in lines[:node.end_lineno-1]) + node.end_col_offset
    return begin, end


def _span_text(node: ast.AST, source: str) -> str:
    a, b = _node_span(node, source.splitlines(keepends=True))
    return source[a:b]


def _docstring_spans(source: str) -> list[tuple[int, int]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines(keepends=True)
    result = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                result.append(_node_span(first, lines))
    return result


def _structural_mutants(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    result = []
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = node.ops[0]
            swapped = {ast.Gt: '<', ast.Lt: '>', ast.Eq: '!=', ast.NotEq: '==', ast.GtE: '<', ast.LtE: '>'}.get(type(op))
            if swapped:
                a, b = _node_span(node, lines)
                original = source[a:b]
                for pattern in (' >= ', ' <= ', ' == ', ' != ', ' > ', ' < '):
                    if pattern in original:
                        result.append(_splice(source, a, b, original.replace(pattern, ' ' + swapped + ' ', 1)))
                        break
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            a, b = _node_span(node, lines)
            original = source[a:b]
            old, new = (' + ', ' - ') if isinstance(node.op, ast.Add) else (' - ', ' + ')
            if old in original:
                result.append(_splice(source, a, b, original.replace(old, new, 1)))
    return result


def _token_mutants(source: str) -> list[str]:
    result = []
    for match in re.finditer(r'\b(?:True|False|and|or)\b|(?<!\w)\d+(?!\w)', source):
        old = match.group()
        new = _WORD_ALTS.get(old, str(int(old) + 1) if old.isdecimal() else old)
        result.append(_splice(source, match.start(), match.end(), new))
    return result


def _mutants(source: str) -> list[str]:
    return list(dict.fromkeys(_structural_mutants(source) + _token_mutants(source)))


def mutation_score(directory: str, max_mutants: int = 20) -> dict[str, Any]:
    from reticuli import kernel
    parsed = kernel.load_recipe(directory)
    root = kernel.verify(directory)['root']
    candidates = []
    for name in kernel.generated_outputs(parsed):
        path = core._safe(directory, name)
        if os.path.isfile(path) and name.endswith('.py'):
            original = Path(path).read_text(encoding='utf-8')
            candidates.extend((name, candidate) for candidate in _mutants(original))
    chosen = _mutant_order(root, candidates)[:max_mutants]
    survivors = []
    killed = 0
    for number, (name, candidate) in enumerate(chosen):
        with tempfile.TemporaryDirectory(prefix='reticuli-mut-') as room:
            kernel._materialize(directory, room)
            target = core._safe(room, name)
            Path(target).write_text(candidate, encoding='utf-8')
            verdict = kernel._audit_room(directory, room, parsed)
            if verdict['ok']:
                survivors.append(_label(name, number))
            else:
                killed += 1
    result = {'mutants': len(chosen), 'killed': killed, 'survivors': survivors,
              'rate': killed / len(chosen) if chosen else 0.0}
    core._write_json(core._safe(directory, core.MUTATION_RESIDUE), result)
    return result


def _machine(path: str) -> dict[str, Any]:
    from reticuli import kernel
    if os.path.isfile(path):
        doc = kernel.record_read(path)
        return {'root': doc['root'], 'digest': doc['build_digest'],
                'audited': all(g['status'] == 'ok' for g in doc['gates']),
                'cost': doc.get('cost'), 'producer': doc.get('producer'),
                'claim': doc.get('claim') if doc['record'] >= 2 else None,
                'record': True}
    verified = kernel.verify(path)
    audited = kernel.audit(path)
    return {'root': verified['root'], 'digest': kernel.build_digest(path),
            'audited': verified['ok'] and audited['ok'], 'cost': kernel.cost(path),
            'producer': kernel.independence(path),
            'claim': kernel.load_recipe(path)['claim'], 'record': False}


def crosscheck(m1: str, m2: str, m3: str, *, mutants: int = 0) -> dict[str, Any]:
    from reticuli import kernel
    paths = [os.path.realpath(os.fspath(p)) for p in (m1, m2, m3)]
    if len(set(paths)) != 3:
        raise core.ClaimError('three machines must have distinct paths')
    a, b, c = map(_machine, paths)
    roots = {'M1': a['root'], 'M2': b['root'], 'M3': c['root']}
    audited = {'M1': a['audited'], 'M2': b['audited'], 'M3': c['audited']}
    equivalent = len(set(roots.values())) == 1
    reuse = a['digest'] == b['digest']
    declared = a['claim']
    rejected, incomplete = [], []
    if not equivalent: rejected.append('root')
    if not reuse: rejected.append('reuse')
    if not all(audited.values()): rejected.append('audit')
    first, third = a['cost'] or {}, c['cost'] or {}
    unit = next((u for u in core.COST_LADDER if u in first and u in third), None)
    tolerance = (declared or {}).get('tolerance', core.TOLERANCE)
    comparable = kernel._in_band(first[unit], third[unit], tolerance) if unit else None
    cost = {'unit': unit, 'comparable': comparable, 'M1': a['cost'], 'M3': c['cost'], 'envelope': {}}
    if declared is None:
        incomplete.append('claim obligations')
    else:
        if 'tolerance' in declared and comparable is False:
            rejected.append('tolerance')
        for u, ceiling in declared.get('envelope', {}).items():
            within = third[u] <= ceiling if u in third else None
            cost['envelope'][u] = {'limit': ceiling, 'measured': third.get(u), 'within': within}
            if within is False: rejected.append('envelope ' + u)
            if within is None: incomplete.append('envelope ' + u)
    score = None
    if declared and 'mutation_floor' in declared:
        if mutants and not c['record']:
            score = mutation_score(paths[2], mutants)
            score['ok'] = score['rate'] >= declared['mutation_floor']
            if not score['ok']: rejected.append('mutation floor')
        else:
            incomplete.append('mutation floor')
    producer = c.get('producer') or {}
    if producer.get('vendor'):
        independence = f"declared: {producer['vendor']}/{producer.get('model','')}, blind workspace; not proven"
    else:
        independence = 'unestablished: producer independence not proven'
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied': verdict == 'accept', 'verdict': verdict, 'rejected': rejected,
            'incomplete': incomplete, 'roots': roots, 'equivalence': equivalent,
            'reuse': reuse, 'audited': audited, 'cost': cost,
            'mutation_score': score, 'independence': independence}
