"""Grade 2 on the closure trials, loaded the one way that is honest.

A first pass at this measurement fell into the import-resolution trap the
reconstruct-codebase skill documents, and the fall is half the finding. Two
of the three trial kernels import their internals RELATIVELY (`from ._kernel
import ...`); `r24-claude` imports them ABSOLUTELY, `from reticuli._kernel
import ...`. Loaded under the package name `tree`, r24's absolute import
resolved to the editable-installed shipped reticuli instead of its own
`tree/_kernel`, and a probe comparing the three measured shipped-vs-trial and
called it a behavioural split. The misresolved-guard in zeta's own probe
(`probe.py`) checks that `kernel.__file__` sits under the member tree -- which
it did -- but not where that kernel's transitive imports resolve, so a facade
that imports the package by its real name passes the guard while running
foreign code.

The honest load: materialise each tree UNDER THE NAME `reticuli`, in an
interpreter started with `-I -S` so the editable `.pth` is not processed and
`import reticuli` can only find the tree on the path. Then an absolute
`from reticuli._kernel import ...` loads the tree's own internals, a relative
import still works, and every trial runs its own code. That is also how the
succession harness materialises a whole-tool reconstruction -- as reticuli,
because it IS reticuli -- so this reproduces the trials' own qualification
conditions rather than a probe-specific artefact.

Probes: identity off the vectors, and the cost totaller on edge ledgers.
Both compare VALUES exactly, so a divergence is behaviour, not wording.

    python3 research/harness/closure/grade2_probe.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LINEAGES = REPO / "research" / "harness" / "succession"
ROOT_900 = "900b6594d4ade4d51f1331054437fa311f5f7a73153a722781d4fb701192cc0f"
TRIALS = [("r23-codex", "lineages-r23/codex", "relative"),
          ("r24-claude", "lineages-r24/claude", "absolute"),
          ("g2-codex", "lineages-g2/codex", "relative")]

# Novel claims (no gate step, so root is computable from bytes on disk).
NOVEL = {
    "big-int-envelope": ('[claim]\nname="b"\nformat=4\n'
                         'envelope={ tokens = 1000000000000000000000 }\n'
                         'inputs=["d.txt"]\n'
                         '[[step]]\nkind="produce"\noutput="a.py"\nclass="generated"\n',
                         {"d.txt": "data\n"}),
    "unicode-name": ('[claim]\nname="café-über-☃"\nformat=4\ninputs=["d.txt"]\n'
                     '[[step]]\nkind="produce"\noutput="a.py"\nclass="generated"\n',
                     {"d.txt": "ünîcödé\n"}),
    "reordered-steps": ('[claim]\nname="r"\nformat=4\ninputs=["z.txt","a.txt"]\n'
                        '[[step]]\nkind="produce"\noutput="zz.py"\nclass="generated"\n'
                        '[[step]]\nkind="produce"\noutput="aa.py"\nclass="generated"\n',
                        {"z.txt": "zeta\n", "a.txt": "alpha\n"}),
}

LEDGERS = {
    "boolean-value": [{"kind": "producer", "usd": True}],
    "negative-value": [{"kind": "producer", "usd": -5, "tokens": 10}],
    "nonfinite-value": [{"kind": "producer", "usd": float("inf")}],
    "scope-tagged": [{"kind": "producer", "usd": 1, "scope": "discovery"},
                     {"kind": "producer", "usd": 4}],
    "no-kind": [{"usd": 7}],
    "mixed-units": [{"kind": "producer", "usd": 1.5, "tokens": 100,
                     "calls": 3, "seconds": 2.0}],
}

DRIVER = r'''
import importlib, json, os, sys
req = json.loads(sys.stdin.readline())
sys.path.insert(0, req["asret"])
try:
    k = importlib.import_module("reticuli.kernel")
    # Containment, transitively: not just where kernel.py sits, but where the
    # function we call actually comes from. This is the guard the first probe
    # lacked -- a facade passes a __file__ check while its internals resolve
    # elsewhere.
    import inspect
    origin = os.path.realpath(inspect.getsourcefile(getattr(k, req["witness"])))
    if not origin.startswith(os.path.realpath(req["tree"]).rstrip(os.sep) + os.sep):
        print(json.dumps({"kind": "misresolved", "where": origin})); raise SystemExit(0)
except Exception as exc:
    print(json.dumps({"kind": "unavailable", "err": f"{type(exc).__name__}: {exc}"[:200]}))
    raise SystemExit(0)
try:
    if req["op"] == "root":
        out = k.root(k.load_recipe(req["claim"]), req["claim"])
    else:  # cost
        for e in req["events"]:
            k.ledger(req["claim"], e)
        out = k.cost(req["claim"])
    print(json.dumps({"kind": "value", "out": out}, sort_keys=True))
except BaseException as exc:
    print(json.dumps({"kind": "refused", "err": f"{type(exc).__name__}: {exc}"[:200]}))
'''


def run(tree, op, witness, claim, events=None):
    """Load the tree AS reticuli, under -S so the editable install is absent.

    For the cost op the ledger is WRITTEN, so each trial gets its OWN fresh
    claim -- a shared one lets the first trial's events accumulate under the
    next's, a false 1x/2x/3x split the first run produced. Root only reads,
    so it shares harmlessly.
    """
    stage = tempfile.mkdtemp(prefix="asret-")
    try:
        # The package is the `tree` subdirectory; symlink it IN as `reticuli`
        # so `import reticuli` loads the tree's own package.
        pkg = (Path(tree) / "tree").resolve()
        (Path(stage) / "reticuli").symlink_to(pkg)
        if op == "cost":
            claim = tempfile.mkdtemp(prefix="ledger-", dir=stage)
        req = json.dumps({"asret": stage, "tree": str(pkg), "op": op,
                          "witness": witness, "claim": claim,
                          "events": events or []})
        done = subprocess.run([sys.executable, "-I", "-S", "-c", DRIVER],
                              input=req + "\n", text=True, capture_output=True,
                              timeout=30)
        line = (done.stdout or "").strip().splitlines()
        if not line:
            return {"kind": "crashed", "err": (done.stderr or "")[-200:]}
        return json.loads(line[-1])
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        return {"kind": "crashed", "err": str(exc)[:200]}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def classify(obs):
    classes = {}
    for mid, o in obs.items():
        k = ("v:" + json.dumps(o.get("out"), sort_keys=True)
             if o["kind"] == "value" else o["kind"])
        classes.setdefault(k, []).append(mid)
    return {k: sorted(v) for k, v in sorted(classes.items())}


def sweep(title, cases, op, witness, make_args):
    print(f"\n{title}")
    splits = 0
    tmp = tempfile.mkdtemp(prefix="g2-")
    try:
        for name, spec in cases.items():
            claim, events = make_args(tmp, name, spec)
            obs = {t: run(str(LINEAGES / p), op, witness, claim, events)
                   for t, p, _ in TRIALS}
            classes = classify(obs)
            bad = [t for t, o in obs.items()
                   if o["kind"] in ("misresolved", "unavailable", "crashed")]
            if bad:
                print(f"  BAD   {name:16s} {', '.join(f'{t}:{obs[t][chr(107)+chr(105)+chr(110)+chr(100)]}' for t in bad)}")
                continue
            if len(classes) == 1:
                out = obs[next(iter(classes.values()))[0]].get("out")
                print(f"  agree {name:16s} -> {json.dumps(out)[:60]}")
            else:
                splits += 1
                print(f"  SPLIT {name}")
                for key, members in classes.items():
                    print(f"          {', '.join(members):28s} {key[2:][:48]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return splits


def main():
    print(f"grade-2 probe of the closure trials, loaded AS reticuli "
          f"(root {ROOT_900[:12]})")
    print(f"  import style: " + ", ".join(f"{t}={s}" for t, _, s in TRIALS))

    def claim_args(tmp, name, spec):
        toml_text, extras = spec
        d = Path(tmp) / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "reticuli.toml").write_text(toml_text)
        for fn, c in extras.items():
            (d / fn).write_text(c)
        return str(d.resolve()), None

    def ledger_args(tmp, name, events):
        d = Path(tmp) / name
        d.mkdir(parents=True, exist_ok=True)
        return str(d.resolve()), events

    id_splits = sweep("identity off the vectors (root of 3 novel claims):",
                      NOVEL, "root", "root", claim_args)
    cost_splits = sweep("cost totaller on edge ledgers:",
                        LEDGERS, "cost", "cost", ledger_args)

    print(f"\nsplits: identity {id_splits}/{len(NOVEL)}, "
          f"cost {cost_splits}/{len(LEDGERS)}")
    if id_splits == 0 and cost_splits == 0:
        print("With every trial running its OWN code, the three agree on identity\n"
              "off the vectors AND on the cost totaller's edge behaviour. The\n"
              "earlier 'split' was the import-resolution trap, not the trials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
