import os, sys, json, subprocess, shutil, signal, time, math, re, importlib.util, tempfile, platform
from .core import *
from .core import _KEEP_ENV, _JAILED, _SHELL, _now, _write_json, _hash_file
_REQ_OPS = ('<=','>=','==','!=','~=','<','>')
_BWRAP_OK = None
_SB_OK = None

def _scrub_env(extra=None):
    e={k:v for k,v in os.environ.items() if k in _KEEP_ENV};e['PYTHONDONTWRITEBYTECODE']='1'
    if extra:e.update(extra)
    return e

def _bwrap_usable():
    global _BWRAP_OK
    if _BWRAP_OK is None:
        _BWRAP_OK=bool(shutil.which('bwrap')) and subprocess.run(['bwrap','--ro-bind','/','/','--unshare-net','true'],capture_output=True).returncode==0
    return _BWRAP_OK

def sandbox_backend():
    global _SB_OK
    if os.environ.get(_JAILED):return 'inherited'
    if sys.platform=='darwin' and shutil.which('sandbox-exec'):
        if _SB_OK is None:_SB_OK=subprocess.run(['sandbox-exec','-p','(version 1)(allow default)','true'],capture_output=True).returncode==0
        if _SB_OK:return 'seatbelt'
    return 'bubblewrap' if _bwrap_usable() else 'none'

def _quote_sb(s):return str(s).replace('\\','\\\\').replace('"','\\"')
def _sandbox_argv(cmd,d,backend=None,strict=False):
    b=backend or sandbox_backend();d=os.path.realpath(d)
    argv=[_SHELL,'-c',cmd]
    if b=='seatbelt':
        p='(version 1)(allow default)(deny network*)(deny file-write*)(allow file-write* (subpath "'+_quote_sb(d)+'") (subpath "/dev"))'
        return ['sandbox-exec','-p',p]+argv
    if b=='bubblewrap':return ['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--bind',d,d,'--unshare-net','--die-with-parent']+argv
    return argv

def _kill_tree(p):
    try:os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError:pass

def _run(argv,d,env=None,timeout=120):
    start=time.monotonic()
    p=subprocess.Popen(argv,cwd=d,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    status='ok'
    try:o,e=p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p);o,e=p.communicate();status='timeout'
    if p.returncode and status!='timeout':status='failed'
    return {'status':status,'returncode':p.returncode,'stdout':o,'stderr':e,'seconds':time.monotonic()-start}

def sandbox(cmd,d,env=None,timeout=120,strict=False):
    b=sandbox_backend(); e=_scrub_env(env)
    scratch=os.path.join(os.path.realpath(d),STORE,'scratch');os.makedirs(scratch,exist_ok=True)
    e.update(HOME=scratch,TMPDIR=scratch)
    if b in ('seatbelt','bubblewrap'):e[_JAILED]=b
    return _run(_sandbox_argv(cmd,d,b,strict),d,e,timeout),b

def gate_timeout(r=None):
    t=(r or {}).get('claim',{}).get('gate_timeout',GATE_TIMEOUT)
    cap=os.environ.get('RETICULI_GATE_TIMEOUT')
    return min(float(t),float(cap)) if cap else float(t)

def run_gate(cmd,d,recipe=None,strict=False,env=None):
    missing=preflight(recipe or {})
    if missing:return {'status':'environment','quarantine':None,'stdout':'','stderr':', '.join(missing),'returncode':1,'seconds':0}
    out,b=sandbox(cmd,d,env,gate_timeout(recipe),strict);out['quarantine']=b
    return out

def _ledger_path(d):return os.path.join(d,LEDGER)
def ledger(d,e):
    p=_ledger_path(d);os.makedirs(os.path.dirname(p),exist_ok=True)
    with open(p,'a',encoding='utf-8') as f:f.write(json.dumps(e,sort_keys=True)+'\n')
def ledger_events(d):
    try:
        with open(_ledger_path(d),encoding='utf-8') as f:
            out=[]
            for l in f:
                try:e=json.loads(l)
                except ValueError:continue
                if isinstance(e,dict):out.append(e)
            return out
    except OSError:return []

def cost(d):
    totals={}; discovery={}
    for e in ledger_events(d):
        if e.get('event')=='gate':continue
        dst=discovery if e.get('scope')=='discovery' else totals
        for k in COST_KEYS:
            v=e.get(k)
            if type(v) in (int,float) and math.isfinite(v) and v>=0:dst[k]=dst.get(k,0)+v
    if discovery:totals['discovery']=discovery
    return totals or None

def _in_band(a,b,t):return a==b if not a or not b else 1/t<=a/b<=t

def independence(d):
    es=[e for e in ledger_events(d) if e.get('event')=='producer']
    return {k:v for k,v in (es[-1] if es else {}).items() if k in ('vendor','model','blind','cutoff')}
def _independence_line(x):
    if x.get('vendor') and x.get('model'):return 'declared: '+x['vendor']+'/'+x['model']+', blind workspace; not proven'
    return 'unestablished; independence is not proven'

def _version_tuple(s):return tuple(int(x) for x in re.findall(r'\d+',s)[:3])
def _version_ok(have,op,want):
    a=_version_tuple(have);b=_version_tuple(want)
    return {'>=':a>=b,'<=':a<=b,'>':a>b,'<':a<b,'==':a[:len(b)]==b,'!=':a[:len(b)]!=b,'~=':a>=b and a[:1]==b[:1]}.get(op,False)
def _tool_version(n):
    if n in ('python','python3'):return platform.python_version()
    try:return subprocess.run([n,'--version'],capture_output=True,text=True,timeout=5).stdout
    except (OSError,subprocess.TimeoutExpired):return ''
def _have(s):
    m=re.match(r'^(.+?)(<=|>=|==|!=|~=|<|>)(.+)$',s)
    n=m[1] if m else s
    present=bool(shutil.which(n))
    if not present:
        try:present=importlib.util.find_spec(n) is not None
        except (ValueError,ModuleNotFoundError):pass
    return present and (not m or _version_ok(_tool_version(n),m[2],m[3]))
def preflight(r):return [s for s in r.get('claim',{}).get('requires',[]) if not _have(s)]
def _env_cache_dir():return os.environ.get('RETICULI_ENV_CACHE',os.path.join(tempfile.gettempdir(),'reticuli-environments'))
def furnish(r,d):
    name=r.get('claim',{}).get('environment')
    if not name:return None
    key=digest([_hash_file(os.path.join(d,name)),sys.executable,sys.platform])
    dest=os.path.join(_env_cache_dir(),key); marker=os.path.join(dest,'.ready')
    if not os.path.isfile(marker):
        os.makedirs(os.path.dirname(dest),exist_ok=True)
        p=_run([sys.executable,'-m','venv',dest],d,_scrub_env(),FURNISH_TIMEOUT)
        if p['status']!='ok':raise ClaimError('environment: '+p['stderr'])
        p=_run([os.path.join(dest,'bin','python'),'-m','pip','install','--require-hashes','--only-binary=:all:','-r',os.path.abspath(os.path.join(d,name))],d,_scrub_env(),FURNISH_TIMEOUT)
        if p['status']!='ok':raise ClaimError('environment: '+p['stderr'])
        open(marker,'w').close()
    return {'PATH':os.path.join(dest,'bin')+os.pathsep+os.environ.get('PATH','')}
