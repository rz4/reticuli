"""Human-readable renderers for command results.

The result mappings come from the kernel and the layers above it.  Keeping
these functions free of filesystem effects lets the CLI select text or JSON
without changing the operation that produced the result.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import views


def _when(value):
    """Display a UTC timestamp, leaving unknown values alone."""
    if value is None:
        return "unknown"
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _row(label, value=None):
    """A single labelled line for a text report."""
    if value is None:
        return str(label)
    if isinstance(value, bool):
        value = "yes" if value else "no"
    elif isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return f"{label}: {value}"


def _generic_contract(command, result=None):
    """Render the stable facts common to command results."""
    if result is None:
        result = command
        command = "result"
    if not isinstance(result, dict):
        return _row(command, result)
    lines = [_row(command, result.get("status", result.get("verdict", "ok" if result.get("ok") else "result")))]
    for key in ("name", "root", "phase", "build_digest", "path", "quarantine"):
        if key in result:
            lines.append(_row(key, result[key]))
    for key in sorted(result):
        if key not in {"name", "root", "phase", "build_digest", "path", "quarantine", "status", "verdict", "ok"}:
            lines.append(_row(key, result[key]))
    return "\n".join(lines)


def _render(command, result=None):
    return _generic_contract(command, result)


def _r_verify(result):
    return _render("verify", result)


def _r_audit(result):
    return _render("audit", result)


def _r_assess(result):
    return _render("assess", result)


def _r_rebuild(result):
    return _render("rebuild", result)


def _r_seal(result):
    return _render("seal", result)


def _r_crosscheck(result):
    return _render("crosscheck", result)


def _r_record(result):
    return _render("record", result)


def _r_sign(result):
    return _render("sign", result)


def _r_export(result):
    return _render("export", result)


def _r_pack(result):
    return _render("pack", result)


def _r_attest(result):
    return _render("attest", result)


def _r_attest_check(result):
    return _render("attest check", result)


def _r_hooks(result):
    return _render("hooks", result)


def _r_import(result):
    return _render("import", result)


def _r_init(result):
    return _render("init", result)


def _r_pull(result):
    return _render("pull", result)


def _r_review(result):
    return _render("review", result)


def _r_sign_check(result):
    return _render("sign check", result)


def _t_init(result):
    if isinstance(result, dict):
        return _row("init", result.get("path", result.get("status", "ready")))
    return _row("init", result)
