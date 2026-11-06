import os,json,time
from ._util import trace_append,write_json

def event(payload):
    ws=payload.get('cwd','.')
    if not os.path.isdir(os.path.join(ws,'.reticuli')): return None
    kind=payload.get('hook_event_name'); e=None
    if kind=='UserPromptSubmit': e={'event':'prompt','text':payload.get('prompt','')}
    if kind=='PostToolUse':
        tool=payload.get('tool_name'); data=payload.get('tool_input',{})
        if tool=='Bash': e={'event':'bash','cmd':data.get('command','')}
        elif tool in ('Write','Edit','Read'):
            p=os.path.abspath(data.get('file_path','')); base=os.path.abspath(ws)
            if not p.startswith(base+os.sep): return None
            e={'event':'read' if tool=='Read' else 'write','path':os.path.relpath(p,base)}
    if e:
        if payload.get('transcript_path'): trace_append(ws,{'event':'session','transcript':payload['transcript_path'],'ts':time.time(),'via':'hook'})
        e.update(ts=time.time(),via='hook'); trace_append(ws,e)
    return e
def install(ws):
    p=os.path.join(ws,'.claude','settings.json')
    try: v=json.load(open(p))
    except OSError: v={}
    hooks=v.setdefault('hooks',{}); wired=['UserPromptSubmit','PostToolUse']
    if all(k in hooks and 'reticuli' in json.dumps(hooks[k]) for k in wired): return {'status':'already wired','wired':wired}
    for k in wired: hooks.setdefault(k,[]).append({'hooks':[{'type':'command','command':'python3 -m reticuli hook'}]})
    write_json(p,v); return {'status':'wired','wired':wired}
