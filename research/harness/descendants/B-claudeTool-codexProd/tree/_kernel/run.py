import os,sys,json,subprocess,shutil,time,signal,platform,re,importlib.util,tempfile
from .core import *
from .core import _KEEP_ENV,_JAILED,_now,_write_json,_judging_host,_hash_file
from .recipe import number
_REQ_OPS=('<=','>=','==','!=','~=','<','>')
_BWRAP_OK=None
_SEATBELT_OK=None
def _bwrap_usable():
    global _BWRAP_OK
    if _BWRAP_OK is None:
        _BWRAP_OK=bool(shutil.which('bwrap')) and subprocess.run(['bwrap','--ro-bind','/','/','--unshare-net','true'],capture_output=True).returncode==0
    return _BWRAP_OK
def sandbox_backend():
    global _SEATBELT_OK
    if os.environ.get(_JAILED): return 'inherited'
    if sys.platform=='darwin' and shutil.which('sandbox-exec'):
        if _SEATBELT_OK is None: _SEATBELT_OK=subprocess.run(['sandbox-exec','-p','(version 1)(allow default)','true'],capture_output=True).returncode==0
        if _SEATBELT_OK: return 'seatbelt'
        # Seatbelt refuses nesting; propagate the ambient confinement signal.
        os.environ[_JAILED]='inherited'
        return 'inherited'
    if _bwrap_usable(): return 'bubblewrap'
    return 'none'
def _quote_sb(s): return s.replace('\\','\\\\').replace('"','\\"')
def _sandbox_argv(cmd,d,strict=False):
    b=sandbox_backend(); d=os.path.realpath(d)
    argv=['/bin/sh','-c',cmd]
    if b=='seatbelt':
        profile='(version 1)(allow default)(deny network*)(deny file-write*)(allow file-write* (subpath "'+_quote_sb(d)+'") (subpath "/dev"))'
        argv=['sandbox-exec','-p',profile]+argv
    elif b=='bubblewrap': argv=['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--bind',d,d,'--unshare-net','--die-with-parent']+argv
    return argv,b
def sandbox(cmd='true',d='.',strict=False): return _sandbox_argv(cmd,d,strict)
def _scrub_env(extra=None):
    e={k:os.environ[k] for k in _KEEP_ENV if k in os.environ}; e.update(extra or {}); return e
def _kill_tree(p):
    try: os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError: pass
def _run(cmd,d,env=None,timeout=120):
    start=time.monotonic()
    p=subprocess.Popen(cmd,cwd=d,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try: out,err=p.communicate(timeout=timeout); status='ok' if p.returncode==0 else 'failed'
    except subprocess.TimeoutExpired:
        _kill_tree(p); out,err=p.communicate(); status='timeout'
    return {'status':status,'stdout':out,'stderr':err,'returncode':p.returncode,'elapsed':time.monotonic()-start}
def gate_timeout(r=None):
    t=(r or {}).get('claim',{}).get('gate_timeout',GATE_TIMEOUT)
    if os.environ.get('RETICULI_GATE_TIMEOUT'): t=min(t,float(os.environ['RETICULI_GATE_TIMEOUT']))
    return t
def run_gate(cmd,d,recipe=None,strict=False,env=None,**kw):
    argv,b=_sandbox_argv(cmd,d,strict); e=_scrub_env(env)
    scratch=os.path.join(os.path.realpath(d),STORE,'scratch'); os.makedirs(scratch,exist_ok=True)
    e.update(HOME=scratch,TMPDIR=scratch,PYTHONDONTWRITEBYTECODE='1')
    if b in ('seatbelt','bubblewrap'): e[_JAILED]=b
    result=_run(argv,d,e,gate_timeout(recipe)); result['quarantine']=b; return result
def _version_tuple(v): return tuple(int(x) for x in re.findall(r'\d+',v))
def _version_ok(v,op,w):
    a,b=_version_tuple(v),_version_tuple(w)
    return {'>=':a>=b,'<=':a<=b,'==':a==b,'!=':a!=b,'>':a>b,'<':a<b,'~=':a>=b}[op]
def _tool_version(name):
    if name in ('python','python3'): return platform.python_version()
    try: return subprocess.run([name,'--version'],capture_output=True,text=True,timeout=5).stdout
    except OSError: return ''
def _have(n):
    if shutil.which(n): return True
    try: return importlib.util.find_spec(n) is not None
    except (ImportError,ValueError): return False
def preflight(r):
    missing=[]
    for req in r.get('claim',{}).get('requires',[]):
        m=re.match(r'^(.*?)(<=|>=|==|!=|~=|<|>)(.+)$',req)
        name=m[1] if m else req
        if not _have(name) or (m and not _version_ok(_tool_version(name),m[2],m[3])): missing.append(req)
    return missing
def _ledger_path(d): return os.path.join(d,LEDGER)
def ledger(d,event):
    p=_ledger_path(d); os.makedirs(os.path.dirname(p),exist_ok=True)
    with open(p,'a') as f: f.write(json.dumps(event,sort_keys=True)+'\n')
def ledger_events(d):
    try:
        out=[]
        for line in open(_ledger_path(d)):
            try: out.append(json.loads(line))
            except ValueError: pass
        return out
    except OSError: return []
def cost(d):
    total={}; discovery={}
    for e in ledger_events(d):
        if not isinstance(e,dict): continue
        target=discovery if e.get('scope')=='discovery' else total
        for k in COST_KEYS:
            if number(e.get(k)): target[k]=target.get(k,0)+e[k]
    if discovery: total['discovery']=discovery
    return total or None
def independence(d):
    out={}
    for e in ledger_events(d):
        if e.get('event')=='producer': out.update({k:e[k] for k in ('vendor','model','blind','cutoff') if k in e})
    return out

def _independence_line(v):
    if v.get('vendor') and v.get('model'): return f'declared: {v["vendor"]}/{v["model"]}, blind workspace; not proven'
    return 'unestablished: independence not proven'
def _in_band(a,b,t): return a==b if not a or not b else 1/t<=a/b<=t
def _env_cache_dir(): return os.environ.get('RETICULI_ENV_CACHE',os.path.join(tempfile.gettempdir(),'reticuli-envs'))
def furnish(r,d):
    lock=r.get('claim',{}).get('environment')
    if not lock: return {}
    key=digest([_hash_file(os.path.join(d,lock)),sys.executable,sys.platform])
    cache=os.path.join(_env_cache_dir(),key); binary=os.path.join(cache,'bin')
    if not os.path.isfile(os.path.join(cache,'ready')):
        os.makedirs(cache,exist_ok=True)
        q=subprocess.run([sys.executable,'-m','venv',cache],capture_output=True,text=True)
        if q.returncode: raise ClaimError('environment: '+q.stderr)
        q=subprocess.run([os.path.join(binary,'python'),'-m','pip','install','--disable-pip-version-check','--require-hashes','--only-binary=:all:','-r',os.path.abspath(os.path.join(d,lock))],cwd=d,capture_output=True,text=True,timeout=FURNISH_TIMEOUT)
        if q.returncode: raise ClaimError('environment: '+q.stderr)
        open(os.path.join(cache,'ready'),'w').close()
    return {'PATH':binary+os.pathsep+os.environ.get('PATH','')}
