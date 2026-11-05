import os, sys, subprocess, shutil, time
from .. import kernel, hooks
from .._util import trace_append
_PRODUCER_PASSTHROUGH=('OPENAI_BASE_URL','RETICULI_PRICE','RETICULI_AGENT_TURNS')
_PRODUCERS={'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}
_CLI_PRODUCERS={'codex':'codex','claude':'claude'}

def _ensure(d):os.makedirs(os.path.join(d,kernel.STORE),exist_ok=True)
def init(d,no_agent=False,agent=None):
    _ensure(d);p=os.path.join(d,'.gitignore')
    existing=open(p).read() if os.path.isfile(p) else ''
    if 'ledger.jsonl' not in existing:
        with open(p,'a') as f:f.write('\n.reticuli/ledger.jsonl\n.reticuli/draft.jsonl\n')
    if agent=='claude':hooks.install(d)
    return {'path':d}
def run(command,workspace):
    _ensure(workspace);p=subprocess.run(command,shell=True,cwd=workspace,check=False)
    trace_append(workspace,{'event':'bash','cmd':command,'ts':time.time(),'via':'shell'})
    return p.returncode

def _expand_producer(value):
    name,_,model=value.partition(':')
    if name not in _PRODUCERS and name not in _CLI_PRODUCERS:return value,None
    env={k:os.environ[k] for k in _PRODUCER_PASSTHROUGH if k in os.environ}
    env['PYTHONPATH']=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if name in _PRODUCERS:
        key=_PRODUCERS[name]
        if not os.environ.get(key):raise kernel.ClaimError(f'the {name} producer needs {key}')
        env[key]=os.environ[key]
    elif not shutil.which(_CLI_PRODUCERS[name]):raise kernel.ClaimError('producer '+name+' is not on PATH')
    if model:env['RETICULI_MODEL']=model
    return sys.executable+' -m reticuli.producers.'+name,env

def _scan_workspace(d):
    return [os.path.relpath(os.path.join(b,f),d) for b,dirs,fs in os.walk(d) for f in fs if not os.path.relpath(b,d).startswith('.reticuli')]
def _version_line():return 'ret 6.0'
