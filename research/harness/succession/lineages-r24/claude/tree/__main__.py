"""reticuli.__main__: `python3 -m reticuli` -- the CLI entrypoint.

Binds the same function object `reticuli.cli.main` exports, so the two
names are provably one implementation, not a wrapper around it.
"""
import sys

from reticuli.cli import main

if __name__ == "__main__":
    sys.exit(main())
