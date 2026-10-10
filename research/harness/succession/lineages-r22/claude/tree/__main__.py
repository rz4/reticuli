"""`python3 -m reticuli ...` -- the same entrypoint `reticuli.cli` exposes."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
