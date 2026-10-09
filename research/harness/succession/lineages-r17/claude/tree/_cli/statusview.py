"""The status/draft/tree family (`spec/layers.md`: surface, `_cli/statusview.py`).

`views._claim_view` reads a sealed claim into the documented state dict;
the functions here turn that dict (and the sibling data `registry`/
`feedback` hand back) into the terse and verbose text a human reads, plus
the plain tables `--json` callers skip entirely. Presentation only, same
discipline as `report.py`: no identity, no filesystem writes beyond the
read-only listing `_files_claim` does, no judging.

`_t_status_claim` is the one-line form (`ret status`); `_v_status_claim` is
the full multi-line form (`ret status -v`); `_ledger_status_claim` is the
accumulated-cost line neither carries, read fresh from the claim's own
ledger. `_files_claim` lists every path a claim's recipe declares against
what is actually present on disk. `_r_status_draft` renders
`feedback.advise`'s sealability probe. `_r_claims`/`_r_deps`/`_r_tree`/
`_r_structure` render `registry.claims`/`registry.deps` four ways: a plain
table, a flat table of dependency edges, an indented tree, and a grouped
per-claim listing.

`_DECLARED_ROLE` names the three crosscheck positions a relayed record can
stand in (`spec/verification.md`: M1/M2/M3) -- used to label the recorded
proof's embedded record legs (`spec/record.md`: "a proof built from
records names its records").

Stdlib only.
"""
import os

from reticuli import _util, kernel, render
from reticuli._cli import output

_DECLARED_ROLE = {
    "M1": "original workspace",
    "M2": "transfer",
    "M3": "independent rebuild",
}


# =============================================================================
# a claim's status: terse, verbose, ledger
# =============================================================================

_VERIFIED_MARK = {True: "+", False: "!", None: "?"}


def _t_status_claim(view: dict) -> str:
    """One terse line: name, short root, phase, and a verified mark
    (`+` holds, `!` drifted, `?` no sealed manifest to check against)."""
    mark = _VERIFIED_MARK.get(view.get("verified"), "?")
    return (f"{view.get('name', '')}  {render.short(view.get('root') or '')}  "
            f"{view.get('phase', '')}  {mark}")


def _v_status_claim(view: dict) -> str:
    """The full multi-line rendering of `views._claim_view`'s state dict:
    name, root, phase, verified, every gate's own verdict, who signed,
    the recorded proof's legs (labeled by `_DECLARED_ROLE`), and the
    ladder's recommended next rung."""
    lines = [
        f"name: {view.get('name', '')}",
        f"root: {view.get('root', '')}",
        f"phase: {view.get('phase', '')}",
        f"verified: {view.get('verified')}",
    ]
    for gate in view.get("gates", []):
        lines.append(f"  gate {gate.get('output')}: {gate.get('verdict')}")
    signatures = view.get("signatures") or []
    lines.append(f"signed by: {', '.join(signatures) if signatures else '--'}")

    residue = view.get("residue") or {}
    proof = residue.get("proof")
    if proof:
        for record in proof.get("records", []):
            leg = record.get("leg", "?")
            role = _DECLARED_ROLE.get(leg, leg)
            lines.append(f"  {leg} ({role}): signer={record.get('signer')} "
                         f"digest={render.short(record.get('digest') or '')}")
    mutation = residue.get("mutation_score")
    if mutation:
        lines.append(f"mutation score: {mutation.get('rate')}")

    lines.append(f"next: {view.get('next', '')}")
    return "\n".join(lines)


def _ledger_status_claim(d: str) -> str:
    """The claim's accumulated production cost (`kernel.cost`), one short
    line; `"cost: unmeasured"` when the ledger carries nothing."""
    totals = kernel.cost(d)
    if not totals:
        return "cost: unmeasured"
    parts = ", ".join(f"{k}={v}" for k, v in sorted(totals.items()))
    return f"cost: {parts}"


# =============================================================================
# files: every declared path against what is actually present
# =============================================================================

def _files_claim(d: str) -> list:
    """Every path `d`'s recipe declares -- pinned inputs, then every step's
    output in recipe order -- with its step class and whether it is present
    on disk. Display-only: it does not re-hash anything (`verify`'s job)."""
    try:
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError:
        return []

    rows = []
    seen = set()
    for name in _util.declared_inputs(d):
        if name in seen:
            continue
        seen.add(name)
        rows.append({"path": name, "class": "input",
                     "present": os.path.isfile(os.path.join(d, name))})
    for step in parsed.get("step", []):
        output_name = step.get("output")
        if not output_name or output_name in seen:
            continue
        seen.add(output_name)
        cls = step.get("class") or (
            "generated" if step.get("kind") == "produce" else "pinned")
        rows.append({"path": output_name, "class": cls,
                     "present": os.path.isfile(os.path.join(d, output_name))})
    return rows


# =============================================================================
# a draft session's sealability (`feedback.advise`)
# =============================================================================

def _r_status_draft(args, result: dict) -> bool:
    """Render `feedback.advise`'s probe of a session's trace: sealable now,
    or not yet and why."""
    sealable = result.get("sealable", False)
    output._finish("status", result, sealable,
                    "sealable" if sealable else "not-sealable", args)
    if not sealable and result.get("reason"):
        output._line(args, f"  {result['reason']}")
    return sealable


# =============================================================================
# the workspace's claims, as a table, a tree, and a dependency graph
# =============================================================================

def _r_claims(args, claims_list: list) -> None:
    """Render `registry.claims(ws)` as a plain table: name, short root,
    phase."""
    rows = [(c.get("name", ""), render.short(c.get("root") or ""),
             c.get("phase", "")) for c in claims_list]
    output._line(args, render.table(rows, headers=("name", "root", "phase")))


def _r_tree(args, claims_list: list) -> None:
    """Render `registry.claims(ws)` as an indented tree, one line per
    claim (name, short root, phase)."""
    rows = [f"{c.get('name', '')}  {render.short(c.get('root') or '')}  "
            f"{c.get('phase', '')}" for c in claims_list]
    output._line(args, render.tree({"claims": rows}))


def _r_structure(args, deps_result: dict) -> None:
    """Render `registry.deps(ws)` grouped per claim: each claim's name,
    then one line per declared component link and its current status."""
    for claim in deps_result.get("claims", []):
        output._line(args, claim.get("name", ""))
        for link in claim.get("depends_on", []):
            output._line(
                args,
                f"  {link.get('input')} -> {link.get('component')} "
                f"({link.get('status')})")


def _r_deps(args, deps_result: dict) -> None:
    """Render `registry.deps(ws)` as a flat table of dependency edges:
    claim, input, component, status -- the same data `_r_structure` groups
    per claim, laid out for scanning across claims instead of within one."""
    rows = []
    for claim in deps_result.get("claims", []):
        for link in claim.get("depends_on", []):
            rows.append((claim.get("name", ""), link.get("input", ""),
                         link.get("component", ""), link.get("status", "")))
    output._line(args, render.table(
        rows, headers=("claim", "input", "component", "status")))
