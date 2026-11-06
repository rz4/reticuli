import os,sys,shutil,subprocess,time,shlex
from .. import kernel,hooks,feedback
from .._util import trace_append
_PRODUCER_PASSTHROUGH=('OPENAI_BASE_URL','RETICULI_PRICE','RETICULI_AGENT_TURNS')
_PRODUCERS={'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}
_CLI_PRODUCERS={'codex':'codex','claude':'claude'}
def _expand_producer(command):
    name=command.split(':')[0]
    if name not in _PRODUCERS and name not in _CLI_PRODUCERS: return command,None
    env={'PYTHONPATH':os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))}
    if name in _CLI_PRODUCERS:
        if not shutil.which(_CLI_PRODUCERS[name]): raise kernel.ClaimError(f'{name} missing on PATH')
    else:
        var=_PRODUCERS[name]
        if not os.environ.get(var): raise kernel.ClaimError(f'the {name} producer needs {var}')
        env[var]=os.environ[var]
    for k in _PRODUCER_PASSTHROUGH:
        if k in os.environ: env[k]=os.environ[k]
    return shlex.quote(sys.executable)+' -m reticuli.producers.'+name,env
def init(ws,no_agent=False,agent=None):
    os.makedirs(os.path.join(ws,'.reticuli'),exist_ok=True)
    p=os.path.join(ws,'.gitignore')
    with open(p,'a') as f: f.write('\n.reticuli/ledger.jsonl\n')
    if agent=='claude': hooks.install(ws)
    return {'ok':True,'path':ws}
def run(command,workspace):
    os.makedirs(workspace,exist_ok=True)
    trace_append(workspace,{'event':'bash','cmd':command,'ts':time.time(),'via':'shell'})
    return subprocess.run(command,shell=True,cwd=workspace).returncode
def _ensure(d): os.makedirs(d,exist_ok=True)
def _scan_workspace(d): return feedback.advise(d)
def _version_line(): return 'ret 6'
