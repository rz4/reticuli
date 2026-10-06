"""Human-readable summaries of results from CLI action verbs.

These functions format data; the command layer decides where to write it.
Keeping that boundary here also makes the same results usable by JSON output.
"""

from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Mapping

from .. import render


def _when(value: object) -> str:
    """Format an optional UTC timestamp for display."""
    if value is None or value == "":
        return "unknown"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _row(label: object, value: object = None) -> str:
    """Format one labeled detail, including false and zero values."""
    if isinstance(label, Mapping) and value is None:
        return "\n".join(_row(key, item) for key, item in label.items())
    if isinstance(value, bool):
        value = "yes" if value else "no"
    elif value is None:
        value = "unknown"
    elif isinstance(value, (list, tuple)):
        value = ", ".join(map(str, value)) or "none"
    elif isinstance(value, Mapping):
        value = ", ".join(f"{key}={item}" for key, item in value.items()) or "none"
    return f"{label}: {value}"


def _generic_contract(command: str, result: Mapping | None = None,
                      *, verbose: bool = False) -> str:
    """Render a result summary and, on request, its available evidence."""
    data = result or {}
    status = data.get("status", data.get("verdict"))
    if status is None:
        status = "ok" if data.get("ok", data.get("satisfied", True)) else "failed"
    headline = f"{command}: {status}"
    root = data.get("root")
    if root:
        headline += f" {root}"
    if not verbose:
        return headline
    details = [_row(key, value) for key, value in data.items()
               if key not in ("status", "verdict", "root")]
    return "\n".join([headline, *details])


def _r_verify(result=None, *, verbose=False):
    return _generic_contract("verify", result, verbose=verbose)


def _r_audit(result=None, *, verbose=False):
    return _generic_contract("audit", result, verbose=verbose)


def _r_assess(result=None, *, verbose=False):
    return _generic_contract("assess", result, verbose=verbose)


def _r_rebuild(result=None, *, verbose=False):
    return _generic_contract("rebuild", result, verbose=verbose)


def _r_seal(result=None, *, verbose=False):
    return _generic_contract("seal", result, verbose=verbose)


def _r_crosscheck(result=None, *, verbose=False):
    return _generic_contract("crosscheck", result, verbose=verbose)


def _r_record(result=None, *, verbose=False):
    return _generic_contract("record", result, verbose=verbose)


def _r_sign(result=None, *, verbose=False):
    return _generic_contract("sign", result, verbose=verbose)


def _r_export(result=None, *, verbose=False):
    return _generic_contract("export", result, verbose=verbose)


def _r_pack(result=None, *, verbose=False):
    return _generic_contract("pack", result, verbose=verbose)


def _r_attest(result=None, *, verbose=False):
    return _generic_contract("attest", result, verbose=verbose)


def _r_attest_check(result=None, *, verbose=False):
    return _generic_contract("attest check", result, verbose=verbose)


def _r_hooks(result=None, *, verbose=False):
    return _generic_contract("hooks", result, verbose=verbose)


def _r_import(result=None, *, verbose=False):
    return _generic_contract("import", result, verbose=verbose)


def _r_init(result=None, *, verbose=False):
    return _generic_contract("init", result, verbose=verbose)


def _r_pull(result=None, *, verbose=False):
    return _generic_contract("pull", result, verbose=verbose)


def _r_review(result=None, *, verbose=False):
    return _generic_contract("review", result, verbose=verbose)


def _r_sign_check(result=None, *, verbose=False):
    return _generic_contract("sign check", result, verbose=verbose)


def _t_init(result=None):
    return _r_init(result)
