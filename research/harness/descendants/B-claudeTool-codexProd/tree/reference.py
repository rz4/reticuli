"""Identity command line."""
from ._kernel.recipe import load_recipe
from ._kernel.identity import root as _root

def root(d): return _root(load_recipe(d),d)
if __name__=='__main__':
    import sys
    print(root(sys.argv[2]))
