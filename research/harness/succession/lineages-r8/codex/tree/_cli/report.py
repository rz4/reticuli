"""Human readable reports for the action commands.

The command layer owns execution and JSON output; these helpers only turn
results from the lower layers into short, printable summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .output import _line


def _row(label: str, value: Any) -> None:
    """Print one labelled result, omitting values that were not measured."""
    if value is not None:
        _line(f"{label}: {value}")


def _when(value: Any) -> str:
    """Show a recorded time without assuming every result has a timestamp."""
    if value is None or value == "":
        return "unknown"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return str(value)


def _generic_contract(command: str, result: Any, *_, **__) -> Any:
    """Render the shared result vocabulary used by the action verbs."""
    if not isinstance(result, dict):
        _row(command, result)
        return result
    status = result.get("status") or result.get("verdict")
    if status is None:
        status = "ok" if result.get("ok", True) else "failed"
    _line(f"{command}: {status}")
    for key in ("name", "root", "build_digest", "phase", "reason", "detail",
                "path", "statement", "signature", "identity"):
        if key in result:
            _row(key.replace("_", " "), result[key])
    for key in ("gates", "layers", "attestations", "authorizations"):
        rows = result.get(key)
        if isinstance(rows, list):
            for item in rows:
                if isinstance(item, dict):
                    label = item.get("output") or item.get("name") or key[:-1]
                    _row(str(label), item.get("status") or item.get("verdict") or
                         ("ok" if item.get("ok") else "failed"))
                else:
                    _row(key[:-1], item)
    return result


def _r_verify(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("verify", result, *args, **kwargs)


def _r_audit(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("audit", result, *args, **kwargs)


def _r_assess(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("assess", result, *args, **kwargs)


def _r_rebuild(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("rebuild", result, *args, **kwargs)


def _r_seal(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("seal", result, *args, **kwargs)


def _r_crosscheck(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("crosscheck", result, *args, **kwargs)


def _r_record(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("record", result, *args, **kwargs)


def _r_sign(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("sign", result, *args, **kwargs)


def _r_export(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("export", result, *args, **kwargs)


def _r_pack(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("pack", result, *args, **kwargs)


def _r_attest(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("attest", result, *args, **kwargs)


def _r_attest_check(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("attest check", result, *args, **kwargs)


def _r_hooks(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("hooks", result, *args, **kwargs)


def _r_import(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("import", result, *args, **kwargs)


def _r_init(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("init", result, *args, **kwargs)


def _r_pull(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("pull", result, *args, **kwargs)


def _r_review(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("review", result, *args, **kwargs)


def _r_sign_check(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _generic_contract("sign check", result, *args, **kwargs)


def _t_init(result: Any, *args: Any, **kwargs: Any) -> Any:
    return _r_init(result, *args, **kwargs)
