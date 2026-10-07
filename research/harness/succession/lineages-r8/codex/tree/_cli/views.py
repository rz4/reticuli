"""Read a claim into a compact state view for CLI presentation."""

from __future__ import annotations

import json
import os
from pathlib import Path

from reticuli import kernel


def _read_residue(directory: str, name: str) -> object | None:
    """Read optional JSON residue without treating its absence as a claim error."""
    path = Path(directory) / kernel.STORE / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None


def _signatures(directory: str) -> list[str]:
    path = Path(directory) / kernel.SIGN_DIR
    try:
        return sorted(entry.name for entry in path.iterdir()
                      if entry.is_file() and entry.name.endswith(".sign.json"))
    except OSError:
        return []


def _verified(directory: str) -> dict:
    """Identity verification, including a readable result for an unsealed draft."""
    try:
        return kernel.verify(directory)
    except kernel.ClaimError as exc:
        return {"ok": False, "reason": str(exc)}


def _phase(directory: str) -> str:
    return kernel.phase(directory)


def _gate_ok(gate: dict) -> bool:
    return gate.get("status") in ("ok", "reproduced")


def _verdict(value: dict | None) -> str:
    if not value:
        return "unmeasured"
    if value.get("ok") is True:
        return str(value.get("verdict", "earned"))
    return str(value.get("verdict", "carried or broken"))


def _deciding_words(recipe: dict) -> list[str]:
    words: list[str] = []
    for step in recipe.get("step", []):
        if step.get("kind") == "gate":
            words.extend(kernel.gate_deciders(step["run"]))
    return list(dict.fromkeys(words))


def _next_step(view: dict) -> str:
    """Name the next action on the claim's draft → sealed → signed ladder."""
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "seal"
    if not view.get("verified", {}).get("ok", False):
        return "verify"
    if phase == "signed":
        return "audit"
    if not view.get("proof"):
        return "crosscheck"
    return "sign"


def _claim_view(directory: os.PathLike[str] | str) -> dict:
    """Summarize declared identity, present bytes, and recorded evidence."""
    path = os.fspath(directory)
    recipe = kernel.load_recipe(path)
    checked = _verified(path)
    try:
        manifest = kernel.read_manifest(path)
    except kernel.ClaimError:
        manifest = {}
    phase = _phase(path)
    outputs = [step["output"] for step in recipe.get("step", [])
               if step.get("kind") == "produce"
               and step.get("class", "generated") in ("generated", "free")]
    view = {
        "name": recipe["claim"]["name"],
        "root": manifest.get("root"),
        "phase": phase,
        "verified": checked,
        "proof": manifest.get("proof"),
        "signatures": _signatures(path),
        "generated": [{"output": name, "present": (Path(path) / name).is_file()}
                      for name in outputs],
        "gates": [step["output"] for step in recipe.get("step", [])
                  if step.get("kind") == "gate"],
        "deciders": _deciding_words(recipe),
        "cost": kernel.cost(path),
    }
    view["next"] = _next_step(view)
    return view
