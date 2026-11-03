"""Sub-finding: can a CALLER relax a tolerance the CLAIM pinned?

The claim declares a tight band. M1 and M3 costs differ by much more than it
allows, so the declared condition should reject. Then the same comparison is
run with a caller-supplied wide band.
"""
import os, shutil, sys, tempfile, json
sys.path.insert(0, "src")
from reticuli import kernel

RECIPE = ('[claim]\nname = "tight"\ntolerance = 1.05\ninputs = ["check.py"]\n\n'
          '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
          '[[step]]\nkind = "gate"\noutput = "OK"\nclass = "validated"\n'
          'run = "python3 check.py && printf ok > OK"\n')
CHECK = ("from impl import answer\nassert answer == 42\n"
         "open('OK','w').write('ok')\n")

d = tempfile.mkdtemp(prefix="ovr-")
try:
    m1 = os.path.join(d, "m1"); os.makedirs(m1)
    for n, b in {"reticuli.toml": RECIPE, "check.py": CHECK,
                 "impl.py": "answer = 42\n", "OK": "ok"}.items():
        open(os.path.join(m1, n), "w").write(b)
    kernel.seal(m1)
    m2 = os.path.join(d, "m2"); shutil.copytree(m1, m2)

    prod = os.path.join(d, "p.py")
    open(prod, "w").write("open('impl.py','w').write('answer = 6 * 7\\n')\n")
    m3 = os.path.join(d, "m3")
    kernel.rebuild(m1, f"{sys.executable} {prod}", m3)

    # give M1 a ledger with a WILDLY different cost so the band is violated
    from reticuli._kernel.run import ledger
    ledger(m1, {"event": "oracle", "calls": 100, "seconds": 100.0})

    print("M1 cost:", kernel.cost(m1))
    print("M3 cost:", kernel.cost(m3))
    print("claim-declared tolerance: 1.05")
    print()
    a = kernel.crosscheck(m1, m2, m3)
    print(f"  no caller band   -> band={a['cost']['tolerance']}  "
          f"comparable={a['cost']['comparable']}  verdict={a['verdict']}  "
          f"rejected={a['rejected']}")
    b = kernel.crosscheck(m1, m2, m3, tolerance=10000.0)
    print(f"  caller band 10000-> band={b['cost']['tolerance']}  "
          f"comparable={b['cost']['comparable']}  verdict={b['verdict']}  "
          f"rejected={b['rejected']}")
    print()
    if a["verdict"] == "reject" and b["verdict"] != "reject":
        print("CONFIRMED: a caller widened a band the CLAIM pinned, turning a "
              "reject into a non-reject, with no change to the root.")
    else:
        print("not reproduced as a reject flip; see values above")
finally:
    shutil.rmtree(d, ignore_errors=True)
