"""Performance assay: every realization runs the same workload as the tool.
Median of 3 per op. Ops: seal, verify, audit (sandboxed gate), rebuild
(printf producer), audit_deep (nested 2-layer, so nesting walkers resolve)."""
import importlib, json, os, shutil, statistics, subprocess, sys, tempfile, time

NAME = sys.argv[1]          # label
# tree is already on sys.path as `reticuli` via PYTHONPATH
from reticuli import kernel, registry

def mk_claim(d):
    os.makedirs(d)
    open(os.path.join(d,"impl.py"),"w").write("v = 1\n")
    open(os.path.join(d,"check.py"),"w").write("from impl import v\nassert v==1\nopen('OK','w').write('ok\\n')\n")
    open(os.path.join(d,"claim.toml"),"w").write(
        '[claim]\nname = "perf"\ninputs = ["check.py"]\n\n'
        '[[step]]\nkind = "produce"\noutput = "impl.py"\nclass = "generated"\n\n'
        '[[step]]\nkind = "gate"\noutput = "OK"\nrun = "python3 check.py"\nclass = "validated"\n')
    subprocess.run("python3 check.py", shell=True, cwd=d, check=True, capture_output=True)

def timed(fn, reps=3):
    xs = []
    for _ in range(reps):
        t = time.perf_counter(); fn(); xs.append(time.perf_counter()-t)
    return round(statistics.median(xs), 3)

res = {"name": NAME}
base = tempfile.mkdtemp(prefix=f"perf-{NAME}-")
try:
    # seal (fresh claim each rep)
    def op_seal():
        d = os.path.join(base, f"s{time.monotonic_ns()}"); mk_claim(d); kernel.seal(d)
        op_seal.last = d
    res["seal"] = timed(op_seal)
    sealed = op_seal.last
    res["verify"] = timed(lambda: kernel.verify(sealed))
    res["audit"]  = timed(lambda: kernel.audit(sealed))
    def op_rebuild():
        out = os.path.join(base, f"r{time.monotonic_ns()}")
        kernel.rebuild(sealed, "printf 'v = 1\\n' > impl.py", out)
    try:
        res["rebuild"] = timed(op_rebuild)
    except Exception as e:
        res["rebuild"] = f"DNF: {type(e).__name__}"
    # nested composed claim for audit_deep (parent carries child nested)
    child = os.path.join(base, "child"); mk_claim(child); rc = kernel.seal(child)
    parent = os.path.join(base, "parent"); mk_claim(parent)
    shutil.copytree(child, os.path.join(parent, ".reticuli", "sealed", "perf-child"))
    try:
        from reticuli.registry import seal_with
        seal_with(parent, components=[{"input":"impl.py","component":"perf-child",
                                       "root":rc["root"],"output":"impl.py"}])
        try:
            res["audit_deep"] = timed(lambda: registry.audit_deep(parent))
        except Exception as e:
            res["audit_deep"] = f"DNF: {type(e).__name__}"
    except Exception as e:
        res["audit_deep"] = f"SETUP-DNF: {type(e).__name__}"
finally:
    shutil.rmtree(base, ignore_errors=True)
print(json.dumps(res))
