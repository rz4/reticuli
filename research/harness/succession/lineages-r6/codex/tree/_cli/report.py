"""Human-readable summaries of command results.

Renderers return text so the caller can choose stdout or stderr.  The
structured result remains available to the JSON output path unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from reticuli.render import ago, short


def _value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_value(item) for item in value) or "—"
    if isinstance(value, Mapping):
        return ", ".join(f"{key}={_value(item)}" for key, item in value.items()) or "—"
    return str(value)


def _row(label: str, value: Any) -> str:
    """Format one labelled detail without discarding false or zero values."""
    return f"{label}: {_value(value)}"


def _when(value: Any) -> str:
    """Show a timestamp relative to now, preserving unknown timestamps."""
    if value is None or value == "":
        return "—"
    try:
        return ago(value)
    except (TypeError, ValueError, OverflowError, AttributeError):
        return str(value)


def _generic_contract(command: str, result: Any, *, details: tuple[str, ...] = ()) -> str:
    """Render the common result fields and any command-specific details."""
    if not isinstance(result, Mapping):
        return f"{command}: {_value(result)}"
    status = result.get("status", result.get("verdict"))
    if status is None:
        status = "ok" if result.get("ok", result.get("satisfied", False)) else "failed"
    lines = [f"{command}: {status}"]
    if result.get("root"):
        lines.append(_row("root", result["root"]))
    for key in details:
        if key in result:
            lines.append(_row(key.replace("_", " "), result[key]))
    return "\n".join(lines)


def _r_verify(result: Any) -> str:
    return _generic_contract("verify", result, details=("name", "recomputed"))


def _r_audit(result: Any) -> str:
    return _generic_contract("audit", result, details=("gates", "environment", "layers"))


def _r_assess(result: Any) -> str:
    return _generic_contract("assess", result, details=("measured", "not_measured", "not_applicable"))


def _r_rebuild(result: Any) -> str:
    return _generic_contract("rebuild", result, details=("name", "gates", "quarantine", "rebuilt_components"))


def _r_seal(result: Any) -> str:
    return _generic_contract("seal", result, details=("name",))


def _r_crosscheck(result: Any) -> str:
    return _generic_contract("crosscheck", result, details=("rejected", "incomplete", "roots", "cost", "independence"))


def _r_record(result: Any) -> str:
    return _generic_contract("record", result, details=("name", "build_digest", "gates", "cost", "when"))


def _r_sign(result: Any) -> str:
    return _generic_contract("sign", result, details=("identity", "statement", "proof_recorded"))


def _r_export(result: Any) -> str:
    return _generic_contract("export", result, details=("path",))


def _r_pack(result: Any) -> str:
    return _generic_contract("pack", result, details=("name",))


def _r_attest(result: Any) -> str:
    return _generic_contract("attest", result, details=("identity", "statement"))


def _r_attest_check(result: Any) -> str:
    return _generic_contract("attest check", result, details=("attestations",))


def _r_hooks(result: Any) -> str:
    return _generic_contract("hooks", result, details=("wired",))


def _r_import(result: Any) -> str:
    return _generic_contract("import", result, details=("name",))


def _r_init(result: Any) -> str:
    return _generic_contract("init", result, details=("path", "workspace"))


def _r_pull(result: Any) -> str:
    return _generic_contract("pull", result, details=("materialized",))


def _r_review(result: Any) -> str:
    return _generic_contract("review", result, details=("build_digest", "sign_root", "audit", "proof"))


def _r_sign_check(result: Any) -> str:
    return _generic_contract("sign check", result, details=("authorizations",))


def _t_init(result: Any) -> str:
    if isinstance(result, Mapping):
        return f"init {short(result.get('path', result.get('workspace', '')))}".rstrip()
    return f"init {_value(result)}"
