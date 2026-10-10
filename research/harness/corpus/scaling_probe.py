"""Chain-build scaling: time building a K-layer self-claim-shaped chain
(each layer carries all lower modules, uniform glob patterns) with THIS
realization's pack/seal. Doubling ratio t(2K)/t(K) estimates the exponent,
host speed cancelling."""
import os, shutil, subprocess, sys, tempfile, time
from reticuli import kernel, pack

NAME = sys.argv[1]
def build_chain(K):
    d = tempfile.mkdtemp(prefix=f"scal-{K}-")
    t0 = time.perf_counter()
    try:
        prev = None; prev_root = None; layers = []
        for i in range(K):
            room = os.path.join(d, f"lay{i}"); os.makedirs(os.path.join(room, "pkg"))
            # layer i carries all lower modules + adds one (selfclaim's shape)
            for j in range(i + 1):
                open(os.path.join(room, "pkg", f"m{j}.py"), "w").write(f"v{j} = {j}\n")
            open(os.path.join(room, "check.py"), "w").write(
                f"import sys\nsys.path.insert(0,'pkg')\nimport m{i}\nopen('OK','w').write('ok\\n')\n")
            subprocess.run("python3 check.py", shell=True, cwd=room, check=True, capture_output=True)
            comp = None if prev is None else {"name": os.path.basename(prev), "claim": prev,
                                              "outputs": [f"pkg/m{j}.py" for j in range(i)]}
            pack.pack(room, f"lay{i}", generated=["pkg/*.py", "pkg/sub/*.py"],
                      inputs=["check.py"], gate="python3 check.py", gate_output="OK",
                      component=comp, claim_format=4)
            store = os.path.join(room, ".reticuli", "sealed"); os.makedirs(store, exist_ok=True)
            for anc in layers:
                link = os.path.join(store, os.path.basename(anc))
                if not os.path.exists(link): os.symlink(anc, link)
            prev, layers = room, layers + [room]
        return time.perf_counter() - t0
    finally:
        shutil.rmtree(d, ignore_errors=True)

for K in (4, 8, 16):
    t = build_chain(K)
    print(f"{NAME} K={K:3} t={t:6.2f}s")
