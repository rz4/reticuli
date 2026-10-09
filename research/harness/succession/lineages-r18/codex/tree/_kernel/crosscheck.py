"""Three-machine comparison and deterministic mutation sampling."""
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import tokenize

from . import attest, build, core, identity, recipe, run, seal

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<', '<': '>', '>=': '<', '<=': '>', '==': '!=', '!=': '==', '+': '-', '-': '+'}
_OP_KIND = {key: 'operator' for key in _OP_ALTS}
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}
_STRING_LITERAL = re.compile(r'''(['"])(?:\\.|(?!\1).)*?\1''')


def _label(name: str, index: int) -> str:
    return f'{name}:{index}'


def _named(names: list[str], name: str) -> bool:
    return name in names


def _draw_order(root: str, values: list) -> list:
    return sorted(values, key=lambda value: hashlib.sha256((root + repr(value)).encode()).digest())


def _mutant_order(root: str, values: list) -> list:
    return _draw_order(root, values)


def _node_span(node: ast.AST) -> tuple[int, int, int, int]:
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def _span_text(source: str, span: tuple[int, int, int, int]) -> str:
    lines = source.splitlines(keepends=True)
    a, b, c, d = span
    if a == c:
        return lines[a-1][b:d]
    return lines[a-1][b:] + ''.join(lines[a:c-1]) + lines[c-1][:d]


def _splice(source: str, span: tuple[int, int, int, int], replacement: str) -> str:
    lines = source.splitlines(keepends=True)
    a, b, c, d = span
    return ''.join(lines[:a-1]) + lines[a-1][:b] + replacement + lines[c-1][d:] + ''.join(lines[c:])


def _edit(source: str, old: str, new: str, start: int = 0) -> str:
    return source[:start] + source[start:].replace(old, new, 1)


