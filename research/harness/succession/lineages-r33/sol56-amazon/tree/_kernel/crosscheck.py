"""Deterministic source mutation helpers used by the public kernel."""
from __future__ import annotations
import ast, hashlib, io, os, re, tokenize
from . import core
from . import run as _run_module
# Private residue paths and furnishing mechanics are implementation details.
# A producer reports usage before the store exists, and relative requirements
# entries are resolved from the claim carrying them.
core.USAGE = ".reticuli-usage.json"
_old_furnish = _run_module.furnish
def _claim_furnish(d, recipe=None):
    before=os.getcwd()
    try:
        os.chdir(os.path.abspath(os.fspath(d)))
        return _old_furnish(d,recipe)
    finally:
        os.chdir(before)
_run_module.furnish=_claim_furnish
_COMPARISON=(">","<",">=","<=","==","!=")
_INTERPRETERS=frozenset({'Rscript','awk','lua','python','python3','python2','node','ruby','perl','dash','deno','py.test','zsh','tclsh','php','sh','bash','py','pytest'})
_OPERATORS=frozenset({'&','\n','|','||','&&',';'})
_SKIP_VALUE=frozenset({'-m','-p','--module','-X','-c','-e'})
_ARITHMETIC=("+","-","*","/","//","%")
_OP_ALTS={'>':('>=','<'),'<':('<=','>'),'>=':('>','<'),'<=':('<','>'),'==':('!=',),'!=':('==',),'+':('-',),'-':('+',),'*':('+',)}
_OP_KIND={k:('comparison' if k in _COMPARISON else 'arithmetic') for k in _OP_ALTS}
_WORD_ALTS={'True':('False',),'False':('True',),'and':('or',),'or':('and',)}
_STRING_LITERAL=re.compile(r'''(?s)(?:[rubfRUBF]*)(?:''' + '"\'\'\'|\"\"\"|\'|\")')
def _label(path,kind,start,old,new): return f"{path}:{start}:{kind}:{old!r}->{new!r}"
def _splice(text,start,end,replacement): return text[:start]+replacement+text[end:]
def _edit(text,span,replacement): return _splice(text,span[0],span[1],replacement)
def _draw_order(seed,values): return sorted(values,key=lambda x:hashlib.sha256((seed+'\0'+repr(x)).encode()).digest())
def _mutant_order(seed,values): return _draw_order(seed,values)
def _named(node): return type(node).__name__
def _node_span(node,offsets=None):
    if offsets is None or not hasattr(node,'end_lineno'): return None
    return offsets[node.lineno-1]+node.col_offset,offsets[node.end_lineno-1]+node.end_col_offset
def _span_text(text,span): return '' if span is None else text[span[0]:span[1]]
def _docstring_spans(text):
    try: tree=ast.parse(text)
    except SyntaxError:return []
    offsets=[]; n=0
    for line in text.splitlines(keepends=True): offsets.append(n); n+=len(line)
    out=[]
    for node in ast.walk(tree):
        body=getattr(node,'body',None)
        if body and isinstance(body[0],ast.Expr) and isinstance(getattr(body[0],'value',None),ast.Constant) and isinstance(body[0].value.value,str):
            s=_node_span(body[0],offsets)
            if s:out.append(s)
    return out
def _token_mutants(text,path='source'):
    lines=text.splitlines(keepends=True); starts=[]; n=0
    for line in lines:starts.append(n);n+=len(line)
    out=[]
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            alts=_OP_ALTS.get(tok.string,()) or _WORD_ALTS.get(tok.string,())
            if not alts:continue
            a=starts[tok.start[0]-1]+tok.start[1]; b=starts[tok.end[0]-1]+tok.end[1]
            for new in alts:
                changed=_splice(text,a,b,new)
                try:compile(changed,path,'exec')
                except SyntaxError:continue
                out.append({'label':_label(path,'token',a,tok.string,new),'text':changed})
    except (tokenize.TokenError,IndentationError):pass
    return out
def _structural_mutants(text,path='source'):
    out=[]
    for m in re.finditer(r'(?m)^(\s*)return\s+([^\n#]+)',text):
        for value in ('0','1','None'):
            new=m.group(1)+'return '+value; changed=_splice(text,m.start(),m.end(),new)
            try:compile(changed,path,'exec')
            except SyntaxError:continue
            out.append({'label':_label(path,'return',m.start(),m.group(0),new),'text':changed})
    return out
def _mutants(text,path='source'):
    out=[];seen=set()
    for x in _token_mutants(text,path)+_structural_mutants(text,path):
        if x['text']!=text and x['text'] not in seen:seen.add(x['text']);out.append(x)
    return out
def _machine(value): return dict(value) if isinstance(value,dict) else {'value':value}
