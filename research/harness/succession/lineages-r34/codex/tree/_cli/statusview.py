import os
from .. import kernel, feedback, registry
from ..authoring import events
from .views import _claim_view
_DECLARED_ROLE={'generated':'free','validated':'verdict','pinned':'criterion','carried':'carried'}
def _colored(s):return '\033[32m'+s+'\033[0m' if os.environ.get('RETICULI_COLOR')=='always' else s

def _t_status_claim(v):
    print(_colored(v['name']+' identity '+('fresh' if v['ok'] else 'broken')+' '+v['root'][:12]))
    print('audited '+(str(v['audited'].get('when'))+' on this machine' if v.get('audited') else 'unknown'))
    print('signed '+str(v.get('signatures',0))+' statement(s)')
    if v.get('cost'):print('cost '+str(v['cost']))
    print('next '+v['next'])
def _ledger_status_claim(v):
    _t_status_claim(v);print('fixed criteria\ndeciding '+('measured' if v.get('deciding') else 'unknown')+'\nfree generated\nrecorded assess, a receipt, not a verdict\nunknown independence')
def _v_status_claim(v):_ledger_status_claim(v)
def _files_claim(d):
    r=kernel.load_recipe(d)
    for n in r['claim'].get('inputs',[]):print(n,'pinned criterion')
    for s in r.get('step',[]):
        cl=s.get('class','generated' if s['kind']=='produce' else 'pinned');print(s['output'],cl,_DECLARED_ROLE.get(cl,'criterion'))
    print('next '+_claim_view(d)['next'])
def _r_tree(d):
    r=kernel.load_recipe(d);print(_colored('layers='+str(len(kernel.read_manifest(d).get('components',[]))+1)))
    for s in r.get('step',[]):
        label='generated' if s.get('class')=='generated' else 'pinned'
        print(_colored(s['output']) if os.environ.get('RETICULI_COLOR')=='always' else label.ljust(11)+s['output'])
    print('next '+_claim_view(d)['next'])
def _r_structure(d):_r_tree(d)
def _r_status_draft(d,all_=False):
    a=feedback.advise(d);es=a['events']
    if not all_:print('draft observed='+str(len(es))+' declared='+str(len(a['writes']))+' unresolved='+str(len(a['unresolved']))+' '+('packable' if a['sealable'] else 'undeclared'))
    else:
        print('path observed declared evidence')
        known={e.get('path'):e for e in es if e.get('path')}
        for n in sorted(set(os.listdir(d))|set(known)):
            if n.startswith('.'):continue
            e=known.get(n,{});ev=e.get('event','-');cl='generated' if ev=='write' else '-'
            print(n,ev,cl,e.get('via','-'),'gate' if n in a['covered'] else '')
    print('next ret pack --accept <verdict> -o <claim>')
def _r_claims(ws):
    for c in registry.claims(ws):print(c['name'],c['root'],c['phase'])
def _r_deps(ws):print(registry.deps(ws))
