"""Measuring how much a claim's tests prove.

The kernel's `mutation_score` draws a capped, deterministic sample of
mutants and reports a kill rate; `assess` puts that number in context by
bucketing the claim's generated Python surface into what the sample actually
exercised, what exists but the cap left untouched, and what mutation testing
cannot speak to at all (non-Python output, or output not yet produced). A
mutation floor read in isolation cannot tell those apart -- a 100% kill rate
over two mutants sampled from a sprawling module says far less than the same
rate over two mutants that were all there were.

Stdlib only.
"""
import ast
import os

from reticuli import kernel

_MUTABLE_NODES = (ast.Compare, ast.BinOp, ast.If, ast.Return, ast.Break, ast.Continue)


def _generated_outputs(doc: dict) -> list:
    outputs = []
    for step in doc.get("step") or []:
        if step.get("kind") != "produce":
            continue
        cls = step.get("class", "generated")
        if cls not in ("generated", "free"):
            continue
        output = step.get("output")
        if isinstance(output, str):
            outputs.append(output)
    return outputs


def _mutable_sites(source: str) -> int:
    """A rough, independent count of constructs mutation testing could
    touch in `source` -- used only to size the "not yet measured" bucket.
    The kernel's own mutant generator (`spec/verification.md`) remains the
    one that actually decides and runs mutants; this never duplicates that
    decision, only estimates its scale cheaply, without running anything.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    return sum(1 for node in ast.walk(tree) if isinstance(node, _MUTABLE_NODES))


def assess(d: str, mutants=None) -> dict:
    """How much claim `d`'s tests prove, bucketed:

    - `measured`: mutants the kernel actually sampled and ran (killed or
      survived) within the cap.
    - `not_measured`: mutable sites estimated to exist in the claim's
      generated Python but left unsampled by the cap.
    - `not_applicable`: generated outputs mutation testing cannot touch --
      not Python, or not present on disk to mutate.

    Alongside the buckets, the kernel's own mutation result is carried
    through (`killed`, `rate`, `survivors`) so neither number is read
    without the other.
    """
    doc = kernel.load_recipe(d)

    not_applicable = 0
    estimated_sites = 0
    for rel in _generated_outputs(doc):
        path = os.path.join(d, rel)
        if not rel.endswith(".py") or not os.path.isfile(path):
            not_applicable += 1
            continue
        with open(path, "r", encoding="utf-8") as f:
            estimated_sites += _mutable_sites(f.read())

    score = kernel.mutation_score(d, max_mutants=mutants)
    measured = score["mutants"]
    not_measured = max(estimated_sites - measured, 0)

    return {
        "measured": measured,
        "not_measured": not_measured,
        "not_applicable": not_applicable,
        "killed": score["killed"],
        "rate": score["rate"],
        "survivors": score["survivors"],
    }
