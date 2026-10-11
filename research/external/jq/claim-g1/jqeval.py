# SEED SHIM (jig): delegates to the reference binary so the claim can
# seal warm. Excluded from the blind room with every other generated
# byte; a producer regrows this file from the criteria alone.
import subprocess, sys
r = subprocess.run(["/opt/homebrew/bin/jq", "-c", sys.argv[1]],
                   stdin=sys.stdin, text=True)
raise SystemExit(r.returncode)
