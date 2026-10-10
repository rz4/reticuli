"""Three-machine comparison and deterministic mutation probes."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import tempfile

from . import core, identity, recipe, run, seal, attest

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<=', '<': '>=', '>=': '<', '<=': '>', '==': '!=', '!=': '==', '+': '-', '-': '+'}
_OP_KIND = {ast.Gt: '>', ast.Lt: '<', ast.GtE: '>=', ast.LtE: '<=', ast.Eq: '==', ast.NotEq: '!='}
_STRING_LITERAL = re.compile(r'''(['"])(?:\\.|(?!\1).)*?\1''')
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}


def _named(value):
    return str(value)


def _label(value):
    return str(value)


def _machine(path):
    if os.path.isfile(path):
        doc = attest.record_read(path)
        return {'root': doc['root'], 'digest': doc['build_digest'], 'audited': all(g['status'] == 'ok' for g in doc['gates']), 'cost': doc.get('cost'), 'claim': doc.get('claim') if doc['record'] >= 2 else None, 'record': doc, 'path': path}
    v = seal.verify(path)
    a = __import__('reticuli.kernel', fromlist=['audit']).audit(path)
    parsed = recipe.load_recipe(path)
    obligations = {k: parsed['claim'][k] for k in ('tolerance', 'envelope', 'mutation_floor') if k in parsed['claim']}
    return {'root': v['root'], 'digest': identity.build_digest(path), 'audited': v['ok'] and a['ok'], 'cost': __import__('reticuli.kernel', fromlist=['cost']).cost(path), 'claim': obligations, 'record': None, 'path': path}


def _draw_order(items, seed):
    return sorted(items, key=lambda x: hashlib.sha256((seed + repr(x)).encode()).digest())


def _mutant_order(items, seed):
    return _draw_order(items, seed)


def _docstring_spans(tree):
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            spans.append(_node_span(node.body[0]))
    return spans


def _node_span(node):
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def _span_text(source, span):
    lines = source.splitlines(keepends=True)
    a,b,c,d = span
    return ''.join(lines[a-1:c])[b:d] if a == c else lines[a-1][b:] + ''.join(lines[a:c-1]) + lines[c-1][:d]


def _splice(source, start, end, replacement):
    return source[:start] + replacement + source[end:]


def _edit(source, old, new):
    return source.replace(old, new, 1)


def _structural_mutants(source):
    candidates = []
    for pattern, replacement in ((r'(?<![<>=!])>(?!=)', '<='), (r'(?<![<>=!])<(?!=)', '>='), (r'(?<![=])==(?!=)', '!='), (r'(?<![=])!=(?!=)', '=='), (r'(?<![+])\+(?![+=])', '-'), (r'(?<![-])-(?![-=>])', '+')):
        for match in re.finditer(pattern, source):
            candidates.append(_splice(source, match.start(), match.end(), replacement))
    return list(dict.fromkeys(candidates))


def _token_mutants(source):
    candidates = []
    for old,new in _WORD_ALTS.items():
        for match in re.finditer(r'\b'+old+r'\b', source):
            candidates.append(_splice(source, match.start(), match.end(), new))
    return list(dict.fromkeys(candidates))


def _mutants(source):
    return list(dict.fromkeys(_structural_mutants(source) + _token_mutants(source)))


def mutation_score(directory, *, max_mutants=core.MUTANT_CEILING):
    from . import build
    parsed = recipe.load_recipe(directory)
    root = seal.verify(directory)['root']
    candidates = []
    for name in recipe.generated_outputs(parsed):
        path = core._safe(directory, name)
        if os.path.isfile(path) and name.endswith('.py'):
            try:
                source = open(path, encoding='utf-8').read()
            except UnicodeError:
                continue
            candidates += [(name, content) for content in _mutants(source)]
    chosen = _mutant_order(candidates, root)[:max_mutants]
    survivors = []
    for index, (name, content) in enumerate(chosen):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as room:
            build._materialize(directory, room, parsed, generated=True)
            with open(core._safe(room, name), 'w', encoding='utf-8') as f:
                f.write(content)
            gates = build._judge(directory, room, parsed)
            if all(row['status'] == 'ok' for row in gates):
                survivors.append(index)
    count = len(chosen)
    result = {'mutants': count, 'killed': count-len(survivors), 'survivors': survivors, 'rate': (count-len(survivors))/count if count else 0.0}
    core._write_json(core._safe(directory, core.MUTATION_RESIDUE), result)
    return result


def crosscheck(m1, m2, m3, *, mutants=None):
    paths = [os.path.realpath(os.fspath(p)) for p in (m1,m2,m3)]
    if len(set(paths)) != 3:
        raise core.ClaimError('three machines need distinct paths')
    legs = [_machine(p) for p in (m1,m2,m3)]
    roots = {k: leg['root'] for k,leg in zip(('M1','M2','M3'),legs)}
    audited = {k: leg['audited'] for k,leg in zip(('M1','M2','M3'),legs)}
    equivalence = len(set(roots.values())) == 1
    reuse = legs[0]['digest'] == legs[1]['digest']
    c1,c3 = legs[0]['cost'],legs[2]['cost']
    claim = legs[0]['claim']
    tolerance = (claim or {}).get('tolerance', core.TOLERANCE)
    shared = next((key for key in core.COST_LADDER if c1 and c3 and key in c1 and key in c3), None)
    comparable = None
    if shared:
        a,b = c1[shared],c3[shared]
        comparable = (a == b == 0) if not a or not b else max(a/b,b/a) <= tolerance
    cost_report = {'comparable': comparable, 'unit': shared, 'M1': c1, 'M3': c3, 'envelope': {}}
    rejected = []
    incomplete = []
    if not equivalence: rejected.append('root')
    if not reuse: rejected.append('reuse')
    for role, ok in audited.items():
        if not ok: rejected.append('audit '+role)
    if claim is None: incomplete.append('declared conditions')
    elif 'tolerance' in claim and comparable is False: rejected.append('tolerance')
    for unit, ceiling in (claim or {}).get('envelope', {}).items():
        measured = c3.get(unit) if c3 else None
        within = None if measured is None else measured <= ceiling
        cost_report['envelope'][unit] = {'ceiling': ceiling, 'measured': measured, 'within': within}
        if within is False: rejected.append('envelope '+unit)
        if within is None: incomplete.append('envelope '+unit)
    mutation = None
    if claim and 'mutation_floor' in claim:
        if mutants is None or os.path.isfile(m3):
            incomplete.append('mutation floor')
        else:
            mutation = mutation_score(m3, max_mutants=mutants)
            mutation['ok'] = mutation['rate'] >= claim['mutation_floor']
            if not mutation['ok']: rejected.append('mutation floor')
    declaration = __import__('reticuli.kernel', fromlist=['independence']).independence(m3) if not os.path.isfile(m3) else {}
    independence = ('declared: '+str(declaration.get('vendor'))+'/'+str(declaration.get('model'))+', blind workspace (not proven)' if declaration.get('vendor') and declaration.get('model') and declaration.get('blind') else 'unestablished: producer independence not proven')
    verdict = 'reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied': verdict == 'accept', 'verdict': verdict, 'rejected': rejected, 'incomplete': incomplete, 'roots': roots, 'equivalence': equivalence, 'reuse': reuse, 'audited': audited, 'cost': cost_report, 'mutation_score': mutation, 'independence': independence}


def record_proof(m1,m2,m3, *, mutants=None):
    if os.path.isfile(m1):
        raise core.ClaimError('proof needs a directory M1')
    result = crosscheck(m1,m2,m3,mutants=mutants)
    if not result['satisfied']:
        return {'proof_recorded': False, 'crosscheck': result}
    records = []
    for path in (m2,m3):
        if os.path.isfile(path):
            anchor = os.environ.get(core._ENV_SIGNERS)
            if not anchor:
                raise core.ClaimError('record proof needs a signer anchor')
            signer = attest.record_signer(path,anchor)
            if not signer:
                raise core.ClaimError('record signature is untrusted')
            records.append({'digest': attest.record_digest(attest.record_read(path)), 'signer': signer})
    manifest = seal.read_manifest(m1)
    manifest['proof'] = {'kind': 'crosscheck', 'm2': result['roots']['M2'], 'm3': result['roots']['M3'], 'records': records}
    core._write_json(core._safe(m1,core.MANIFEST),manifest)
    return {'proof_recorded': True, 'crosscheck': result}
