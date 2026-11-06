import os
from . import kernel
from ._kernel.core import _write_json,_now

def assess(d,mutants=10,**kw):
    v=kernel.verify(d); score=kernel.mutation_score(d,max_mutants=mutants)
    result={'root':v['root'],'measured':{'mutation_score':score},'not_measured':[],'not_applicable':[],'declared':kernel.load_recipe(d)['claim'],'gate':v['ok'],'when':_now()}
    _write_json(os.path.join(d,kernel.STORE,'assess.json'),result); return result
