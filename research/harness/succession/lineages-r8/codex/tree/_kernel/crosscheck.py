"""Comparison and mutation primitives for the public kernel."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import tempfile
import tokenize
from io import BytesIO

from . import core, recipe

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/')
_OP_ALTS = {'+': '-', '-': '+', '*': '/', '/': '*', '>': '<', '<': '>', '==': '!='}
_OP_KIND = dict.fromkeys(_OP_ALTS, 'operator')
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}
_STRING_LITERAL = re.compile(r"(['\"]).*?\1")


def _label(*parts):
    return ':'.join(map(str, parts))


def _named(value):
    return getattr(value, '__name__', str(value))


def _span_text(source, span):
    return source[span[0]:span[1]]


def _splice(source, start, end, replacement):
    return source[:start] + replacement + source[end:]


def _edit(source, old, new):
    return source.replace(old, new, 1)


def _node_span(node, lines):
    start = sum(len(line) for line in lines[:node.lineno - 1]) + node.col_offset
    end = sum(len(line) for line in lines[:node.end_lineno - 1]) + node.end_col_offset
    return start, end


def _docstring_spans(tree, lines):
    spans = []
    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            spans.append(_node_span(body[0], lines))
    return spans


def _structural_mutants(source):
    """Simple syntactic edits, stable in source order."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines(keepends=True)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = node.ops[0]
            left = node.left
            right = node.comparators[0]
            start = _node_span(left, lines)[1]
            end = _node_span(right, lines)[0]
            middle = source[start:end]
            for old, new in [('>', '<'), ('<', '>'), ('==', '!='), ('!=', '=='), ('>=', '<'), ('<=', '>')]:
                if old in middle:
                    found.append(_splice(source, start, end, middle.replace(old, new, 1)))
                    break
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            start = _node_span(node.left, lines)[1]
            end = _node_span(node.right, lines)[0]
            middle = source[start:end]
            old, new = ('+', '-') if isinstance(node.op, ast.Add) else ('-', '+')
            if old in middle:
                found.append(_splice(source, start, end, middle.replace(old, new, 1)))
    return found


def _token_mutants(source):
    found = []
    try:
        tokens = tokenize.tokenize(BytesIO(source.encode()).readline)
        for token in tokens:
            if token.type == tokenize.NUMBER and token.string.isdigit():
                lines = source.splitlines(keepends=True)
                start = sum(map(len, lines[:token.start[0] - 1])) + token.start[1]
                end = start + len(token.string)
                found.append(_splice(source, start, end, str(int(token.string) + 1)))
    except (tokenize.TokenError, UnicodeError):
        pass
    return found


def _mutants(source):
    return list(dict.fromkeys(_structural_mutants(source) + _token_mutants(source)))


def _draw_order(items, seed):
    return sorted(items, key=lambda x: hashlib.sha256((seed + str(x)).encode()).digest())


def _mutant_order(items, seed):
    return _draw_order(items, seed)


def _machine(path):
    return os.path.realpath(path)


def mutation_score(directory, max_mutants=core.MUTANT_CEILING):
    from reticuli import kernel
    claim = recipe.load_recipe(directory)
    candidates = []
    for name in recipe.generated_outputs(claim):
        if not name.endswith('.py'):
            continue
        path = core._safe(directory, name)
        if not os.path.isfile(path):
            continue
        source = open(path, encoding='utf-8').read()
        candidates.extend((name, variant) for variant in _mutants(source))
    root = kernel.verify(directory)['root']
    chosen = _mutant_order(candidates, root)[:max_mutants]
    killed = 0
    survivors = []
    for index, (name, variant) in enumerate(chosen):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as room:
            shutil.copytree(directory, room, dirs_exist_ok=True)
            with open(core._safe(room, name), 'w', encoding='utf-8') as stream:
                stream.write(variant)
            if kernel.audit(room)['ok']:
                survivors.append(index)
            else:
                killed += 1
    result = {'mutants': len(chosen), 'killed': killed,
              'survivors': survivors, 'rate': killed / len(chosen) if chosen else 0.0}
    core._write_json(core._safe(directory, core.MUTATION_RESIDUE), result)
    return result
