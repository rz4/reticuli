import json
import os
import hashlib
import copy
from . import recipe, core

def _is_valid_file(base: str, path: str) -> bool:
    if not path or os.path.isabs(path) or ".." in path.split(os.sep):
        return False
    parts = path.split(os.sep)
    current = base
    for part in parts:
        current = os.path.join(current, part)
        if os.path.islink(current):
            return False
    full_path = os.path.join(base, path)
    if not os.path.isfile(full_path):
        return False
    st = os.stat(full_path)
    if st.st_nlink != 1:
        return False
    return True

def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(', ', ': '), ensure_ascii=True).encode('utf-8')

def _recompute_root(path, parsed=None):
    if not parsed:
        parsed = recipe.load_recipe(path)
    parts = {}
    parts["digest"] = "sha256"
    
    recipe_dict = copy.deepcopy(parsed)
    fmt = recipe_dict.get("claim", {}).get("format", 1)
    
    if fmt >= 3:
        for step in recipe_dict.get("step", []):
            step.pop("guidance", None)
            step.pop("request", None)
            
    if fmt >= 4:
        if "step" in recipe_dict:
            recipe_dict["step"].sort(key=lambda s: canonical_json(s))
            
    parts["recipe"] = canonical_json(recipe_dict).decode("utf-8")
    
    inputs = recipe._inputs(path, parsed)
    for inp in inputs:
        if not _is_valid_file(path, inp):
            raise core.ClaimError(f"invalid input path {inp}")
        p = os.path.join(path, inp)
        parts["input:" + inp] = core._hash_file(p)
        
    gen_outs = set(recipe.generated_outputs(parsed))
    for step in parsed.get("step", []):
        out = step.get("output")
        if out and out not in gen_outs:
            if not _is_valid_file(path, out):
                raise core.ClaimError(f"invalid pinned path {out}")
            p = os.path.join(path, out)
            parts["pinned:" + out] = core._hash_file(p)
            
    return hashlib.sha256(canonical_json(parts)).hexdigest()

def test_vectors():
    vdir = "spec/vectors"
    if not os.path.exists(vdir):
        return
    for name in os.listdir(vdir):
        d = os.path.join(vdir, name)
        if os.path.isdir(d):
            exp_path = os.path.join(d, "expected-root")
            if os.path.exists(exp_path):
                with open(exp_path) as f:
                    expected = f.read().strip()
                try:
                    r = _recompute_root(d)
                    if r == expected:
                        print(f"PASS: {name}")
                    else:
                        print(f"FAIL: {name} got {r} expected {expected}")
                except Exception as e:
                    print(f"FAIL: {name} exception {e}")

test_vectors()

def _changed_parts(path, previous_parts):
    return []

def read_manifest(path):
    mpath = os.path.join(path, core.MANIFEST)
    if os.path.exists(mpath):
        with open(mpath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def seal(path):
    r = _recompute_root(path)
    parsed = recipe.load_recipe(path)
    manifest = {
        "name": parsed.get("claim", {}).get("name", ""),
        "root": r
    }
    mpath = os.path.join(path, core.MANIFEST)
    os.makedirs(os.path.dirname(mpath), exist_ok=True)
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

def verify(path):
    m = read_manifest(path)
    if not m:
        return {"ok": False, "recomputed": None}
    r = _recompute_root(path)
    if m.get("root") == r:
        return {"ok": True, "root": r}
    else:
        return {"ok": False, "recomputed": r, "root": m.get("root")}
