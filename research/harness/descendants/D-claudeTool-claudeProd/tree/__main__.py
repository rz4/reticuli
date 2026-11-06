"""`python3 -m reticuli` -- the entrypoint, and nothing else."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
