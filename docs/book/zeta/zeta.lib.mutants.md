# `zeta/lib/mutants.py`

**Deliberately broken members, used as controls so the ranker can rank.**

The first sweep's controls were the trials that failed to qualify, and they
discriminated nothing: those trials failed for reasons elsewhere, so on the
record surface they behaved exactly like members. A ranker that cannot
separate any two pressures ranks nothing, and every free click looked equally
worth a signature.

A mutant fixes that without waiting for a population. It is the authored tree
with one targeted edit -- a comparison flipped, a guard deleted, a refusal
turned into a pass -- and it is NEVER a member: nobody sealed it and it would
not earn the root. It sits in the control set, where its only job is to answer
a pressure differently from the members. A pressure that no mutant can tell
apart from a conforming member is a pressure that would not have caught a
broken implementation, whatever else it is.

This is the same instrument the kernel already uses for mutation scoring,
turned around: there, mutants measure whether a suite is strong enough; here,
they measure whether a probe is sharp enough.

```python
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
```

Each operator names the file it edits, the edit, what it breaks, and what
it is EXPECTED to do against the criteria. The expectation is the
instrument's own self-check: an outcome that contradicts it is either a
criterion gap or an over-pinned criterion, and both are findings.

  killed    the criteria must refuse this; a survivor is a hole
  survives  the criteria must NOT refuse this, because the specification
            deliberately leaves it open; a kill means a criterion has
            pinned something author-relative
  unknown   nobody decided; whatever happens is the measurement

`survives` is also the positive control. Without an operator that must
live, "every mutant killed" cannot be told apart from a harness unable to
detect survival at all.

```python
ATTEST = Path("reticuli") / "_kernel" / "attest.py"
CORE = Path("reticuli") / "_kernel" / "core.py"
RUN = Path("reticuli") / "_kernel" / "run.py"
IDENTITY = Path("reticuli") / "_kernel" / "identity.py"

OPERATORS = [
```

Anchored on the line that follows, because `record_validate(doc)` is
called from the reader too and an operator that matches twice would
break two things at once -- or, as it did first, be dropped silently.

```python
    ("skip-validation", ATTEST,
     r"^(\s*)record_validate\(doc\)\n(\s*)return json\.dumps",
     r"\1pass  # mutant\n\2return json.dumps",
     "a canonicalizer that validates nothing", "killed"),
    ("accept-any-version", ATTEST,
     r"^(\s*)if version > RECORD_FORMAT:$", r"\1if False:  # mutant",
     "a reader that accepts a document from the future", "killed"),
    ("ignore-unknown-members", ATTEST,
     r"^(\s*)unknown = set\(doc\) - members$", r"\1unknown = set()  # mutant",
     "a reader that lets an unnamed member through", "killed"),
    ("refuse-nothing", ATTEST,
     r'^(\s*)raise ClaimError\(f"not a record: \{reason\}"\)$',
     r"\1return  # mutant",
     "a validator whose refusal does not refuse", "killed"),
```

THE POSITIVE CONTROL. The specification requires a refusal to carry a
reason, not a particular sentence, so a criterion that pinned the words
would make membership depend on the author's prose. This must live.

```python
    ("reword-refusal", ATTEST,
     r'^(\s*)raise ClaimError\(f"not a record: \{reason\}"\)$',
     r'\1raise ClaimError(f"rejected, {reason}")  # mutant',
     "a refusal whose wording differs but whose reason does not", "survives"),
```

Identity: the canonical form and the hash are what a root IS.

```python
    ("unsorted-canonical", ATTEST,
     r'^(\s*)return json\.dumps\(doc, sort_keys=True\)\.encode\("utf-8"\)$',
     r'\1return json.dumps(doc).encode("utf-8")  # mutant',
     "canonical bytes that depend on dictionary order", "killed"),
    ("weak-record-digest", ATTEST,
     r"^(\s*)return hashlib\.sha256\(record_canonical\(doc\)\)\.hexdigest\(\)$",
     r"\1return hashlib.sha1(record_canonical(doc)).hexdigest()  # mutant",
     "a record cited by a broken hash", "killed"),
```

Measurement honesty: these decide whether a cost condition means
anything, and nothing in the project's record says they were tested.
These two target one line each, and the line moved under them when the
implementation was repaired: adding the finite guard to the cost totaller
made the old pattern match nothing. The criterion refused rather than
quietly shipping a smaller mutant pool, which is the right direction --
a dropped operator makes every pressure it would have discriminated look
sharper than it is. The cost of source-level mutation is exactly this
upkeep, and it is paid in the open.

```python
    ("cost-accepts-boolean", RUN,
     r"^(\s*)if isinstance\(value, bool\) or not isinstance\(value, \(int, float\)\) \\\n(\s*)or not math\.isfinite\(value\):$",
     r"\1if not isinstance(value, (int, float)) \\\n\2or not math.isfinite(value):  # mutant",
     "a cost total that counts True as one", "killed"),
```

The newly pinned gene, put to the test the only way that counts: break
it and require the criteria to notice. Before this morning's signature
this operator could not exist, because the guard it removes was absent.

