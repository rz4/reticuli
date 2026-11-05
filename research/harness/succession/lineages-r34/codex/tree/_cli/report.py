from .._kernel.core import toml_value

def _clean(v):
    if v is None:return 'unknown'
    if isinstance(v,dict):return {k:_clean(x) for k,x in v.items()}
    if isinstance(v,list):return [_clean(x) for x in v]
    return v
def _row(k,v):return k+' = '+toml_value(_clean(v))
def _when(x):return str(x)
def _generic_contract(data,section='result'):
    print('['+section+']')
    for k,v in data.items():
        if v is not None:print(_row(k,v))
def _r_verify(d):_generic_contract(d,'verify')
def _r_audit(d):_generic_contract(d,'audit');print('reproduced' if d.get('ok') else d.get('verdict','failed'))
def _r_assess(d):_generic_contract(d,'assess')
def _r_rebuild(d):_generic_contract(d,'rebuild')
def _r_seal(d):_generic_contract(d,'seal')
def _r_crosscheck(d):_generic_contract(d,'crosscheck');_generic_contract(d.get('cost',{}),'cost')
def _r_record(d):_generic_contract(d,'record')
def _r_sign(d):_generic_contract(d,'sign')
def _r_export(d):_generic_contract(d,'export')
def _r_pack(d):_generic_contract(d,'pack')
def _r_attest(d):_generic_contract(d,'attest')
def _r_attest_check(d):_generic_contract(d,'attest')
def _r_hooks(d):_generic_contract(d,'hooks')
def _r_import(d):_generic_contract(d,'import')
def _r_init(d):_generic_contract(d,'init')
def _r_pull(d):_generic_contract(d,'pull')
def _r_review(d):_generic_contract(d,'review')
def _r_sign_check(d):_generic_contract(d,'sign')
def _t_init(d):print('initialized '+d['path'])
