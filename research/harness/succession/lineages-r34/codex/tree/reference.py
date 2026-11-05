"""The standalone identity command."""
import sys
from ._kernel.recipe import load_recipe
from ._kernel.identity import root as _root

def root(d):return _root(load_recipe(d),d)
if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='root':print(root(sys.argv[2]))
    else:raise SystemExit('usage: reference root DIRECTORY')
