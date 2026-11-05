import os, ast
from .authoring import events, _tokens
from . import kernel

def advise(ws):
    es=events(ws);writes={e['path'] for e in es if e.get('event')=='write' and os.path.isfile(os.path.join(ws,e['path']))};commands=[e['cmd'] for e in es if e.get('event')=='bash']
    covered=set();outputs=[]
    for cmd in commands:
        ts=_tokens(cmd);covered.update(t for t in ts if t in writes)
        for i,t in enumerate(ts[:-1]):
            if t=='>':outputs.append(ts[i+1])
        for p in kernel.gate_deciders(cmd):
            try:
                tree=ast.parse(open(os.path.join(ws,p)).read())
                for node in ast.walk(tree):
                    mods=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
                    for m in mods:
                        if m:covered.add(m.replace('.','/')+'.py')
            except (OSError,SyntaxError):pass
    unresolved=sorted(writes-covered)
    return {'sealable':bool(commands) and not unresolved,'unresolved':unresolved,'outputs':outputs,'writes':sorted(writes),'events':es,'covered':sorted(covered)}
