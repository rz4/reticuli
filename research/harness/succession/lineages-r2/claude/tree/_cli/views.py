"""reticuli._cli.views: read a claim into the small state dict a command
prints (spec/layers.md, surface layer).

Every function here reaches only `reticuli.kernel`'s public surface, never
`reticuli._kernel` -- the rule `_util.py` states and this layer inherits.
A view never re-earns a verdict; it reads what `kernel.phase`/`kernel.verify`
already computed and presents it, plus the next rung on the ladder toward
`signed`.
"""
import json
import os

from reticuli import kernel

_LADDER = {
    "draft": "seal the claim: `ret seal`",
    "sealed": "prove independence: `ret crosscheck`",
    "signed": "nothing further -- the claim is signed",
    "invalid": "fix the claim so it verifies again",
}


def _phase(d: str) -> str:
    """`kernel.phase`, with a claim that no longer verifies read as a state
    rather than an exception a view has to catch."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "invalid"


def _verified(d: str) -> bool:
    """Whether the claim's identity currently holds -- `False`, not a
    raised error, for a directory that is not (yet, or no longer) a claim."""
    try:
        return bool(kernel.verify(d)["ok"])
    except kernel.ClaimError:
        return False


def _gate_ok(status: str) -> bool:
    """Whether a gate's status (spec/verification.md's failure-class
    vocabulary) counts as passing. Only `ok` does; every other class --
    `failed`, `timeout`, `mismatch`, `environment` -- is some form of no."""
    return status == "ok"


def _deciding_words(cmd: str) -> str:
    """A human phrase naming what decides a gate's `run` command, from
    `kernel.gate_deciders`. Empty deciders means the recipe text itself is
    the criterion (a bare `grep`/`printf` line with nothing to point at)."""
    deciders = kernel.gate_deciders(cmd)
    if not deciders:
        return "the recipe text itself"
    return ", ".join(deciders)


def _signatures(d: str) -> list:
    """The signature statements under the claim's sign directory, read for
    display only -- trust (whether one verifies against an anchor) is
    `kernel.phase`'s job, not this view's."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    sigs = []
    for name in sorted(os.listdir(sign_dir)):
        if not name.endswith(".sign.json"):
            continue
        path = os.path.join(sign_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                statement = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(statement, dict):
            continue
        sigs.append({
            "name": name[: -len(".sign.json")],
            "identity": statement.get("identity"),
            "proof_recorded": statement.get("proof_recorded"),
        })
    return sigs


def _read_residue(d: str, name: str):
    """Read one file of store residue (a ledger, a mutation-score cache) by
    name under `.reticuli/`. `.jsonl` is read as a list of parsed lines,
    skipping any that don't parse -- residue, not identity, so a partial
    write must not make the whole file unreadable. Returns `None` when the
    file is absent."""
    path = os.path.join(d, kernel.STORE, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    if name.endswith(".jsonl"):
        entries = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _verdict(result) -> str:
    """The three-valued crosscheck word (`accept`/`reject`/`incomplete`)
    out of a `kernel.crosscheck` result, or `incomplete` for anything that
    is not that shape -- unknown evidence is not evidence."""
    if isinstance(result, dict) and "verdict" in result:
        return result["verdict"]
    return "incomplete"


def _next_step(view) -> str:
    """The next rung on the ladder toward `signed`, from a claim view's
    (or a bare phase string's) `phase`. Always a non-empty string: even an
    unrecognized phase gets a safe default rather than nothing to print."""
    p = view.get("phase") if isinstance(view, dict) else view
    return _LADDER.get(p, "verify the claim: `ret verify`")


def _claim_view(d: str) -> dict:
    """The documented state dict for a sealed claim: `name`, `root`,
    `phase`, `verified`, `signatures`, and `next` -- the one rung a command
    like `ret status` prints without re-deriving any of this itself."""
    manifest = kernel.read_manifest(d)
    view = {
        "name": manifest.get("name"),
        "root": manifest.get("root"),
        "phase": _phase(d),
        "verified": _verified(d),
        "signatures": _signatures(d),
    }
    view["next"] = _next_step(view)
    return view
