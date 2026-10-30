"""The stack's first external, non-Python target: POSIX sed, two ways.

jq was the project's external arm, but jq ships three implementations the
project went looking for. This points the SAME machinery at a target that was
not chosen for it: POSIX sed, as implemented independently by BSD
(`/usr/bin/sed`, Apple's) and GNU (`gsed`). Two implementations of one
documented spec, written by people who were not coordinating -- the foreign
population zeta's process driver exists for, on a tool nobody here wrote and
that is not jq.

What a divergence means here. POSIX specifies sed; where two conforming
implementations produce different output for one script-and-input, the spec
left that corner undetermined (or one implementation has a bug). Either way it
is negative space in a boundary someone else wrote, found by differential
pressure -- grade 2 on POSIX sed. Agreement is the spec doing its job; a split
is a point it does not pin, and the kind of split matters:

  both produce output, DIFFERENT      a semantic divergence -- the sharp kind.
  one REFUSES, the other produces      an extension one side has and the other
                                       does not: portable sed cannot rely on it.

This reuses zeta's own split classifier and process probe unchanged, so the
instrument meeting a new target is the same instrument the closure work
hardened. Research tooling: decides nothing, moves no root, needs no producer.

    python3 research/external/sed/probe_sed.py
"""
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zeta"))

from lib import probe, split as splitlib          # noqa: E402

# Two independent implementations of POSIX sed. `command` and the process
# driver are zeta's; `flags=[]` runs each in its default (POSIX BRE) mode so a
# divergence is about the SPEC, not about a flag one side spells differently.
BSD = shutil.which("sed") or "/usr/bin/sed"
GNU = shutil.which("gsed") or "/opt/homebrew/bin/gsed"
POP = {"schema": "zeta.population.1", "name": "posix-sed",
       "current_root": "external:" + "posix-sed".ljust(55, "-"),
       "members": [
           {"id": "bsd-sed", "command": BSD, "driver": "process", "flags": [],
            "earned_root": "external:" + "posix-sed".ljust(55, "-")},
           {"id": "gnu-sed", "command": GNU, "driver": "process", "flags": [],
            "earned_root": "external:" + "posix-sed".ljust(55, "-")}],
       "retired": [], "refused": []}

# (name, sed script, input document, what POSIX leaves open here). The input
# always ends in a newline unless the case is specifically about EOF.
CASES = [
    # The append/insert/change family -- POSIX specifies the `a\<newline>text`
    # form; the one-liner is where implementations diverge most visibly.
    ("append-oneline", "1a hello", "x\n", "does `a text` work without a backslash"),
    ("insert-oneline", "1i hello", "x\n", "does `i text` work without a backslash"),
    ("change-oneline", "1c hello", "x\n", "does `c text` work without a backslash"),
    ("append-backslash", "1a\\\nhello", "x\n", "the POSIX `a\\` form"),
    # BRE intervals and the GNU BRE extensions BSD does not take.
    ("interval", "s/a\\{2\\}/X/", "aaa\n", "a counted repeat in BRE"),
    ("bre-plus", "s/a\\+/X/", "aaa\n", "is \\+ a quantifier or a literal plus"),
    ("bre-question", "s/ab\\?/X/", "ab\n", "is \\? a quantifier in BRE"),
    ("bre-alt", "s/cat\\|dog/X/", "dog\n", "is \\| alternation in BRE"),
    # Replacement-side features.
    ("ampersand", "s/na/[&]/g", "banana\n", "& is the whole match"),
    ("backref", "s/\\(an\\)\\1/X/", "anan\n", "a backreference in the pattern"),
    ("case-upper", "s/.*/\\U&/", "abc\n", "is \\U uppercase conversion (GNU)"),
    ("newline-repl", "s/b/x\\ny/", "ab\n", "a newline in the replacement"),
    ("tab-repl", "s/b/\\t/", "ab\n", "is \\t a tab in the replacement"),
    # s/// flags and delimiters.
    ("subst-nth", "s/a/X/2", "aaa\n", "replace only the Nth match"),
    ("subst-nth-g", "s/a/X/2g", "aaaa\n", "replace from the Nth match on"),
    ("alt-delim", "s|a|X|g", "banana\n", "a non-slash delimiter"),
    ("empty-regex", "s/an/X/;s//Y/", "banana\n", "// reuses the last regex"),
    # Transliteration and classes.
    ("translit", "y/abc/xyz/", "cab\n", "y/// one-to-one"),
    ("posix-class", "s/[[:digit:]]/#/g", "a1b2\n", "a POSIX character class"),
    # Addresses.
    ("last-line", "$d", "a\nb\nc\n", "the $ last-line address"),
    ("step-addr", "1~2d", "a\nb\nc\nd\n", "the GNU first~step address"),
    ("zero-addr", "0,/b/d", "a\nb\nc\n", "the GNU 0,/re/ address"),
    # Quitting and end-of-file.
    ("quit", "2q", "a\nb\nc\n", "q prints the current line then quits"),
    ("quit-silent", "2Q", "a\nb\nc\n", "is Q (quit without printing) supported"),
    ("no-trailing-newline", "s/a/X/", "no newline here no a? a", "input without a final newline"),
    ("delete-all", "d", "a\nb\n", "d deletes every line"),
]


