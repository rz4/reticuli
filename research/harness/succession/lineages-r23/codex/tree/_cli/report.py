"""Human and JSON result renderers for command-line actions.

The individual entry points keep each verb's name in the output envelope;
the shared contract applies the same success and status rules to all of them.
"""

from __future__ import annotations

from types import SimpleNamespace

from .output import _finish


def _row(label, value):
    """Format one labelled fact for a human-readable report."""
    return f"{label}: {value}"


def _when(condition, value, otherwise=""):
    """Choose optional report text without printing an empty line."""
    return value if condition else otherwise


def _generic_contract(command, data, args=None, *, ok=None, status=None):
    """Emit the common CLI result envelope and return its exit status."""
    if args is None:
        args = SimpleNamespace(json=False, verbose=False)
    if ok is None:
        ok = data.get("ok", data.get("satisfied", True)) if isinstance(data, dict) else True
    if status is None:
        if isinstance(data, dict):
            status = data.get("status") or data.get("verdict")
        status = status or ("ok" if ok else "failed")
    return _finish(command, data, ok, status, args)


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


def _t_init(data):
    """Terse initialization summary."""
    if isinstance(data, dict):
        return data.get("path") or data.get("directory") or data.get("name") or "initialized"
    return str(data)
