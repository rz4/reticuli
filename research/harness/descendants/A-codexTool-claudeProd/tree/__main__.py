"""`python3 -m reticuli` — the same entrypoint `ret` is.

One entrypoint, one name: a module-run and an installed script must be the
same program, or a claim's gate that drives the tool one way would be
exercising something else.
"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
