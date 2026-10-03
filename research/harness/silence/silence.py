"""The silence map: measure what a boundary never said, by sampling its class.

The succession showed that independent blind reconstructions implement
exactly what the checks exercise and nothing more — so the places where N
gate-passing implementations DISAGREE are a direct measurement of the
boundary's silence. This instrument makes that measurement: it generates a
probe battery, runs every implementation on every probe, and clusters the
divergent probes into behavior partitions. Each cluster is a candidate
obligation — a region of the unpinned surface where the class has not
converged, lit up by the model prior itself.

The ratchet, made active: instead of waiting for a consumer to break on a
silent region, sample the class and read the map.

    python3 silence.py --subject kvparse     # stage-2 impls, known ground truth
    python3 silence.py --subject confparse   # ladder controls, known ground truth

An implementation is a module exposing `parse(text) -> value`; probes are
run in one subprocess per implementation (untrusted generated code; a crash
or hang on a probe is an outcome, not a harness failure). Research tooling —
nothing here moves a root.
"""
import argparse
import itertools
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


# -- probe generation ---------------------------------------------------------
#
# The battery is generated, not hand-aimed: small compositions of the lexical
# ingredients config-like text is made of. Hand-written probes encode what the
# author already suspects; a generated battery can only rediscover a known
# silence by actually covering it, which is the validation this instrument
# needs before it is trusted on unknown territory.

KEYS = ["k", "K", "key", "Key", "key2", "k-2", "k_2", "k.x", " k", "k "]
VALUES = ["v", "V", "hello world", "8080", "-3", "3.5", "0x1f", "007",
          "true", "True", "no", "", " ", "a=b", "v # note", "#v",
          "héllo", "v\\", "[v]", "'v'", '"v"']
SEPARATORS = [" = ", "=", " : ", ":", " == ", "  =  ", "\t=\t"]
LINES = ["", " ", "# comment", "## x", "; comment", "[section]", "[ s ]",
         "plainword", "= v", "k =", "   indented = v"]


def battery() -> list:
    probes = []
    # single assignments: every separator, a spread of keys and values
    for sep in SEPARATORS:
        for k, v in itertools.product(KEYS[:4], VALUES):
            probes.append(f"{k}{sep}{v}")
    for k in KEYS:
        probes.append(f"{k} = v")
    # structural lines, alone and before/after an anchor assignment
    for line in LINES:
        probes.append(line)
        probes.append(f"{line}\na = x")
        probes.append(f"a = x\n{line}")
    # duplicates, ordering, continuation, multi-line shapes
    probes += [
        "k = a\nk = b", "k = a\nk = b\nk = c", "K = a\nk = b",
        "a = 1\nb = 2", "b = 2\na = 1",
        "k = one \\\ntwo", "k = one\\\ntwo", "k = \\\n v",
        "[db]\nhost = h", "[db]\nhost = h\n[web]\nhost = w",
        "[db]\n[db]\nk = v",
        "a = x\n\n\nb = y", "a = x\r\nb = y", "\na = x\n",
        "k = v\nk: w", "k: w\nk = v",
    ]
    # dedupe, keep order
    seen, out = set(), []
    for p in probes:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


# -- running one implementation over the battery ------------------------------

_DRIVER = r"""
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("parser", sys.argv[1])
m = importlib.util.module_from_spec(spec)
sys.modules["parser"] = m
try:
    spec.loader.exec_module(m)
except Exception as e:
    print(json.dumps({"__load__": type(e).__name__})); raise SystemExit(0)
probes = json.load(open(sys.argv[2]))
out = []
for p in probes:
    try:
        r = m.parse(p)
        try:
            out.append(["ok", json.dumps(r, sort_keys=True)])
        except (TypeError, ValueError):
            out.append(["ok", repr(r)])
    except Exception as e:
        out.append(["error", type(e).__name__])
print(json.dumps(out))
"""


def outcomes(impl: Path, probes: list, workdir: Path) -> list | None:
    pfile = workdir / "probes.json"
    pfile.write_text(json.dumps(probes))
    try:
        r = subprocess.run([sys.executable, "-c", _DRIVER, str(impl), str(pfile)],
                           capture_output=True, text=True, timeout=120,
                           check=False)
        rows = json.loads(r.stdout.strip().splitlines()[-1])
    except (subprocess.TimeoutExpired, ValueError, IndexError):
        return None
    if isinstance(rows, dict) and "__load__" in rows:
        return None
    return [tuple(x) for x in rows]


# -- the map ------------------------------------------------------------------

