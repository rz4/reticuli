"""A second external target, a different SHAPE: POSIX tr, BSD vs GNU.

sed takes a program on stdin; tr takes its spec as SET ARGUMENTS and has no
program. That difference is the point of doing it: zeta's `process` probe is
built for the sed/jq shape (one program argument), so tr does not fit it --
and that is fine, because the instrument is the CLASSIFIER, not the invocation.
This harness gathers the observations itself (running each tr) and hands them
to `split.classify` unchanged. The partition logic -- agreement vs split, the
behaviour-key equivalence that ignores refusal wording -- is zeta's; only the
tool-specific way of running the member lives here, where it belongs.

Same reading as the sed note: a split is a corner POSIX tr leaves open (or an
implementation deviates), found differentially between two independent
implementations. It rules nothing correct; it maps where they part.

    python3 research/external/tr/probe_tr.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zeta"))

from lib import probe, split as splitlib          # noqa: E402

BSD = shutil.which("tr") or "/usr/bin/tr"
GNU = shutil.which("gtr") or "/opt/homebrew/bin/gtr"

POP = {"schema": "zeta.population.1", "name": "posix-tr",
       "current_root": "external:" + "posix-tr".ljust(55, "-"),
       "members": [{"id": "bsd-tr", "earned_root": "external:" + "posix-tr".ljust(55, "-")},
                   {"id": "gnu-tr", "earned_root": "external:" + "posix-tr".ljust(55, "-")}],
       "retired": [], "refused": []}

# (name, argv after the binary, stdin, what POSIX leaves open)
CASES = [
    ("reverse-range", ["c-a", "x-z"], "abc\n", "a range whose endpoints descend"),
    ("class-to-class", ["[:lower:]", "[:upper:]"], "Hello\n", "class-to-class translation"),
    ("complement-delete", ["-cd", "[:digit:]"], "a1b2\n", "delete the complement of a class"),
    ("squeeze", ["-s", "a-c"], "aabbcc\n", "squeeze repeats in a set"),
    ("octal-escape", ["\\130", "Y"], "aXb\n", "an octal escape in set1"),
    ("short-string2", ["a-e", "xy"], "abcde\n", "string2 shorter than string1"),
    ("upper-lower-range", ["A-Z", "a-z"], "ABC\n", "an ascending letter range"),
    ("newline-translate", ["\\n", "_"], "a\nb\n", "translating the newline itself"),
    ("repeat-construct", ["a-d", "[y*]"], "abcd\n", "the [c*] repeat construct"),
    ("equiv-class", ["[=e=]", "E"], "cafe\n", "a POSIX equivalence class"),
    ("delete-range", ["-d", "b-d"], "abcde\n", "delete a range"),
    ("complement-translate", ["-c", "a", "X"], "abc\n", "translate the complement"),
    ("literal-backslash", ["\\\\", "/"], "a\\b\n", "a literal backslash in set1"),
    ("class-upper-delete", ["-d", "[:space:]"], "a b\tc\n", "delete a whitespace class"),
]


def observe(binary, argv, stdin):
    """Run one tr and shape the outcome like a zeta observation."""
    prog = shutil.which(binary) or binary
    try:
        done = subprocess.run([prog, *argv], input=stdin, text=True,
                              capture_output=True, timeout=10,
                              env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"kind": "crashed", "error_type": type(exc).__name__,
                "error_message": str(exc)[:200]}
    if done.returncode < 0:
        return {"kind": "crashed", "error_type": f"Signal{-done.returncode}",
                "error_message": (done.stderr or "")[-200:]}
    if done.returncode != 0:
        return {"kind": "refused", "error_type": f"Exit{done.returncode}",
                "error_message": (done.stderr or "").strip()[-200:]}
    return {"kind": "value", "value": {"out": done.stdout}}


def main():
    for b in (BSD, GNU):
        if not Path(b).exists():
            print(f"  missing: {b}")
            return 1

    agree, semantic, extension, rows = 0, [], [], []
    for name, argv, stdin, asking in CASES:
        obs = {"bsd-tr": observe(BSD, argv, stdin),
               "gnu-tr": observe(GNU, argv, stdin)}
        pressure = {"schema": "zeta.pressure.1", "source": "posix_tr",
                    "id": f"tr/{name}", "clause": name, "simplicity": 0,
                    "call": "tr", "args": [argv, stdin],
                    "specified_reader_behaviour": asking,
                    "origin": "POSIX tr, BSD vs GNU"}
        result = splitlib.classify(POP, pressure, obs)
        disp = result["disposition"]
        rows.append((name, disp, obs, asking))
        if disp == "agreement":
            agree += 1
        elif disp == "split":
            kinds = {o["kind"] for o in obs.values()}
            (extension if "refused" in kinds and "value" in kinds
             else semantic).append((name, obs, asking))

    total = len(CASES)
    print(f"\nPOSIX tr, grade 2: BSD ({BSD}) vs GNU ({GNU})")
    print(f"  {total} probes  |  agree {agree}  |  semantic split {len(semantic)}"
          f"  |  extension/acceptance {len(extension)}\n")

    def show(obs):
        for m in ("bsd-tr", "gnu-tr"):
            o = obs[m]
            if o["kind"] == "value":
                print(f"      {m}: {o['value']['out'].replace(chr(10), chr(92)+'n')[:50]!r}")
            else:
                print(f"      {m}: {o['kind']} {o.get('error_type','')}")

    if semantic:
        print("SEMANTIC DIVERGENCES (both run, different output):")
        for name, obs, asking in semantic:
            print(f"  {name}  ({asking})"); show(obs)
        print()
    if extension:
        print("ACCEPTANCE DIVERGENCES (one refuses what the other accepts):")
        for name, obs, asking in extension:
            refuser = next(m for m, o in obs.items() if o["kind"] != "value")
            print(f"  {name}: {refuser} refuses -- {asking}")
        print()

    out = Path(__file__).resolve().parent / "probe_tr.json"
    out.write_text(json.dumps(
        {"target": "posix-tr", "bsd": BSD, "gnu": GNU, "probes": total,
         "agree": agree,
         "semantic": [{"case": n, "asking": a} for n, _, a in semantic],
         "acceptance": [{"case": n, "asking": a} for n, _, a in extension]},
        indent=2, sort_keys=True) + "\n")
    print(f"  written: {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
