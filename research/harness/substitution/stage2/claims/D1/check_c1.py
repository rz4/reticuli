"""C_1: the dependency's boundary after the ratchet.

C_0 plus the two obligations the consumer turned out to rely on silently,
pinned after adjudication: numeric values coerce to int, and a duplicated
key resolves to its last assignment. Everything else is C_0 verbatim.
"""
import parser

CASES = [
    ("name = alice", {"name": "alice"}),
    ("a = x\nb = y", {"a": "x", "b": "y"}),
    ("", {}),
    ("n = 42", {"n": 42}),
    ("k = a\nk = b", {"k": "b"}),
]

for text, want in CASES:
    got = parser.parse(text)
    assert got == want, f"parse({text!r}) = {got!r}, want {want!r}"
print("c1-ok")
