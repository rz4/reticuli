"""C_0: the dependency's acceptance check.

The claim: `parser.py` in this directory defines

    parse(text: str) -> dict

which reads a small key = value configuration text, one assignment per line,
and returns the resulting dictionary. This check pins the happy path:
word-valued assignments with distinct keys, and the empty document.
"""
import parser

CASES = [
    ("name = alice", {"name": "alice"}),
    ("a = x\nb = y", {"a": "x", "b": "y"}),
    ("", {}),
]

for text, want in CASES:
    got = parser.parse(text)
    assert got == want, f"parse({text!r}) = {got!r}, want {want!r}"
print("c0-ok")
