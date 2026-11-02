"""Grade 2/3 probe for the globmatch rebuild, by mutation of the artifact.

The honest positive control is the rebuild's OWN source with a targeted bug
injected: if the probe catches codex-with-a-bug on every injection and finds
nothing against clean codex, grade 3 is real -- the probe discriminates the
exact error classes a from-scratch glob matcher is prone to, and the rebuild
has none of them. Cases are a curated set of WELL-FORMED quirky patterns (a
random fuzz mostly produces malformed brackets that every matcher treats as
literals, agreeing trivially), crossed with revealing names. Deterministic.

    probe_globmatch.py <dir-with-globmatch.py>
"""
import fnmatch, importlib.util, sys, types
from pathlib import Path

def load(src_text, tag):
    mod = types.ModuleType(f"gm_{tag}")
    exec(compile(src_text, f"<{tag}>", "exec"), mod.__dict__)
    return mod.match

# Well-formed patterns that exercise the machinery, crossed with revealing names.
PATTERNS = ["*","?","a","ab","a*","*a","a?c","*?","??","[ab]","[!ab]","[a-c]",
            "[!a-c]","[]]","[!]]","[^a]","[-a]","[a-]","[0-9]","[!0-9]","a[bc]d",
            "*[ab]*","[ab]?","\\a","a.b","[A-Z]","[z-a]","[]a]","[!]a]","*.*",
            "[ab][cd]","?[a-c]","[!a]*"]
NAMES = ["","a","b","c","d","]","^","-","0","5","ab","a.b","abc","]a","a]",
         "A","M","z","ba","cd","ac","a-c","abcd",".",".a"]
CASES = [(p, n) for p in PATTERNS for n in NAMES]

def outcome(m, p, s):
    try: return ("v", bool(m(p, s)))
    except Exception as e: return ("x", type(e).__name__)

def divergences(match):
    d = []
    for p, s in CASES:
        want = outcome(fnmatch.fnmatchcase, s, p)
        got = outcome(match, p, s)
        if want != got: d.append((p, s, got, want))
    return d

# Source mutations of the artifact: each a plausible from-scratch glob bug.
MUTATIONS = {
    "drop-negation":      [("if negate:", "if False:"), ("negate = ", "negate = False and ")],
    "range-exclusive":    [("low <= char <= high", "low <= char < high")],
    "question-literal":   [("accepts = True", "accepts = char == '?'")],
    "literal-casefold":   [("accepts = char == value", "accepts = char.lower() == value.lower()")],
}

def apply_mut(src, edits):
    out = src; hit = 0
    for a, b in edits:
        if a in out: out = out.replace(a, b, 1); hit += 1
    return (out, hit)

def main():
    target = sys.argv[1]
    src = (Path(target) / "globmatch.py").read_text()
    clean = load(src, "clean")
    clean_div = divergences(clean)

    print(f"probe: {len(CASES)} well-formed cases "
          f"({len(PATTERNS)} patterns x {len(NAMES)} names)")
    print("discriminating power (artifact source-mutations caught):")
    usable = 0
    for name, edits in MUTATIONS.items():
        mutsrc, hit = apply_mut(src, edits)
        if hit == 0:
            print(f"    {name:18} n/a (pattern not present in this artifact)"); continue
        try:
            caught = len(divergences(load(mutsrc, name)))
        except Exception as e:
            print(f"    {name:18} mutation broke source: {type(e).__name__}"); continue
        usable += 1 if caught else 0
        print(f"    {name:18} {caught} divergence(s) caught"
              + ("" if caught else "  <-- SLIPS THROUGH"))
    if usable < 2:
        print("PROBE TOO WEAK: fewer than two mutations are both applicable and caught")
        return 2

    if not clean_div:
        print(f"\nGRADE 3 over this probe: the rebuild matches fnmatch on all "
              f"{len(CASES)} cases,\nand the probe catches targeted mutations of "
              f"its own source. No divergence.")
        return 0
    print(f"\nGRADE 2: {len(clean_div)} divergence(s) vs fnmatch:")
    for p, s, got, want in clean_div[:30]:
        print(f"  match({p!r}, {s!r}): rebuilt={got} oracle={want}")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
