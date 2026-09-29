"""Text renderers for the result of a Reticuli command.

The command implementations own the facts.  These helpers only turn their
result dictionaries into short, readable lines for the text interface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _row(label: str, value: Any) -> str:
    """Render one labelled fact, omitting facts that were not measured."""
    if value is None:
        return ""
    if isinstance(value, bool):
        value = "yes" if value else "no"
    return f"{label}: {value}"


def _when(value: Any) -> str:
    """Display a timestamp without changing the instant it represents."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _generic_contract(command: str, result: Any) -> str:
    """Summarize a command result while keeping failure details visible."""
    if not isinstance(result, dict):
        return f"{command}: {result}" if result is not None else command

    status = result.get("status") or result.get("verdict")
    if status is None:
        if result.get("ok") is True or result.get("satisfied") is True:
            status = "ok"
        elif result.get("ok") is False or result.get("satisfied") is False:
            status = "failed"
        else:
            status = "complete"
    lines = [f"{command}: {status}"]
    for key in ("name", "root", "path", "output", "phase", "build_digest",
                "statement", "signature", "packet", "proof_recorded"):
        if key in result:
            line = _row(key.replace("_", " "), result[key])
            if line:
                lines.append(line)
    for key in ("rejected", "incomplete", "environment"):
        value = result.get(key)
        if value:
            lines.append(_row(key, ", ".join(map(str, value)) if isinstance(value, list) else value))
    return "\n".join(lines)


def _r_verify(result: Any) -> str:
    return _generic_contract("verify", result)


def _r_audit(result: Any) -> str:
    return _generic_contract("audit", result)


def _r_assess(result: Any) -> str:
    return _generic_contract("assess", result)


def _r_rebuild(result: Any) -> str:
    return _generic_contract("rebuild", result)


def _r_seal(result: Any) -> str:
    return _generic_contract("seal", result)


def _r_crosscheck(result: Any) -> str:
    return _generic_contract("crosscheck", result)


def _r_record(result: Any) -> str:
    return _generic_contract("record", result)


def _r_sign(result: Any) -> str:
    return _generic_contract("sign", result)


def _r_export(result: Any) -> str:
    return _generic_contract("export", result)


def _r_pack(result: Any) -> str:
    return _generic_contract("pack", result)


def _r_attest(result: Any) -> str:
    return _generic_contract("attest", result)


def _r_attest_check(result: Any) -> str:
    return _generic_contract("attest check", result)


def _r_hooks(result: Any) -> str:
    return _generic_contract("hooks", result)


def _r_import(result: Any) -> str:
    return _generic_contract("import", result)


def _r_init(result: Any) -> str:
    return _generic_contract("init", result)


def _r_pull(result: Any) -> str:
    return _generic_contract("pull", result)


def _r_review(result: Any) -> str:
    return _generic_contract("review", result)


def _r_sign_check(result: Any) -> str:
    return _generic_contract("sign check", result)


def _t_init(result: Any) -> str:
    return _r_init(result)
