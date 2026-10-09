"""`python3 -m reticuli` -- the CLI entrypoint (spec/layers.md: surface)."""
import sys

from reticuli import cli

main = cli.main

if __name__ == "__main__":
    sys.exit(main())
