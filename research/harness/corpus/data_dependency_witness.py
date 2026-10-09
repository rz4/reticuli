"""Witness: a claim with a MANIFEST-ONLY component (pulled data dependency,
no from-step) whose shipped bytes are forged. GATES COMPOSE says the deep
audit must refuse. Does this walker?"""
import os, shutil, subprocess, sys, tempfile
from reticuli import kernel, registry
NAME = sys.argv[1]
d = tempfile.mkdtemp()
try:
    # the component: produces data.txt via its gate
    lib = os.path.join(d, "libdata"); os.makedirs(lib)
    open(os.path.join(lib, "claim.toml"), "w").write(
        '[claim]\nname = "libdata"\n\n[[step]]\nkind = "gate"\noutput = "data.txt"\n'
        'run = "printf GOOD > data.txt"\nclass = "validated"\n')
    subprocess.run("printf GOOD > data.txt", shell=True, cwd=lib, check=True)
    rl = kernel.seal(lib)
    # the dependent: PINS data.txt as an input (no from-step), declares the
    # component in the manifest — the pulled-data-dependency shape
    app = os.path.join(d, "app"); os.makedirs(app)
    open(os.path.join(app, "data.txt"), "w").write("GOOD")
    open(os.path.join(app, "app_check.py"), "w").write(
        "assert open('data.txt').read()\nopen('APP_OK','w').write('ok\\n')\n")
    open(os.path.join(app, "claim.toml"), "w").write(
        '[claim]\nname = "app"\ninputs = ["data.txt", "app_check.py"]\n\n'
        '[[step]]\nkind = "gate"\noutput = "APP_OK"\nrun = "python3 app_check.py"\nclass = "validated"\n')
    subprocess.run("python3 app_check.py", shell=True, cwd=app, check=True, capture_output=True)
    shutil.copytree(lib, os.path.join(app, ".reticuli", "sealed", "libdata"))
    registry.seal_with(app, components=[{"input": "data.txt", "component": "libdata",
                                         "root": rl["root"], "output": "data.txt"}])
    clean = registry.audit_deep(app)
    # FORGE the shipped dependency bytes: app's own gate is blind (any content passes),
    # only the component's re-earned gate can see it
    open(os.path.join(app, "data.txt"), "w").write("FORGED")
    kernel.seal(app)  # reseal over the forged input (new root, self-consistent claim)
    forged = registry.audit_deep(app)
    print(f"{NAME}: clean ok={clean['ok']} ({len(clean.get('layers',[]))} layers) | "
          f"FORGED ok={forged['ok']} ({len(forged.get('layers',[]))} layers)"
          + ("   <<< FALSE PASS" if forged.get("ok") else "   (refused, correct)"))
finally:
    shutil.rmtree(d, ignore_errors=True)