def main():
    for member in POP["members"]:
        if not Path(member["command"]).exists():
            print(f"  missing: {member['id']} at {member['command']}")
            return 1

    agree, semantic, extension, rows = 0, [], [], []
    for name, script, document, asking in CASES:
        pressure = {"schema": "zeta.pressure.1", "source": "posix_sed",
                    "id": f"sed/{name}", "clause": name, "simplicity": 0,
                    "call": "apply", "args": [script, document],
                    "specified_reader_behaviour": asking,
                    "origin": "POSIX sed, BSD vs GNU"}
        result = splitlib.run(POP, pressure, controls=False)
        disp = result["disposition"]
        obs = result["observations"]
        rows.append((name, disp, obs, asking))
        if disp == "agreement":
            agree += 1
        elif disp == "split":
            kinds = {m: o["kind"] for m, o in obs.items()}
            if "refused" in kinds.values() and "value" in kinds.values():
                extension.append((name, obs, asking))
            else:
                semantic.append((name, obs, asking))

    total = len(CASES)
    print(f"\nPOSIX sed, grade 2: BSD ({BSD}) vs GNU ({GNU})")
    print(f"  {total} probes of corners POSIX leaves open")
    print(f"  agree {agree}  |  semantic split {len(semantic)}  |  "
          f"extension-only {len(extension)}\n")

    def show(obs):
        for m in ("bsd-sed", "gnu-sed"):
            o = obs[m]
            if o["kind"] == "value":
                out = o["value"]["out"].replace("\n", "\\n")
                print(f"      {m}: {out[:60]!r}")
            else:
                print(f"      {m}: {o['kind']} {o.get('error_type','')}")

    if semantic:
        print("SEMANTIC DIVERGENCES (both run, different output -- the sharp kind):")
        for name, obs, asking in semantic:
            print(f"  {name}  ({asking})")
            show(obs)
        print()
    if extension:
        print("EXTENSION-ONLY (one refuses -- portable sed cannot rely on it):")
        for name, obs, asking in extension:
            refuser = next(m for m, o in obs.items() if o["kind"] != "value")
            print(f"  {name}: {refuser} refuses -- {asking}")
        print()

    out = Path(__file__).resolve().parent / "probe_sed.json"
    out.write_text(json.dumps(
        {"target": "posix-sed", "bsd": BSD, "gnu": GNU, "probes": total,
         "agree": agree,
         "semantic": [{"case": n, "asking": a,
                       "out": {m: o.get("value", {}).get("out") if o["kind"] == "value"
                               else o["kind"] for m, o in obs.items()}}
                      for n, obs, a in semantic],
         "extension_only": [{"case": n, "asking": a} for n, _, a in extension]},
        indent=2, sort_keys=True) + "\n")
    print(f"  written: {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
