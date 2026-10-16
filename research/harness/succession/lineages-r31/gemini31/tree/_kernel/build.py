import os
import shutil
import json
import subprocess
import copy
from . import core, recipe, run, seal

def _authorized(): pass
def _compare_pin(): pass
def _materialize(): pass
def _produce(): pass
def _read_usage(): pass
def _ssh_verify(): pass
def _step_guidance(): pass

def audit(path):
    v = seal.verify(path)
    if not v["ok"]:
        return {"ok": False, "verdict": "verify failed"}
    parsed = recipe.load_recipe(path)
    res = {"ok": True, "gates": []}
    for gate in recipe.gates(parsed):
        cmd = gate["run"]
        r = run.run_gate(cmd, path, parsed)
        res["gates"].append(r)
        if r["status"] != "ok":
            res["ok"] = False
            res["verdict"] = "gate failed"
    if res["ok"]:
        res["verdict"] = "ok"
    return res

def _dict_to_toml(d):
    lines = []
    if "claim" in d:
        lines.append("[claim]")
        for k, v in d["claim"].items():
            if isinstance(v, str):
                lines.append(f'{k} = {json.dumps(v)}')
            elif isinstance(v, list):
                lines.append(f'{k} = {json.dumps(v)}')
            elif isinstance(v, int):
                lines.append(f'{k} = {v}')
        lines.append("")
    for step in d.get("step", []):
        lines.append("[[step]]")
        for k, v in step.items():
            if isinstance(v, str):
                lines.append(f'{k} = {json.dumps(v)}')
            elif isinstance(v, list):
                lines.append(f'{k} = {json.dumps(v)}')
            elif isinstance(v, int):
                lines.append(f'{k} = {v}')
        lines.append("")
    return "\n".join(lines)

def rebuild(path, producer_command, dst):
    os.makedirs(dst, exist_ok=True)
    parsed = recipe.load_recipe(path)
    fmt = parsed.get("claim", {}).get("format", 1)
    
    recipe_filename = core.RECIPE if os.path.exists(os.path.join(path, core.RECIPE)) else core.LEGACY_RECIPE
    if fmt >= 3:
        preimage = copy.deepcopy(parsed)
        for s in preimage.get("step", []):
            s.pop("guidance", None)
            s.pop("request", None)
        with open(os.path.join(dst, recipe_filename), "w", encoding="utf-8") as f:
            f.write(_dict_to_toml(preimage))
    else:
        shutil.copy2(os.path.join(path, recipe_filename), os.path.join(dst, recipe_filename))
        
    for inp in recipe._inputs(path, parsed):
        src_inp = os.path.join(path, inp)
        dst_inp = os.path.join(dst, inp)
        os.makedirs(os.path.dirname(dst_inp), exist_ok=True)
        shutil.copy2(src_inp, dst_inp)
        
    gen_outs = recipe.generated_outputs(parsed)
    outs_json = json.dumps(gen_outs)
    
    produces = recipe.produces(parsed)
    if not produces and gen_outs:
        produces = [{"output": g} for g in gen_outs]
        
    for s in produces:
        env = run._scrub_env(os.environ.copy())
        env["RETICULI_OUTPUT"] = os.path.abspath(os.path.join(dst, s["output"]))
        env["RETICULI_OUTPUTS"] = outs_json
        subprocess.run(producer_command, shell=True, cwd=dst, env=env, check=True)
        
    sb = "none"
    for gate in recipe.gates(parsed):
        cmd = gate["run"]
        r = run.run_gate(cmd, dst, parsed)
        if r["status"] != "ok":
            raise core.ClaimError(f"gate failed in rebuild: {r}")
        sb = r.get("quarantine", sb)
        
    seal.seal(dst)
    v = seal.verify(dst)
    return {"root": v["root"], "quarantine": sb}
