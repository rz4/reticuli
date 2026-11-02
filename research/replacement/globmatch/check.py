"""globmatch boundary: match(pattern, name) -> bool, fnmatch-style globbing.

Pins the CORE of shell glob matching on cases.json, and -- after the first
blind rebuild delegated straight to the standard library (the lookup-table
move, jq gen-1's lesson on a new target) -- FORBIDS that shortcut. A
reconstruction must implement the matching itself, not import the answer. The
edge surface (negated classes, literal ], ranges, escaping, case) stays
unpinned: that is where a from-scratch matcher diverges, and where grade 2
looks.
"""
import json
import re as _re
from globmatch import match

# No importing the answer. fnmatch, the stdlib glob, and fnmatch.translate are
# the shortcut; a real reconstruction does the work.
_src = open("globmatch.py", encoding="utf-8").read()
for banned in ("fnmatch", "import glob", "from glob", "pathlib"):
    assert banned not in _src, f"globmatch.py must not use {banned!r}: implement the matcher"

cases = json.load(open("cases.json"))
for pattern, name, want in cases:
    got = match(pattern, name)
    assert got == want, f"match({pattern!r}, {name!r}) = {got}, want {want}"
print("all pass")
