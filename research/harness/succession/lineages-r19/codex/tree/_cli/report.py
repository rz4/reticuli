"""Human-readable summaries of CLI command results.

The command handlers own the operation and its result.  This module only
turns that result into a short display; structured output is handled by
``output._finish``.
"""

from __future__ import annotations

from datetime import datetime

from . import output


def _row(label, value):
    """Format one labelled field for a detailed command view."""
    return f"{label}: {value}"


def _when(value):
    """Return a readable timestamp, preserving values already formatted."""
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _generic_contract(command, data, args=None, *, ok=None, status=None, root=None):
    """Render a command result through the shared text/JSON contract."""
    if ok is None:
        ok = data.get("ok", True) if isinstance(data, dict) else True
    if status is None:
        if isinstance(data, dict):
            status = data.get("status") or ("ok" if ok else "failed")
        else:
            status = "ok" if ok else "failed"
    return output._finish(command, data, ok, status, args, root=root)


def _r_verify(data, args=None):
    return _generic_contract("verify", data, args)


def _r_audit(data, args=None):
    return _generic_contract("audit", data, args)


def _r_assess(data, args=None):
    return _generic_contract("assess", data, args)


def _r_rebuild(data, args=None):
    return _generic_contract("rebuild", data, args)


def _r_seal(data, args=None):
    return _generic_contract("seal", data, args)


def _r_crosscheck(data, args=None):
    return _generic_contract("crosscheck", data, args)


def _r_record(data, args=None):
    return _generic_contract("record", data, args)


def _r_sign(data, args=None):
    return _generic_contract("sign", data, args)


def _r_export(data, args=None):
    return _generic_contract("export", data, args)


def _r_pack(data, args=None):
    return _generic_contract("pack", data, args)


def _r_attest(data, args=None):
    return _generic_contract("attest", data, args)


def _r_attest_check(data, args=None):
    return _generic_contract("attest-check", data, args)


def _r_hooks(data, args=None):
    return _generic_contract("hooks", data, args)


def _r_import(data, args=None):
    return _generic_contract("import", data, args)


def _r_init(data, args=None):
    return _generic_contract("init", data, args)


def _r_pull(data, args=None):
    return _generic_contract("pull", data, args)


def _r_review(data, args=None):
    return _generic_contract("review", data, args)


def _r_sign_check(data, args=None):
    return _generic_contract("sign-check", data, args)


def _t_init(data, args=None):
    return _r_init(data, args)
