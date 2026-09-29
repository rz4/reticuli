"""P's acceptance check: the consumer's contract, exercised through its
dependency's interface.

The consumer reads a deployment config and doubles the port. Its
correctness depends on behavior the dependency's own C_0 never pinned:
what a duplicate key means, and whether a numeric value arrives as a
number. The dependency (`parser.py`) is a generated file here — P's root
commits to this contract, not to any particular parser's bytes.
"""
import parser

cfg = parser.parse("port = 21\nport = 80")
got = cfg["port"] * 2
assert got == 160, f"the doubled port must be 160, got {got!r}"
print("p-ok")
