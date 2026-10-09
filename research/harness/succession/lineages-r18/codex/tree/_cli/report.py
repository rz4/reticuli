"""Text renderers for results returned by Reticuli commands.

The command layer can pass a result mapping to any action renderer.  These
functions only format results; they do not repeat an action or change a claim.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _row(label: str, value: Any) -> str:
    """Render one labelled fact."""
    return f"{label}: {value}"


def _when(value: Any) -> str:
    """Render a recorded time, retaining already formatted timestamps."""
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _generic_contract(command: str, result: Any = None) -> str:
    """Give every action a concise text form even for an empty result."""
    if result is None:
        return command
    if not isinstance(result, dict):
        return _row(command, result)
    lines = [command]
    for key, value in result.items():
        if isinstance(value, (list, tuple)):
            lines.append(_row(key, ", ".join(map(str, value))))
        elif isinstance(value, dict):
            lines.append(_row(key, ", ".join(f"{k}={v}" for k, v in value.items())))
        else:
            lines.append(_row(key, value))
    return "\n".join(lines)


def _r_verify(result: Any = None) -> str:
    return _generic_contract("verify", result)


def _r_audit(result: Any = None) -> str:
    return _generic_contract("audit", result)


def _r_assess(result: Any = None) -> str:
    return _generic_contract("assess", result)


def _r_rebuild(result: Any = None) -> str:
    return _generic_contract("rebuild", result)


def _r_seal(result: Any = None) -> str:
    return _generic_contract("seal", result)


def _r_crosscheck(result: Any = None) -> str:
    return _generic_contract("crosscheck", result)


def _r_record(result: Any = None) -> str:
    return _generic_contract("record", result)


def _r_sign(result: Any = None) -> str:
    return _generic_contract("sign", result)


def _r_export(result: Any = None) -> str:
    return _generic_contract("export", result)


def _r_pack(result: Any = None) -> str:
    return _generic_contract("pack", result)


def _r_attest(result: Any = None) -> str:
    return _generic_contract("attest", result)


def _r_attest_check(result: Any = None) -> str:
    return _generic_contract("attest-check", result)


def _r_hooks(result: Any = None) -> str:
    return _generic_contract("hooks", result)


def _r_import(result: Any = None) -> str:
    return _generic_contract("import", result)


def _r_init(result: Any = None) -> str:
    return _generic_contract("init", result)


def _r_pull(result: Any = None) -> str:
    return _generic_contract("pull", result)


def _r_review(result: Any = None) -> str:
    return _generic_contract("review", result)


def _r_sign_check(result: Any = None) -> str:
    return _generic_contract("sign-check", result)


def _t_init(result: Any = None) -> str:
    return _generic_contract("init", result)
