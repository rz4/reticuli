"""Reference sealer: a second, independent implementation of spec/identity.md.

Implements spec/identity.md and the validation rules of spec/claim-format.md
— nothing else. No gate runner, no sandbox, no rebuild: it computes roots,
writes manifests, and re-checks identity. It exists so the seed claim can be
sealed before the v2 kernel does; the kernel is regrown blind against the
sealed acceptance suite and must agree with this script on every root
(a two-implementation conformance check). Derived by hand from the spec,
which was extracted from v1 — recorded in provenance/bootstrap.md.

    python3 -m reticuli.reference root   <claim-dir>   # print the root
    python3 -m reticuli.reference seal   <claim-dir>   # root + manifest.json
    python3 -m reticuli.reference verify <claim-dir>   # manifest matches bytes?

IT MUST NEVER IMPORT FROM THE REST OF THE PACKAGE. It ships inside `reticuli`
because it is an implementation of the spec rather than a criterion about one,
and implementations are what `src/` holds — but its entire value is being a
SECOND implementation. An import of `reticuli.kernel` here, however
convenient, would collapse the two into one and quietly retire the only
cross-check the identity computation has. Standard library only.
"""
import hashlib
import json
import os
import stat
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
STORE = ".reticuli"


class ClaimError(Exception):
    """A refusal with a reason — the only error this tool raises."""


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True)


def _safe(root: str, name: str) -> str:
    """Join a recipe-declared path under `root`, refusing any that escapes:
    absolute, empty, `..`, or a symlink whose target leaves the claim."""
    if not name or os.path.isabs(name):
        raise ClaimError(f"unsafe recipe path (absolute or empty): {name!r}")
    root_r = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root_r, name))
    if full != root_r and not full.startswith(root_r + os.sep):
        raise ClaimError(f"unsafe recipe path (escapes the claim root): {name!r}")
    return os.path.join(root, name)


def _hash_file(path: str) -> str:
    """Hash a declared file: a REGULAR file with a SINGLE hard link, reached
    without a symlink at the final component (spec/identity.md, file rules)."""
    try:
        st = os.lstat(path)
    except OSError as e:
        raise ClaimError(f"declared file missing: {path!r} ({e})") from e
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"declared file is not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"declared file has multiple links: {path!r}")
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_recipe(d: str) -> dict:
    """Parse and validate claim.toml (spec/claim-format.md, validation rules)."""
    try:
        path = os.path.join(d, RECIPE)
        if not os.path.isfile(path):
            path = os.path.join(d, LEGACY_RECIPE)
        with open(path, "rb") as f:
            recipe = tomllib.load(f)
    except (OSError, ValueError) as e:
        raise ClaimError(f"unreadable recipe in {d}: {e}") from e
    c = recipe.get("claim")
    if not isinstance(c, dict) or not isinstance(c.get("name"), str):
        raise ClaimError(f"malformed recipe in {d} ([claim] name required)")
    for step in recipe.get("step", []):
        if not isinstance(step, dict) or "kind" not in step:
            raise ClaimError(f"malformed step in {d} (a step needs a kind)")
        if step["kind"] not in ("produce", "gate"):
            raise ClaimError(f"unknown step kind in {d}: {step['kind']!r}")
        if "output" not in step:
            raise ClaimError(f"malformed {step['kind']} step in {d} (output required)")
        if step["kind"] == "gate" and "run" not in step:
            raise ClaimError(f"malformed gate step in {d} (a run is required)")
    return recipe


def _class(step: dict) -> str:
    return step.get("class", "generated" if step["kind"] == "produce" else "pinned")


def root(d: str) -> str:
    """The root, exactly as spec/identity.md states it."""
    recipe = load_recipe(d)
    parts = {"digest": "sha256", "recipe": _canonical(recipe)}
    for path in recipe["claim"].get("inputs", []):
        parts[f"input:{path}"] = _hash_file(_safe(d, path))
    for step in recipe.get("step", []):
        if _class(step) != "generated":
            parts[f"pinned:{step['output']}"] = _hash_file(_safe(d, step["output"]))
    return hashlib.sha256(_canonical(parts).encode()).hexdigest()


def seal(d: str) -> dict:
    manifest = {"name": load_recipe(d)["claim"]["name"], "root": root(d)}
    os.makedirs(os.path.join(d, STORE), exist_ok=True)
    with open(os.path.join(d, STORE, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return manifest


def verify(d: str) -> dict:
    path = os.path.join(d, STORE, "manifest.json")
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        raise ClaimError(f"unreadable manifest in {d}: {e}") from e
    if not isinstance(m, dict) or not isinstance(m.get("root"), str):
        raise ClaimError(f"malformed manifest in {d} (name and root required)")
    ok = m["root"] == root(d)
    return {"ok": ok, "name": m.get("name"), "root": m["root"]}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("root", "seal", "verify"):
        print(__doc__, file=sys.stderr)
        return 2
    cmd, d = argv
    try:
        if cmd == "root":
            print(root(d))
        elif cmd == "seal":
            m = seal(d)
            print(f"sealed {m['name']} {m['root']}")
        else:
            v = verify(d)
            print(f"{'ok' if v['ok'] else 'MISMATCH'} {v['name']} {v['root']}")
            return 0 if v["ok"] else 1
    except ClaimError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
