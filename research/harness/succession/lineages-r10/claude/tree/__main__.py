"""`python3 -m reticuli`: the standard module-as-script entry point."""
import sys

from reticuli.cli import main

if __name__ == "__main__":
    sys.exit(main())