```python
    ("cost-accepts-nonfinite", RUN,
     r"^(\s*)if isinstance\(value, bool\) or not isinstance\(value, \(int, float\)\) \\\n(\s*)or not math\.isfinite\(value\):$",
     r"\1if isinstance(value, bool) or not isinstance(value, (int, float)):  # mutant",
     "a cost total that swallows an infinity", "killed"),
    ("reader-accepts-nonfinite", ATTEST,
     r"^(\s*)if isinstance\(value, bool\) or not isinstance\(value, \(int, float\)\) \\\n(\s*)or not math\.isfinite\(value\) or value < 0:$",
     r"\1if isinstance(value, bool) or not isinstance(value, (int, float)) \\\n\2or value < 0:  # mutant",
     "a reader admitting a NaN or infinite cost value", "killed"),
    ("discovery-into-totals", RUN,
     r'^(\s*)bucket = discovery if event\.get\("scope"\) else totals$',
     r"\1bucket = totals  # mutant",
     "an authoring session's discovery bill priced as a redo", "unknown"),
    ("tolerance-exclusive", RUN,
     r"^(\s*)return \(1\.0 / tolerance\) <= ratio <= tolerance$",
     r"\1return (1.0 / tolerance) < ratio < tolerance  # mutant",
```

Was `unknown` and SURVIVED, which is how the gap was found; the
closed band was signed on 2026-10-14 and coverage now kills it. The
expectation moves with the signature, so a later survival reads as a
regression rather than as a fresh discovery.

```python
     "a cost band that refuses its own boundary", "killed"),
```

IDENTITY: the root's own preimage. Coverage killed every operator above,
which says the vocabulary was exhausted against the criteria, not that
no gaps remain -- so the next place to look is the surface nothing had
mutated. This is the sharpest one in the system: if a mutant can change
how the root is computed and still earn the gate, nothing else matters.

```python
    ("root-includes-generated", IDENTITY,
     r'^(\s*)if step\.get\("class"\) == "generated":$',
     r"\1if False:  # mutant",
     "a root that hashes the implementation, destroying the equivalence class",
     "killed"),
    ("root-omits-the-recipe", IDENTITY,
     r'^(\s*)parts = \{"digest": DIGEST, "recipe": serialized\}$',
     r'\1parts = {"digest": DIGEST}  # mutant',
     "a root that does not cover the recipe, so a changed criterion moves nothing",
     "killed"),
    ("recipe-preimage-unsorted", IDENTITY,
     r"^(\s*)serialized = json\.dumps\(_preimage_recipe\(recipe\), sort_keys=True\)$",
     r"\1serialized = json.dumps(_preimage_recipe(recipe))  # mutant",
     "a recipe preimage that depends on key order", "killed"),
    ("steps-unsorted", IDENTITY,
     r"^(\s*)stripped\.sort\(key=lambda s: json\.dumps\(s, sort_keys=True\)\)$",
     r"\1pass  # mutant",
     "a format-4 root that moves when steps are reordered", "killed"),
    ("build-digest-unsorted", IDENTITY,
     r'^(\s*)preimage = json\.dumps\(sorted\(own\), sort_keys=True\)\.encode\("utf-8"\)$',
     r'\1preimage = json.dumps(own, sort_keys=True).encode("utf-8")  # mutant',
     "a build digest that depends on step order", "killed"),
```

The interesting one. The `input:` and `pinned:` prefixes keep a crafted
filename out of the preimage's structural namespace: without them, a
claim carrying a file named `recipe` or `digest` would shadow the part
that holds the recipe or the format tag. Whether any vector exercises a
filename like that is exactly the question, and nobody has asked it.

```python
    ("root-drops-the-input-prefix", IDENTITY,
     r'^(\s*)parts\[f"input:\{name\}"\] = _hash_file\(_safe\(claimdir, name\)\)$',
     r"\1parts[name] = _hash_file(_safe(claimdir, name))  # mutant",
     "a preimage where a filename can collide with a structural key",
     "unknown"),
```

Confinement: a gate that can read an inherited secret can seal it into
a verdict. Whether any criterion notices is exactly the question.

```python
    ("leak-environment", CORE,
     r'^_KEEP_ENV = \("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", _JAILED\)$',
     '_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", _JAILED,\n'
     '              "AWS_SECRET_ACCESS_KEY")  # mutant',
     "a gate that can read one more inherited secret", "unknown"),
]
```

The record layer's file, for callers that only need that one.

```python
TARGET = ATTEST


def build(repo, into, operators=None):
    """Copy the authored tree once per operator and apply that one edit.

    Returns control members, ready to hand to a split as controls. An operator
    whose pattern does not match is reported rather than skipped silently: a
    mutant that was never built would otherwise look like a pressure nothing
    could discriminate.
    """
    source = Path(repo) / "src"
    into = Path(into)
    built, missed = [], []
    for name, target, pattern, replacement, why, expect in (operators or OPERATORS):
        tree = into / name
        if tree.exists():
            shutil.rmtree(tree)
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns("__pycache__"))
        path = tree / target
        text = path.read_text()
        changed, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
        if count != 1:
            missed.append({"operator": name, "matches": count,
                           "target": str(target),
                           "why": "pattern did not match exactly once"})
            shutil.rmtree(tree)
            continue
        path.write_text(changed)
        built.append({"id": f"mutant:{name}", "run": "mutant", "family": "broken",
                      "earned_root": None, "path": str(tree),
                      "package": "reticuli", "driver": "python-package",
                      "target": str(target), "breaks": why, "expect": expect})
    return built, missed


def session(repo):
    """A temporary directory of mutants, cleaned up afterwards."""
    return tempfile.TemporaryDirectory(prefix="zeta-mutants-")
```

---
*Woven from `zeta/lib/mutants.py` by `docs/weave.py`. The implementation is generated -- one member of the claim's equivalence class -- so this page is derived twice over: regenerate it, never edit it.*
