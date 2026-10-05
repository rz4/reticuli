import os
with open("impl.py") as f:
    ns = {}
    exec(f.read(), ns)
assert ns["double"](4) == 8, "double must double"
assert ns["double"](0) == 0
with open("OK", "w") as f:
    f.write("ok\n")
print("toy gate: pass")
