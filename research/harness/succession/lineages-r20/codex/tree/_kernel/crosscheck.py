"""Deterministic mutation helpers and three-machine comparison primitives."""
from __future__ import annotations

import ast
import hashlib
import os
import re

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': ('<', '>=', '<='), '<': ('>', '<=', '>='), '==': ('!=',), '-': ('+', '*')}
_OP_KIND = {'>': 'comparison', '<': 'comparison', '-': 'arithmetic'}
_WORD_ALTS = {'True': ('False',), 'False': ('True',), 'and': ('or',), 'or': ('and',)}
_STRING_LITERAL = re.compile(r'''(?P<quote>['\"])(?:\\.|(?!\1).)*?\1''')


def _span_text(text, start, end):
    return text[start:end]


def _splice(text, start, end, replacement):
    return text[:start] + replacement + text[end:]


def _edit(text, old, new, occurrence=0):
    positions = [m.start() for m in re.finditer(re.escape(old), text)]
    if occurrence >= len(positions):
        return text
    p = positions[occurrence]
    return _splice(text, p, p + len(old), new)


def _node_span(text, node):
    lines = text.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1])) + node.col_offset
    end = sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset
    return start, end


def _docstring_spans(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    spans = []
    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if body and isinstance(body, list) and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            spans.append(_node_span(text, body[0]))
    return spans


def _named(name, text):
    return {'name': name, 'text': text}


def _label(name, number):
    return f'{name}:{number}'


def _draw_order(items, seed):
    return sorted(items, key=lambda item: hashlib.sha256((seed + repr(item)).encode()).digest())


def _mutant_order(items, seed):
    return _draw_order(items, seed)


def _token_mutants(text):
    out = []
    for old, alternatives in {**_OP_ALTS, **_WORD_ALTS}.items():
        for match in re.finditer(r'(?<!\w)' + re.escape(old) + r'(?!\w)', text):
            for alt in alternatives:
                candidate = _splice(text, match.start(), match.end(), alt)
                if candidate != text:
                    out.append(candidate)
    return out


def _structural_mutants(text):
    out = []
    for match in re.finditer(r'(?<!\w)\d+(?!\w)', text):
        out.append(_splice(text, match.start(), match.end(), str(int(match.group()) + 1)))
    return out


def _mutants(text):
    return list(dict.fromkeys(_token_mutants(text) + _structural_mutants(text)))


def _machine(path, role=None):
    return {'path': os.path.realpath(path), 'role': role}
