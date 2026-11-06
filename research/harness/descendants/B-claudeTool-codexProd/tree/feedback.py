import os,re
from .authoring import events,_exists

def advise(ws):
    ev=events(ws); cmds=[e['cmd'] for e in ev if e.get('event')=='bash']; writes={e['path'] for e in ev if e.get('event')=='write' and _exists(ws,e['path'])}
    covered=set()
    for p in writes:
        if any(p in cmd for cmd in cmds): covered.add(p); continue
        for e in writes:
            if e.endswith('.py') and any(e in cmd for cmd in cmds):
                if os.path.splitext(p)[0] in open(os.path.join(ws,e)).read(): covered.add(p)
    return {'sealable':bool(cmds) and writes<=covered,'unresolved':sorted(writes-covered),'observed':len(ev),'declared':len(covered),'events':ev}
