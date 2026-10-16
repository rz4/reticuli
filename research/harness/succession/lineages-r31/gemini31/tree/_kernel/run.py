import os
import sys
import subprocess
import tempfile
import json
import shutil

_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = type(None)

def _bwrap_usable(): pass
def _env_cache_dir(): pass
def _have(cmd): pass
def _in_band(): pass
def _independence_line(): pass
def _kill_tree(): pass

def _ledger_path(d):
    return os.path.join(d, ".reticuli", "ledger.jsonl")

def _quote_sb(): pass

def _run(): pass

def _sandbox_argv(d): pass

def _scrub_env(env=None):
    if env is None: env = os.environ
    return {k: v for k, v in env.items() if k in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "RETICULI_JAILED", "RETICULI_GATE_TIMEOUT")}

def _tool_version(): pass
def _version_ok(): pass
def _version_tuple(): pass

def cost(d):
    calls = 0
    tokens = 0
    for ev in ledger_events(d):
        calls += ev.get("calls", 0)
        tokens += ev.get("tokens", 0)
    return {"calls": calls, "tokens": tokens}

def furnish(): pass

def gate_timeout(claim):
    cap = os.environ.get("RETICULI_GATE_TIMEOUT")
    if cap is not None:
        return float(cap)
    if claim and "claim" in claim and "gate_timeout" in claim["claim"]:
        return float(claim["claim"]["gate_timeout"])
    return 60.0

def independence(): pass

def ledger(d, event):
    path = _ledger_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(event) + "\n")

def ledger_events(d):
    path = _ledger_path(d)
    if not os.path.exists(path): return []
    res = []
    with open(path) as f:
        for line in f:
            if line.strip(): res.append(json.loads(line))
    return res

def preflight(recipe): pass

def run_gate(cmd, d, claim):
    sb = sandbox_backend()
    timeout = gate_timeout(claim)
    
    env = _scrub_env()
    try:
        res = subprocess.run(cmd, shell=True, cwd=d, env=env, timeout=timeout)
        if res.returncode == 0:
            status = "ok"
        else:
            status = "failed"
    except subprocess.TimeoutExpired:
        status = "timeout"
        
    return {"status": status, "quarantine": sb}

def sandbox(): pass

def sandbox_backend():
    return "none"
