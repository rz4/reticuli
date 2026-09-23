#!/bin/sh
# Finding A reproduction. Requires `ret` on PATH. Run in a scratch copy.
set -e
d=$(mktemp -d); cp check_guard.py reticuli.toml "$d/"; cd "$d"; printf x > impl.txt
ret pack . >/dev/null; echo "sealed root: $(python3 -c "import json;print(json.load(open('.reticuli/manifest.json'))['root'])")"
ret verify . && echo "verify (yes): pass"
ret audit . >/dev/null 2>&1 && echo "audit  (yes): PASS" || echo "audit  (yes): fail"
sed -i '' 's/guidance = "yes"/guidance = "no"/' reticuli.toml 2>/dev/null || sed -i 's/guidance = "yes"/guidance = "no"/' reticuli.toml
ret verify . && echo "verify (no):  pass  <- root unchanged; guidance not in root"
ret audit . >/dev/null 2>&1 && echo "audit  (no):  PASS" || echo "audit  (no):  FAIL  <- same root, acceptance flipped"
