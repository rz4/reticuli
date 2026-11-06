import os,sys
from ._kernel.core import dump_toml

def dump_recipe(r): return dump_toml(r)
def toml(r): return dump_toml(r)
def short(s,n=12): return str(s)[:n]
def duration(s): return f'{s:.2f}s'
def ago(s): return str(s)
def paint(s,*args,**kw):
    return '\033[32m'+str(s)+'\033[0m' if os.environ.get('RETICULI_COLOR')=='always' else str(s)
def table(rows,*args,**kw): return '\n'.join('  '.join(map(str,r)) for r in rows)
def tree(rows,*args,**kw): return table(rows)