def _delta_kind(a: tuple, b: tuple) -> str:
    """Classify HOW two outcomes differ — the fingerprint of the underlying
    decision, so one partition that hides several distinct silences (the
    original differing from everyone for eight different reasons) is split
    back into them."""
    (sa, pa), (sb, pb) = a, b
    if sa != sb:
        return "error-vs-accept"
    if sa == "error":
        return "error-kind"
    try:
        da, db = json.loads(pa), json.loads(pb)
    except (ValueError, TypeError):
        return "repr"
    if not isinstance(da, dict) or not isinstance(db, dict):
        return "shape"
    ka, kb = set(da), set(db)
    if ka != kb:
        if {k.lower() for k in ka} == {k.lower() for k in kb}:
            return "key-case"
        if not da or not db:
            return "line-dropped-vs-kept"
        return "key-set"
    for k in ka:
        if type(da[k]) is not type(db[k]):
            return "value-type"
    return "value-text"


def map_silence(impls: dict, probes: list, workdir: Path) -> dict:
    """Run every implementation over the battery; return the divergent probes
    clustered by PARTITION plus DELTA KIND — which implementations split
    which way, and what kind of difference it is. Two probes land in one
    cluster when they split the class the same way for the same kind of
    reason, the signature of one underlying unpinned decision."""
    runs = {}
    for name, path in impls.items():
        rows = outcomes(Path(path), probes, workdir)
        if rows is not None:
            runs[name] = rows
    names = sorted(runs)
    clusters: dict = defaultdict(list)
    agree = 0
    for i, probe in enumerate(probes):
        row = {n: runs[n][i] for n in names}
        if len(set(row.values())) == 1:
            agree += 1
            continue
        # the partition: which impls behave identically, ignoring the probe's
        # concrete text — canonical form so same-shaped splits cluster
        groups = defaultdict(list)
        for n in names:
            groups[row[n]].append(n)
        partition = tuple(sorted(tuple(sorted(v)) for v in groups.values()))
        # the delta kind between the two largest behavior groups
        big = sorted(groups, key=lambda k: -len(groups[k]))[:2]
        kind = _delta_kind(big[0], big[1])
        clusters[(partition, kind)].append(
            {"probe": probe,
             "behaviors": {", ".join(v): k[0] + ":" + k[1][:80]
                           for k, v in groups.items()}})
    ranked = sorted(clusters.items(),
                    key=lambda kv: (-len(kv[1]), kv[0]))
    return {"implementations": names, "probes": len(probes),
            "agreed": agree, "divergent": len(probes) - agree,
            "clusters": [{"partition": [list(g) for g in part],
                          "kind": kind,
                          "probe_count": len(rows),
                          "examples": rows[:5]}
                         for (part, kind), rows in ranked]}


def report(result: dict, title: str) -> None:
    print(f"\nsilence map — {title}")
    print(f"  {len(result['implementations'])} implementations, "
          f"{result['probes']} probes: {result['agreed']} agreed, "
          f"{result['divergent']} divergent, "
          f"{len(result['clusters'])} distinct splits\n")
    for i, c in enumerate(result["clusters"], 1):
        sides = " vs ".join("{" + ",".join(g) + "}" for g in c["partition"])
        print(f"  silence #{i} [{c['kind']}]: {c['probe_count']} probes "
              f"split {sides}")
        for ex in c["examples"][:3]:
            print(f"      probe {ex['probe']!r}")
            for who, what in ex["behaviors"].items():
                print(f"        {who:40} -> {what}")
        print()


# -- subjects with known ground truth -----------------------------------------

SUBJECTS = {
    "kvparse": {
        "original": REPO / "research/harness/substitution/stage2/claims/D/parser.py",
        "impls_glob": REPO / "research/harness/substitution/stage2/impls",
        "ground_truth": "coercion (int vs str) and duplicate keys (first vs last)",
    },
    "confparse": {
        "original": REPO / "research/harness/ladder/claims/L/parser.py",
        "impls_glob": REPO / "research/harness/ladder/controls",
        "ground_truth": "the eight ladder intent bits",
    },
    "kvparse-c1": {
        "original": REPO / "research/harness/substitution/stage2/claims/D/parser.py",
        "impls_glob": REPO / "research/harness/substitution/stage2/impls_c1",
        "ground_truth": "after the ratchet: coercion and duplicates pinned by "
                        "C_1 — the map should show those silences gone",
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", choices=sorted(SUBJECTS), required=True)
    ap.add_argument("--json", metavar="FILE", help="also write the full map")
    a = ap.parse_args()
    s = SUBJECTS[a.subject]
    impls = {"original": str(s["original"])}
    for p in sorted(Path(s["impls_glob"]).glob("impl_*.py")):
        impls[p.stem.removeprefix("impl_")] = str(p)
    workdir = HERE / "scratch"
    workdir.mkdir(exist_ok=True)
    result = map_silence(impls, battery(), workdir)
    report(result, f"{a.subject} (ground truth: {s['ground_truth']})")
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
