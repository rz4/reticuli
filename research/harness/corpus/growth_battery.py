"""The growth battery: doubling ratios for every scaling operation.
Each probe times op at scale S and 2S; the ratio estimates the exponent,
host speed cancelling. Conforming band vs pathology, per axis."""
import os, shutil, subprocess, sys, tempfile, time
from reticuli import kernel, registry

NAME = sys.argv[1]
def T(fn):
    t = time.perf_counter(); fn(); return time.perf_counter() - t

def mk_claim(d, nfiles=1):
    os.makedirs(d, exist_ok=True)
    for i in range(nfiles):
        open(os.path.join(d, f"f{i}.py"), "w").write(f"x{i} = {i}\n")
    open(os.path.join(d, "check.py"), "w").write("open('OK','w').write('ok\\n')\n")
    inputs = ", ".join(f'"f{i}.py"' for i in range(nfiles))
    open(os.path.join(d, "claim.toml"), "w").write(
        f'[claim]\nname = "g"\ninputs = [{inputs}, "check.py"]\n\n'
        '[[step]]\nkind = "gate"\noutput = "OK"\nrun = "python3 check.py"\nclass = "validated"\n')
    subprocess.run("python3 check.py", shell=True, cwd=d, check=True, capture_output=True)

def probe_seal_files():
    out = []
    for N in (200, 400):
        d = tempfile.mkdtemp()
        try:
            mk_claim(os.path.join(d, "c"), N)
            out.append(T(lambda: kernel.seal(os.path.join(d, "c"))))
        finally: shutil.rmtree(d, ignore_errors=True)
    return out

def build_flat_chain(d, K):
    """components flat-stored, rich records — the audit_deep shape."""
    layers = []; prev_root = None
    for i in range(K):
        lay = os.path.join(d, f"l{i}")
        frm = f'from = "l{i-1}"\n' if layers else ""
        os.makedirs(lay)
        open(os.path.join(lay, "impl.py"), "w").write("v = 1\n")
        open(os.path.join(lay, "c.py"), "w").write(
            "from impl import v\nassert v == 1\nopen('OK','w').write('ok\\n')\n")
        open(os.path.join(lay, "claim.toml"), "w").write(
            f'[claim]\nname = "l{i}"\ninputs = ["c.py"]\n\n'
            f'[[step]]\nkind = "produce"\noutput = "impl.py"\n{frm}class = "generated"\n\n'
            '[[step]]\nkind = "gate"\noutput = "OK"\nrun = "python3 c.py"\nclass = "validated"\n')
        subprocess.run("python3 c.py", shell=True, cwd=lay, check=True, capture_output=True)
        store = os.path.join(lay, ".reticuli", "sealed"); os.makedirs(store, exist_ok=True)
        for anc in layers: os.symlink(anc, os.path.join(store, os.path.basename(anc)))
        r = kernel.seal(lay)
        if layers:
            registry.seal_with(lay, components=[{"input": "impl.py",
                "component": os.path.basename(layers[-1]), "root": prev_root, "output": "impl.py"}])
        prev_root = r["root"]; layers.append(lay)
    return layers[-1]

def probe_auditdeep_depth():
    out = []
    for K in (8, 16):
        d = tempfile.mkdtemp()
        try:
            top = build_flat_chain(d, K)
            out.append(T(lambda: registry.audit_deep(top)))
        finally: shutil.rmtree(d, ignore_errors=True)
    return out

def probe_pull_deps():
    out = []
    for K in (8, 16):
        d = tempfile.mkdtemp()
        try:
            top = build_flat_chain(d, K)
            ws = os.path.join(d, "ws"); os.makedirs(os.path.join(ws, ".reticuli"))
            out.append(T(lambda: registry.pull(top, ws)))
        finally: shutil.rmtree(d, ignore_errors=True)
    return out

def probe_detect_inputs():
    out = []
    for N in (50, 100):
        d = tempfile.mkdtemp()
        try:
            ws = os.path.join(d, "ws")
            lib = os.path.join(ws, ".reticuli", "sealed", "lib"); os.makedirs(lib)
            open(os.path.join(lib, "claim.toml"), "w").write(
                '[claim]\nname = "lib"\n\n[[step]]\nkind = "gate"\noutput = "d0.txt"\n'
                'run = "printf x0 > d0.txt"\nclass = "validated"\n')
            open(os.path.join(lib, "d0.txt"), "w").write("x0")
            kernel.seal(lib)
            names = []
            for i in range(N):
                open(os.path.join(ws, f"in{i}.txt"), "w").write(f"y{i}")
                names.append(f"in{i}.txt")
            out.append(T(lambda: registry.detect_components(ws, names)))
        finally: shutil.rmtree(d, ignore_errors=True)
    return out

def probe_ledger_appends():
    out = []
    from reticuli._kernel import run as runmod
    for N in (300, 600):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, ".reticuli"), exist_ok=True)
            def many():
                for i in range(N):
                    runmod.ledger(d, {"kind": "probe", "i": i})
            out.append(T(many))
        finally: shutil.rmtree(d, ignore_errors=True)
    return out

AXES = [("seal/files 200->400", probe_seal_files),
        ("auditdeep/depth 8->16", probe_auditdeep_depth),
        ("pull/deps 8->16", probe_pull_deps),
        ("detect/inputs 50->100", probe_detect_inputs),
        ("ledger/appends 300->600", probe_ledger_appends)]
for label, fn in AXES:
    try:
        a, b = fn()
        print(f"{NAME:10} {label:26} {a:7.2f}s -> {b:7.2f}s   ratio {b/max(a,1e-6):5.1f}")
    except Exception as e:
        print(f"{NAME:10} {label:26} DNF {type(e).__name__}: {str(e)[:60]}")
