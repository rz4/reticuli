"""Human-readable reports for CLI actions.

The command layer owns the result objects.  Renderers in this module accept
those objects and return text, leaving printing and JSON envelopes to output.
"""

from __future__ import annotations

import datetime

from .. import render


def _row(label, value):
    """Format one named fact, including false and zero values."""
    return f"{label}: {value}"


def _when(value):
    """Display a timestamp without changing the instant it describes."""
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return str(value) if value is not None else "unknown"


def _generic_contract(command, data=None):
    """Render the stable facts shared by command results."""
    if data is None and isinstance(command, dict):
        data, command = command, "result"
    if not isinstance(data, dict):
        return _row(command, data)
    lines = [str(command)]
    for key, value in data.items():
        if key == "gates" and isinstance(value, list):
            lines.extend(_row(gate.get("output", "gate"), gate.get("status", "unknown"))
                         if isinstance(gate, dict) else str(gate) for gate in value)
        elif isinstance(value, (dict, list)):
            lines.append(_row(key, render.tree(value)))
        else:
            lines.append(_row(key, value))
    return "\n".join(lines)


def _r_verify(data):
    return _generic_contract("verify", data)


def _r_audit(data):
    return _generic_contract("audit", data)


def _r_assess(data):
    return _generic_contract("assess", data)


def _r_rebuild(data):
    return _generic_contract("rebuild", data)


def _r_seal(data):
    return _generic_contract("seal", data)


def _r_crosscheck(data):
    return _generic_contract("crosscheck", data)


def _r_record(data):
    return _generic_contract("record", data)


def _r_sign(data):
    return _generic_contract("sign", data)


def _r_export(data):
    return _generic_contract("export", data)


def _r_pack(data):
    return _generic_contract("pack", data)


def _r_attest(data):
    return _generic_contract("attest", data)


def _r_attest_check(data):
    return _generic_contract("attest check", data)


def _r_hooks(data):
    return _generic_contract("hooks", data)


def _r_import(data):
    return _generic_contract("import", data)


def _r_init(data):
    return _generic_contract("init", data)


def _r_pull(data):
    return _generic_contract("pull", data)


def _r_review(data):
    return _generic_contract("review", data)


def _r_sign_check(data):
    return _generic_contract("sign check", data)


def _t_init(data):
    return _generic_contract("init", data)
