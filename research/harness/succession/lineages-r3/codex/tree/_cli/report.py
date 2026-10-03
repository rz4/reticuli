"""Human-readable reports for CLI actions.

These functions format result dictionaries; the command dispatcher owns I/O.
"""

from __future__ import annotations

import datetime
import json


def _when(value):
    """Render a recorded UTC time, leaving unknown values explicit."""
    if value is None or value == "":
        return "unmeasured"
    if isinstance(value, datetime.datetime):
        return value.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(value)


def _row(label, value):
    """Format a labelled fact as one line."""
    if isinstance(value, bool):
        value = "yes" if value else "no"
    elif value is None:
        value = "unmeasured"
    elif isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True)
    return f"{label}: {value}"


def _generic_contract(command, result, *, verbose=False):
    """Render the common result shape without discarding diagnostic fields."""
    if not isinstance(result, dict):
        return _row(command, result)
    status = result.get("status", result.get("verdict"))
    if status is None:
        status = "ok" if result.get("ok", result.get("satisfied", True)) else "failed"
    lines = [_row(command, status)]
    if result.get("root"):
        lines.append(_row("root", result["root"]))
    if result.get("detail"):
        lines.append(_row("detail", result["detail"]))
    if verbose:
        for key, value in result.items():
            if key not in {"status", "verdict", "root", "detail", "ok", "satisfied"}:
                lines.append(_row(key.replace("_", " "), value))
    return "\n".join(lines)


def _render(command, result, verbose=False):
    return _generic_contract(command, result, verbose=verbose)


def _r_verify(result, verbose=False):
    return _render("verify", result, verbose)


def _r_audit(result, verbose=False):
    return _render("audit", result, verbose)


def _r_assess(result, verbose=False):
    return _render("assess", result, verbose)


def _r_rebuild(result, verbose=False):
    return _render("rebuild", result, verbose)


def _r_seal(result, verbose=False):
    return _render("seal", result, verbose)


def _r_crosscheck(result, verbose=False):
    return _render("crosscheck", result, verbose)


def _r_record(result, verbose=False):
    return _render("record", result, verbose)


def _r_sign(result, verbose=False):
    return _render("sign", result, verbose)


def _r_export(result, verbose=False):
    return _render("export", result, verbose)


def _r_pack(result, verbose=False):
    return _render("pack", result, verbose)


def _r_attest(result, verbose=False):
    return _render("attest", result, verbose)


def _r_attest_check(result, verbose=False):
    return _render("attest check", result, verbose)


def _r_hooks(result, verbose=False):
    return _render("hooks", result, verbose)


def _r_import(result, verbose=False):
    return _render("import", result, verbose)


def _r_init(result, verbose=False):
    return _render("init", result, verbose)


def _r_pull(result, verbose=False):
    return _render("pull", result, verbose)


def _r_review(result, verbose=False):
    return _render("review", result, verbose)


def _r_sign_check(result, verbose=False):
    return _render("sign check", result, verbose)


def _t_init(result, verbose=False):
    return _render("init", result, verbose)
