"""The acceptance boundary must exclude undeclared pressure. Writes BOUNDARY_OK.

    python3 criteria/boundary_check.py      (from the repository root)

Zeta is this claim's companion: it puts pressure on the equivalence class,
reads what the criteria failed to say, and queues each finding for a
signature. A queued finding is UNDECLARED -- weaker than `incomplete`, because
it is not a condition at all -- and promoting one is an ordinary root move
performed here, in `criteria/` and in the recipe's inputs.

What must never happen is the shortcut: pending pressure reaching the verdict
without being declared. There are two ways in, and this criterion closes both.

PINNING. A path under `zeta/` among the inputs would put undeclared pressure
inside the root, and -- worse -- anything pinned is materialised into a
rebuilding producer's room. A producer that could read the queue would be
reading guidance, and guidance cannot decide whether a rebuild is accepted
(`G` is disjoint from the read set, by construction). It is the same reason
the sealed kernel claim's implementation is deliberately not pinned while its
suite is: a suite is a criterion and belongs in the room; an answer does not.

INVOKING. A gate that ran zeta would make the verdict depend on whatever the
last sweep happened to find, without pinning a single byte. A verdict that
moves on its own is not a verdict.

The guard names `zeta/` specifically rather than stating a general rule about
nested claims, because the general rule has a deliberate exception: this claim
does pin one suite out of `examples/kernel/`, which is itself a claim
directory. A specific guard with its reason written down is worth more than a
general one carrying an exception list.

This claim does not require zeta to exist. The companion is optional; the
independence is not.
"""
import os
import sys

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import recipe

COMPANION = "zeta"


def _pinned(parsed):
    """Every path this claim's identity covers: inputs, and validated outputs.

    Generated outputs are excluded on purpose -- they are the equivalence
    class, not the boundary -- so they cannot smuggle a path in either.
    """
    paths = list(parsed["claim"].get("inputs", []) or [])
    for step in recipe._steps(parsed):
        if step.get("class") == "validated" and step.get("output"):
            paths.append(step["output"])
    return paths


def _under(path, directory):
    parts = os.path.normpath(path).replace(os.sep, "/").split("/")
    return parts[0] == directory


def battery():
    parsed = recipe.load_recipe(".")

    offenders = [p for p in _pinned(parsed) if _under(p, COMPANION)]
    assert not offenders, (
        f"the root must not pin anything under {COMPANION}/: {offenders}. "
        f"Promote a finding by writing a criterion here, not by pinning the queue")

    for gate in recipe.gates(parsed):
        command = gate.get("run", "") or ""
        tokens = command.replace("\\", "/").split()
        reached = [t for t in tokens
                   if t == COMPANION or t.startswith(f"{COMPANION}/")
                   or f"/{COMPANION}/" in t]
        assert not reached, (
            f"gate {gate.get('output')!r} reaches into {COMPANION}/: {reached}. "
            f"A verdict that depends on the last sweep is not a verdict")

    # If the companion is present it must be a separate claim, not a
    # subdirectory of this one. If it is absent, nothing here requires it.
    if os.path.isdir(COMPANION):
        own = os.path.join(COMPANION, "reticuli.toml")
        assert os.path.isfile(own), (
            f"{COMPANION}/ exists but carries no recipe of its own; a companion "
            f"is a claim with its own root, not a directory of scripts")
        companion = recipe.load_recipe(COMPANION)
        assert companion["claim"]["name"] != parsed["claim"]["name"], (
            "the companion must be a different claim; two bodies, separate orbits")

        # The queue in particular: undeclared findings, never an obligation.
        queue = os.path.join(COMPANION, "queue")
        if os.path.isdir(queue):
            pinned = _pinned(parsed)
            assert not any(_under(p, COMPANION) for p in pinned), \
                "a queued finding must not be reachable from this root"


if __name__ == "__main__":
    battery()
    with open("BOUNDARY_OK", "w", encoding="utf-8") as handle:
        handle.write("boundary-ok\n")
    print("boundary-ok")
