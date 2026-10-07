"""`python3 -m reticuli`: the CLI entrypoint (`spec/layers.md`'s surface layer)."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
