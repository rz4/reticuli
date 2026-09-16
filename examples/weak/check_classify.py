"""The acceptance test, as a model wrote it alongside the implementation.

It passes. It is also fitted to the code: it names one value per branch and
never probes where the branches actually change. Everything about it looks
reasonable, which is the point.
"""
import sys

sys.path.insert(0, ".")
from classify import classify

assert classify(5) == "low"
assert classify(50) == "medium"
assert classify(500) == "high"
print("classify-ok (3 cases)")
with open("OK", "w") as f:
    f.write("ok\n")
