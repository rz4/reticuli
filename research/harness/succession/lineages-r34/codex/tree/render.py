import json, time, datetime
from ._kernel.core import dump_recipe, toml_value

def toml(x):return toml_value(x)
def short(s,n=12):return str(s)[:n]
def duration(s):return f'{s:.2f}s'
def ago(s):return str(s)
def paint(s,*args,**kwargs):return str(s)
def table(rows,*args,**kwargs):return '\n'.join('  '.join(map(str,r)) for r in rows)
def tree(rows,*args,**kwargs):return table(rows)
