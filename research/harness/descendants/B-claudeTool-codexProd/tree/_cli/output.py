import json,sys,os

def _err(verb,fact): print(f'ret: {verb}: {fact}',file=sys.stderr)
def _finish(command,data,ok,status,args,renderer=None):
    if getattr(args,'json',False): print(json.dumps({'command':command,'ok':bool(ok),'status':status,'root':data.get('root'),'data':data},sort_keys=True))
    elif renderer: renderer(data,args)
    return 0 if ok else 1
def _line(s): print(s)
def _rel(p): return os.path.relpath(p)
def _warn_block(s): print(s,file=sys.stderr)
def _confirm(s): return input(s).lower() in ('y','yes')
class _Progress:
    def __init__(self,*a,**kw): pass
    def __enter__(self): return self
    def __exit__(self,*a): pass
