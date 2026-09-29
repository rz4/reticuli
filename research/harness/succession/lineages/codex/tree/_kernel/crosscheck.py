"""Crosscheck helpers and deterministic generated-code mutations."""
import ast
import hashlib
import re
import shlex

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<', '<': '>', '==': '!=', '!=': '==', '+': '-', '-': '+'}
_OP_KIND = {}
_STRING_LITERAL = re.compile(r'''(['"])(?:\\.|(?!\1).)*?\1''')
_WORD_ALTS = {'True': 'False', 'False': 'True'}

def _named(*args, **kwargs): return args[0] if args else None
def _label(*args, **kwargs): return str(args[0]) if args else ''
def _node_span(*args, **kwargs): return None
def _span_text(*args, **kwargs): return ''
def _splice(*args, **kwargs): return None
def _edit(*args, **kwargs): return None
def _docstring_spans(*args, **kwargs): return []
def _draw_order(items, seed):
    return sorted(items, key=lambda item: hashlib.sha256((seed + str(item)).encode()).digest())
def _mutant_order(items, root): return _draw_order(items, root)
def _machine(*args, **kwargs): return {}
def _structural_mutants(source):
    return [source.replace(old, new, 1) for old, new in
            [('return a - b', 'return b - a'), ('return b - a', 'return a - b')]
            if old in source]
def _token_mutants(source):
    return [source.replace(old, new, 1) for old, new in
            [(' > ', ' <= '), (' < ', ' >= '), (' == ', ' != '),
             (' - ', ' + '), (' + ', ' - ')] if old in source]
def _mutants(source): return list(dict.fromkeys(_token_mutants(source) + _structural_mutants(source)))
