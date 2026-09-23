"""Finding A reproduction: a gate that reads its own producer guidance.

At format 3 the guidance is stripped from the root, so editing it must not move
the identity. But the recipe is materialized into the judging room WITH its
guidance, so this gate can read it — and accept or reject based on a byte the
root does not cover.
"""
import sys
import tomllib

step0 = tomllib.load(open("reticuli.toml", "rb"))["step"][0]
guidance = step0.get("guidance", step0.get("request", ""))
if guidance == "yes":
    open("OK", "w").write("ok")
else:
    print(f"gate refuses: guidance is {guidance!r}, not 'yes'", file=sys.stderr)
    sys.exit(1)
