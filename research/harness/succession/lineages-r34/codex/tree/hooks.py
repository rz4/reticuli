import os, json, time
from ._util import trace_append, write_json

def event(payload):
    ws=payload.get('cwd','.')
    if not os.path.isdir(os.path.join(ws,'.reticuli')):return None
    name=payload.get('hook_event_name');e=None
    if name=='UserPromptSubmit':e={'event':'prompt','text':payload.get('prompt','')}
    elif name=='PostToolUse':
        tool=payload.get('tool_name');args=payload.get('tool_input',{})
        if tool in ('Write','Edit','Read'):
            p=os.path.abspath(os.path.join(ws,args.get('file_path','')));base=os.path.abspath(ws)
            if not p.startswith(base+os.sep):return None
            e={'event':'read' if tool=='Read' else 'write','path':os.path.relpath(p,base)}
        elif tool=='Bash':e={'event':'bash','cmd':args.get('command','')}
    if e:
        if payload.get('transcript_path'):trace_append(ws,{'event':'session','transcript':payload['transcript_path'],'ts':time.time(),'via':'hook'})
        e.update(ts=time.time(),via='hook');trace_append(ws,e)
    return e

def install(ws):
    p=os.path.join(ws,'.claude','settings.json')
    try:doc=json.load(open(p))
    except (OSError,ValueError):doc={}
    hooks=doc.setdefault('hooks',{})
    names=['UserPromptSubmit','PostToolUse'];changed=False
    for n in names:
        if not any('reticuli' in json.dumps(x) for x in hooks.get(n,[])):
            hooks.setdefault(n,[]).append({'hooks':[{'type':'command','command':'python3 -m reticuli hook'}]});changed=True
    if changed:write_json(p,doc)
    return {'wired':names,'status':'wired' if changed else 'already wired'}
