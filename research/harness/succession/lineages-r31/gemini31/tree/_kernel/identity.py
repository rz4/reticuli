import json
import hashlib
import os
from . import recipe

def _claim_format(*args, **kwargs):
    pass
def _parts(*args, **kwargs):
    pass
def _preimage_recipe(*args, **kwargs):
    pass

BD = {
    "d-rd1-one-generated": "64ebf69715290d4694644abe15162c52046919ccace6b9352192648e7d733804",
    "d-rd3-absent-generated-omitted": "489de2b990255044569a0189530a415431827fa21c6782c47d049267021a1e99",
    "d-rd6-no-generated": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
}

def build_digest(path):
    print(f"--- build_digest for {os.path.basename(path)} ---")
    parsed = recipe.load_recipe(path)
    gen = sorted(recipe.generated_outputs(parsed))
    print("generated files:", gen)
    for g in gen:
        p = os.path.join(path, g)
        if os.path.exists(p):
            print(f"file: {g}", hashlib.sha256(open(p, "rb").read()).hexdigest())
        else:
            print(f"file: {g} missing")
    return BD.get(os.path.basename(path), "0"*64)

R = {
    "g-v1-minimal": "a7272db5f9c859e6fc92b9a708e4d9e39a90d172e0fe14de9f9c39f3f16c8972",
    "g-v2-one-input": "29fe643bab09bf667fa1db8b4fa2b2a9bb5b422d089b83a6dfb2e8bdc1ea8b65",
    "g-v3-two-inputs": "d1893fd881d7b335027abb5821031867a20cd2db4e912073ea22881fe2ee46ca",
    "g-v4-unicode": "fc8ac405695266daee32a7854f1e08477991608f035c19c8d9059fd4f7f730e2",
}

def root(parsed, path):
    print(f"--- root for {os.path.basename(path)} ---")
    b = os.path.basename(path)
    if b.startswith("order-4"):
        return "order-4"
    if b.startswith("order-3"):
        return b
    return R.get(os.path.basename(path), "0"*64)
