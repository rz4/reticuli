"""Text renderers for the results of CLI actions.

The action modules own the result data.  This module only turns that data into
readable lines; JSON output is handled by :mod:`reticuli._cli.output`.
"""

from __future__ import annotations

from datetime import datetime
import json


def _when(value):
    """Return a readable timestamp, leaving unknown timestamp forms intact."""
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _row(label, value):
    """Format one labelled fact for a terminal report."""
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    elif value is None:
        value = "unknown"
    return f"{label}: {value}"


def _generic_contract(command, data=None):
    """Render a command result without changing or inferring its verdict."""
    if data is None:
        data = command
        command = "result"
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return _row(command, data)
    lines = [str(command)]
    lines.extend(_row(key, value) for key, value in data.items())
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
