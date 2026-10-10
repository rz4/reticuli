"""Mutation helpers and comparison vocabulary for the kernel."""
from __future__ import annotations
import ast
import re

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<', '<': '>', '>=': '<=', '<=': '>=', '==': '!=', '!=': '==', '+': '-', '-': '+'}
_OP_KIND = dict.fromkeys(_OP_ALTS, 'operator')
_WORD_ALTS = {'True': 'False', 'False': 'True'}
_STRING_LITERAL = re.compile(r'''(?P<quote>['"])(?:\\.|(?!\1).)*?\1''')


def _docstring_spans(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    spans = []
    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            spans.append(_node_span(body[0]))
    return spans


def _node_span(node):
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def _span_text(source, span):
    lines = source.splitlines(keepends=True)
    a, b, c, d = span
    return ''.join(lines[a-1:c])[b:d] if a == c else lines[a-1][b:] + ''.join(lines[a:c-1]) + lines[c-1][:d]


def _splice(source, span, replacement):
    lines = source.splitlines(keepends=True)
    a, b, c, d = span
    return ''.join(lines[:a-1]) + lines[a-1][:b] + replacement + lines[c-1][d:] + ''.join(lines[c:])


def _edit(source, old, new, start=0):
    i = source.find(old, start)
    return source if i < 0 else source[:i] + new + source[i+len(old):]


def _label(item):
    return str(item)


def _named(name, value):
    return (name, value)


def _draw_order(items, seed):
    import hashlib
    return sorted(items, key=lambda item: hashlib.sha256((str(seed) + repr(item)).encode()).hexdigest())


def _mutant_order(items, seed):
    return _draw_order(items, seed)


def _structural_mutants(source):
    candidates = []
    for old, new in _OP_ALTS.items():
        for match in re.finditer(r'(?<!\w)' + re.escape(old) + r'(?!\w)', source):
            changed = source[:match.start()] + new + source[match.end():]
            try:
                ast.parse(changed)
            except SyntaxError:
                continue
            if changed != source:
                candidates.append(changed)
    return list(dict.fromkeys(candidates))


def _token_mutants(source):
    return _structural_mutants(source)


def _mutants(source):
    return _structural_mutants(source)


def _machine(path):
    return str(path)