def _docstring_spans(source: str) -> list[tuple[int, int, int, int]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                spans.append(_node_span(body[0]))
    return spans


def _structural_mutants(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                symbols = {ast.Gt: '>', ast.Lt: '<', ast.GtE: '>=', ast.LtE: '<=', ast.Eq: '==', ast.NotEq: '!='}
                old = symbols.get(type(op))
                if old:
                    segment = _span_text(source, _node_span(node))
                    replacement = _OP_ALTS[old]
                    changed = segment.replace(old, replacement, 1)
                    if changed != segment:
                        found.append(_splice(source, _node_span(node), changed))
        elif isinstance(node, ast.BinOp):
            symbols = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*'}
            old = symbols.get(type(node.op))
            if old:
                segment = _span_text(source, _node_span(node))
                changed = segment.replace(old, _OP_ALTS.get(old, '+'), 1)
                if changed != segment:
                    found.append(_splice(source, _node_span(node), changed))
    return found


def _token_mutants(source: str) -> list[str]:
    found = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return found
    for token in tokens:
        if token.type == tokenize.OP and token.string in _OP_ALTS:
            changed = _splice(source, (token.start[0], token.start[1], token.end[0], token.end[1]), _OP_ALTS[token.string])
            if changed != source:
                found.append(changed)
        elif token.type == tokenize.NAME and token.string in _WORD_ALTS:
            found.append(_splice(source, (token.start[0], token.start[1], token.end[0], token.end[1]), _WORD_ALTS[token.string]))
    return found


def _mutants(source: str) -> list[str]:
    return list(dict.fromkeys(_structural_mutants(source) + _token_mutants(source)))


def mutation_score(claim_dir: str, max_mutants: int = 20) -> dict:
    doc = recipe.load_recipe(claim_dir)
    root = identity.root(doc, claim_dir)
    candidates = []
    for step in recipe.produces(doc):
        if step.get('class', 'generated') != 'generated' or 'from' in step or not step['output'].endswith('.py'):
            continue
        path = core._safe(claim_dir, step['output'])
        if not os.path.isfile(path):
            continue
        try:
            source = open(path, encoding='utf-8').read()
        except UnicodeError:
            continue
        for changed in _mutants(source):
            candidates.append((step['output'], changed))
    candidates = _mutant_order(root, candidates)[:max_mutants]
    killed = 0
    survivors = []
    for index, (name, changed) in enumerate(candidates):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as room:
            build._materialize(claim_dir, room, doc)
            with open(core._safe(room, name), 'w', encoding='utf-8') as target:
                target.write(changed)
            gates = build._judge(claim_dir, room, doc)
            if all(g['status'] == 'ok' for g in gates):
                survivors.append(_label(name, index))
            else:
                killed += 1
    count = len(candidates)
    result = {'mutants': count, 'killed': killed, 'survivors': survivors, 'rate': killed / count if count else 0.0}
    core._write_json(os.path.join(claim_dir, core.MUTATION_RESIDUE), result)
    return result


def _machine(path: str, audit_fn) -> dict:
    if os.path.isfile(path):
        doc = attest.record_read(path)
        return {'root': doc['root'], 'digest': doc['build_digest'],
                'audited': all(g['status'] == 'ok' for g in doc['gates']),
                'cost': doc.get('cost'), 'claim': doc.get('claim') if doc['record'] >= 2 else None,
                'producer': doc.get('producer', {}), 'record': doc}
    checked = seal.verify(path)
    audit = audit_fn(path) if checked['ok'] else {'ok': False}
    from . import run as run_module
    return {'root': checked['root'], 'digest': identity.build_digest(path),
            'audited': bool(audit['ok']), 'cost': _cost(path),
            'claim': recipe.load_recipe(path)['claim'],
            'producer': _independence(path), 'record': None}


def _cost(path: str) -> dict | None:
    totals = {}
    for event in run.ledger_events(path):
        for key in core.COST_KEYS:
            value = event.get(key)
            if type(value) in (int, float):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _independence(path: str) -> dict:
    for event in run.ledger_events(path):
        if event.get('event') == 'producer':
            return {k: event[k] for k in ('vendor', 'model', 'blind') if k in event}
    return {}


def _comparison(a: dict | None, b: dict | None, tolerance: float) -> dict:
    shared = next((unit for unit in core.COST_LADDER if a and b and unit in a and unit in b), None)
    if shared is None:
        return {'unit': None, 'comparable': None}
    av, bv = a[shared], b[shared]
    return {'unit': shared, 'original': av, 'rebuild': bv,
            'comparable': run._in_band(av, bv, tolerance)}


def crosscheck(m1: str, m2: str, m3: str, *, mutants: int | None = None, audit_fn=None) -> dict:
    if len({os.path.realpath(os.fspath(p)) for p in (m1, m2, m3)}) != 3:
        raise core.ClaimError('three machines require distinct paths')
    if audit_fn is None:
        audit_fn = build.audit
    legs = {name: _machine(os.fspath(path), audit_fn) for name, path in zip(('M1', 'M2', 'M3'), (m1, m2, m3))}
    a, b, c = (legs[k] for k in ('M1', 'M2', 'M3'))
    roots = {k: v['root'] for k, v in legs.items()}
    equivalent = len(set(roots.values())) == 1
    reuse = a['digest'] == b['digest']
    audited = {k: v['audited'] for k, v in legs.items()}
    claim = a['claim']
    tolerance = claim.get('tolerance', core.TOLERANCE) if claim is not None else core.TOLERANCE
    comparison = _comparison(a['cost'], c['cost'], tolerance)
    envelope = {}
    for unit, limit in (claim or {}).get('envelope', {}).items():
        measured = c['cost'].get(unit) if c['cost'] else None
        envelope[unit] = {'limit': limit, 'measured': measured, 'within': measured <= limit if measured is not None else None}
    comparison['envelope'] = envelope
    rejected, incomplete = [], []
    if not equivalent: rejected.append('root')
    if not reuse: rejected.append('reuse')
    if not all(audited.values()): rejected.append('audit')
    if claim is None: incomplete.append('declared conditions')
    elif 'tolerance' in claim and comparison['comparable'] is False: rejected.append('tolerance')
    for unit, row in envelope.items():
        if row['within'] is False: rejected.append('envelope ' + unit)
        if row['within'] is None: incomplete.append('envelope ' + unit)
    score = None
    if claim and 'mutation_floor' in claim:
        if mutants is None or os.path.isfile(m3):
            incomplete.append('mutation floor')
        else:
            score = mutation_score(m3, mutants)
            score['ok'] = score['rate'] >= claim['mutation_floor']
            if not score['ok']: rejected.append('mutation floor')
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    p = c['producer']
    independence = (f"declared: {p['vendor']}/{p['model']}, blind workspace (not proven)"
                    if p.get('vendor') and p.get('model') and p.get('blind') else 'unestablished (not proven)')
    return {'satisfied': verdict == 'accept', 'verdict': verdict, 'rejected': rejected,
            'incomplete': incomplete, 'roots': roots, 'equivalence': equivalent,
            'reuse': reuse, 'audited': audited, 'cost': comparison,
            'independence': independence, 'mutation_score': score}


def record_proof(m1: str, m2: str, m3: str, *, mutants: int | None = None, audit_fn=None) -> dict:
    if os.path.isfile(m1):
        raise core.ClaimError('proof must land on a claim directory')
    records = []
    for leg in (m2, m3):
        if os.path.isfile(leg):
            anchor = os.environ.get(core._ENV_SIGNERS)
            if not anchor:
                raise core.ClaimError('record proof needs a trust anchor')
            signer = attest.record_signer(leg, anchor)
            if signer is None:
                raise core.ClaimError('record signature is not trusted')
            doc = attest.record_read(leg)
            records.append({'digest': attest.record_digest(doc), 'signer': signer})
    result = crosscheck(m1, m2, m3, mutants=mutants, audit_fn=audit_fn)
    result['proof_recorded'] = result['satisfied']
    if result['satisfied']:
        manifest = seal.read_manifest(m1)
        manifest['proof'] = {'kind': 'crosscheck', 'roots': result['roots'], 'records': records}
        core._write_json(os.path.join(m1, core.MANIFEST), manifest)
    return result
