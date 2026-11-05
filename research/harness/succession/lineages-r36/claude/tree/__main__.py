"""`python3 -m reticuli` -- the same entry point the `ret` console script
binds to, so the module form and the installed form cannot diverge."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
