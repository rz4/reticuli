import os, sys, json

def _err(verb,message):print(f'ret: {verb}: {message}',file=sys.stderr)
def _finish(command,data,ok,status,args,renderer=None):
    if getattr(args,'json',False):print(json.dumps({'command':command,'ok':bool(ok),'status':status,'root':data.get('root'),'data':data}))
    elif getattr(args,'verbose',False):
        if renderer:renderer(data)
        else:print('['+command+']\n'+json.dumps(data,sort_keys=True))
    elif not ok:_err(command,status+'; hint: inspect the claim and restore its declared files')
    return 0 if ok else 1

def _line(*x):print(*x)
def _rel(p):return os.path.relpath(p)
def _confirm(prompt):return input(prompt).lower() in ('y','yes')
def _warn_block(message):print(message,file=sys.stderr)
class _Progress:
    def __init__(self,*a,**kw):pass
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def __call__(self,*a):pass
