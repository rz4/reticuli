"""Human-readable renderers for claim command results.

Each renderer accepts a result mapping and returns text.  Keeping rendering
separate from command execution also lets JSON output use the original result.
"""

from __future__ import annotations

from collections.abc import Mapping

from .. import render


def _value(value):
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_value(item) for item in value) or "none"
    if isinstance(value, Mapping):
        return ", ".join(f"{key}={_value(item)}" for key, item in value.items()) or "none"
    return str(value)


def _row(label, value):
    """Format one labeled fact."""
    return f"{label}: {_value(value)}"


def _when(value):
    """Format a recorded time, preserving an unreadable value."""
    if not value:
        return "unknown"
    try:
        return render.ago(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _generic_contract(command, data=None):
    """Render a command result without discarding unrecognized fields."""
    if data is None and isinstance(command, Mapping):
        data = command
        command = "result"
    if not isinstance(data, Mapping):
        return f"{command}: {_value(data)}"
    lines = [f"{command}: {_value(data.get('verdict', data.get('status', data.get('ok', 'done'))))}"]
    for key, value in data.items():
        if key not in ("verdict", "status", "ok"):
            lines.append(_row(key.replace("_", " "), value))
    return "\n".join(lines)


def _render(command, data):
    return _generic_contract(command, data)


def _r_verify(data):
    return _render("verify", data)


def _r_audit(data):
    return _render("audit", data)


def _r_assess(data):
    return _render("assess", data)


def _r_rebuild(data):
    return _render("rebuild", data)


def _r_seal(data):
    return _render("seal", data)


def _r_crosscheck(data):
    return _render("crosscheck", data)


def _r_record(data):
    return _render("record", data)


def _r_sign(data):
    return _render("sign", data)


def _r_export(data):
    return _render("export", data)


def _r_pack(data):
    return _render("pack", data)


def _r_attest(data):
    return _render("attest", data)


def _r_attest_check(data):
    return _render("attest check", data)


def _r_hooks(data):
    return _render("hooks", data)


def _r_import(data):
    return _render("import", data)


def _r_init(data):
    return _render("init", data)


def _r_pull(data):
    return _render("pull", data)


def _r_review(data):
    return _render("review", data)


def _r_sign_check(data):
    return _render("sign check", data)


def _t_init(data):
    return _render("init", data)
