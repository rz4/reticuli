"""Three-machine comparison and deterministic mutation probes."""
from __future__ import annotations
import ast
import hashlib
import json
import os
import re
import shutil
import tempfile
from . import core, recipe, identity, seal, attest

_COMPARISON = ('>', '<', '>=', '<=', '==', '!=')
_INTERPRETERS = frozenset({'Rscript', 'awk', 'lua', 'python', 'python3', 'python2', 'node', 'ruby', 'perl', 'dash', 'deno', 'py.test', 'zsh', 'tclsh', 'php', 'sh', 'bash', 'py', 'pytest'})
_OPERATORS = frozenset({'&', '\n', '|', '||', '&&', ';'})
_SKIP_VALUE = frozenset({'-m', '-p', '--module', '-X', '-c', '-e'})
_ARITHMETIC = ('+', '-', '*', '/', '//', '%')
_OP_ALTS = {'>': '<', '<': '>', '>=': '<=', '<=': '>=', '==': '!=', '!=': '==', '+': '-', '-': '+'}
_OP_KIND = {x: 'operator' for x in _OP_ALTS}
_STRING_LITERAL = re.compile(r'''(['"])(?:\\.|(?!\1).)*?\1''')
_WORD_ALTS = {'True': 'False', 'False': 'True', 'and': 'or', 'or': 'and'}

def _label(name, index=0):
    return f'{name}:{index}'
def _named(path):
    return os.path.basename(os.fspath(path))
def _node_span(node):
    return (node.lineno, node.col_offset, getattr(node, 'end_lineno', node.lineno), getattr(node, 'end_col_offset', node.col_offset))
def _span_text(source, span):
    lines=source.splitlines(keepends=True)
    a,b,c,d=span
    return ''.join(lines[a-1:c])[b:d] if a==c else lines[a-1][b:]+''.join(lines[a:c-1])+lines[c-1][:d]
def _splice(source, start, end, replacement):
    return source[:start]+replacement+source[end:]
def _edit(source, old, new):
    return source.replace(old,new,1)
def _docstring_spans(source):
    try: tree=ast.parse(source)
    except SyntaxError: return []
    result=[]
    for node in ast.walk(tree):
        body=getattr(node,'body',None)
        if isinstance(body,list) and body and isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str):
            result.append(_node_span(body[0]))
    return result

def _structural_mutants(source):
    result=[]
    for old,new in _OP_ALTS.items():
        pat=r'(?<![\w])'+re.escape(old)+r'(?![\w])' if old[0].isalnum() else re.escape(old)
        for match in list(re.finditer(pat,source))[:3]:
            changed=_splice(source,match.start(),match.end(),new)
            try: ast.parse(changed)
            except SyntaxError: continue
            result.append(changed)
    for old,new in _WORD_ALTS.items():
        for match in list(re.finditer(r'\b'+old+r'\b',source))[:3]:
            changed=_splice(source,match.start(),match.end(),new)
            try: ast.parse(changed)
            except SyntaxError: continue
            result.append(changed)
    return result

def _token_mutants(source):
    result=[]
    for match in re.finditer(r'\b\d+\b',source):
        changed=_splice(source,match.start(),match.end(),str(int(match.group())+1))
        try: ast.parse(changed)
        except SyntaxError: continue
        result.append(changed)
    return result

def _draw_order(items, seed):
    return sorted(items,key=lambda x: hashlib.sha256((str(seed)+repr(x)).encode()).hexdigest())
def _mutant_order(items, seed):
    return _draw_order(items,seed)
def _mutants(source):
    return list(dict.fromkeys(_structural_mutants(source)+_token_mutants(source)))
def _machine(path):
    return os.path.realpath(os.fspath(path))

def gate_deciders(command):
    import shlex
    result=[]
    for fragment in re.split(r'&&|\|\||[;|&\n]',command):
        try: words=shlex.split(fragment)
        except ValueError: continue
        if not words: continue
        first=words[0]
        if first in _INTERPRETERS:
            if '-m' in words:
                i=words.index('-m')
                if i+1<len(words) and words[i+1] in ('pytest','unittest'):
                    result += [w for w in words[i+2:] if not w.startswith('-')]
                elif i+1<len(words): result.append(words[i+1])
            elif first in ('pytest','py.test'):
                result += [w for w in words[1:] if not w.startswith('-')]
            else:
                for w in words[1:]:
                    if w.startswith('-'): continue
                    result.append(w); break
        elif first.startswith('./'):
            result.append(first[2:])
    return list(dict.fromkeys(result))

def vacuous_gates(parsed):
    generated=set(recipe.generated_outputs(parsed))
    inputs=set(parsed.get('claim',{}).get('inputs',[]))
    result=[]
    for gate in recipe.gates(parsed):
        deciders=gate_deciders(gate['run'])
        if deciders and all(d in generated and d not in inputs for d in deciders):
            result.append(gate['output'])
    return result

def mutation_score(directory, max_mutants=core.MUTANT_CEILING):
    from reticuli import kernel
    path=os.path.realpath(os.fspath(directory))
    parsed=recipe.load_recipe(path)
    seed=seal.verify(path)['root']
    candidates=[]
    for step in recipe.produces(parsed):
        if step.get('class','generated') not in ('generated','free') or 'from' in step: continue
        name=step['output']
        if not name.endswith('.py'): continue
        target=core._safe(path,name)
        if not os.path.isfile(target): continue
        with open(target,encoding='utf-8') as f: source=f.read()
        candidates += [(name,x) for x in _mutants(source)]
    chosen=_mutant_order(candidates,seed)[:max_mutants]
    survivors=[]
    for idx,(name,content) in enumerate(chosen):
        with tempfile.TemporaryDirectory(prefix='reticuli-mutant-') as room:
            shutil.copytree(path,room,dirs_exist_ok=True)
            with open(core._safe(room,name),'w',encoding='utf-8') as f:f.write(content)
            result=kernel.audit(room)
            if result['ok']: survivors.append(_label(name,idx))
    count=len(chosen)
    result={'mutants':count,'killed':count-len(survivors),'survivors':survivors,'rate':(count-len(survivors))/count if count else 0.0}
    core._write_json(core._safe(path,core.MUTATION_RESIDUE),result)
    return result
