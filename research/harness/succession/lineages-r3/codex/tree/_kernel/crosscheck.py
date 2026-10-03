"""Mutation sampling helpers for the kernel crosscheck."""
from __future__ import annotations

import ast
import hashlib
import io
import re
import tokenize

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'+': '-', '-': '+', '*': '+', '>': '<', '<': '>', '==': '!=', '!=': '==', '>=': '<', '<=': '>'}
_OP_KIND = {key: 'operator' for key in _OP_ALTS}
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}
_STRING_LITERAL = re.compile(r'''(["'])(?:\\.|[^\\])*?\1''')

def _docstring_spans(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [_node_span(node.body[0], source) for node in ast.walk(tree)
            if getattr(node, 'body', None) and isinstance(node.body, list)
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)]

def _node_span(node, source):
    lines = source.splitlines(keepends=True)
    return (sum(map(len, lines[:node.lineno - 1])) + node.col_offset,
            sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset)

def _span_text(source, span):
    return source[span[0]:span[1]]

def _splice(source, span, replacement):
    return source[:span[0]] + replacement + source[span[1]:]

def _edit(source, old, new):
    return source.replace(old, new, 1)

def _label(kind, index):
    return f'{kind}:{index}'

def _named(name, source):
    return (name, source)

def _token_mutants(source):
    out = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        lines = source.splitlines(keepends=True)
        for tok in tokens:
            replacement = (_OP_ALTS.get(tok.string) if tok.type == tokenize.OP
                           else _WORD_ALTS.get(tok.string) if tok.type == tokenize.NAME else None)
            if replacement:
                start = sum(map(len, lines[:tok.start[0]-1])) + tok.start[1]
                end = sum(map(len, lines[:tok.end[0]-1])) + tok.end[1]
                out.append(_splice(source, (start, end), replacement))
    except (tokenize.TokenError, IndentationError):
        pass
    return out

def _structural_mutants(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [_splice(source, _node_span(node.value, source), 'None')
            for node in ast.walk(tree) if isinstance(node, ast.Return) and node.value]

def _mutants(source):
    return list(dict.fromkeys(_token_mutants(source) + _structural_mutants(source)))

def _draw_order(root, count):
    return sorted(range(count), key=lambda i: hashlib.sha256(f'{root}:{i}'.encode()).digest())

def _mutant_order(root, mutants):
    return [mutants[i] for i in _draw_order(root, len(mutants))]

def _machine(path):
    return str(path)
