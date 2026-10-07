"""Readable summaries of results returned by the command line's verbs.

The functions return text so callers can choose where to write it.  Result
dictionaries remain the source of truth; rendering never changes them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _when(value: Any) -> str:
    """Show a timestamp as supplied, or an empty value when absent."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _row(label: str, value: Any) -> str:
    """Render one labelled fact without losing false or zero values."""
    if isinstance(value, bool):
        shown = "yes" if value else "no"
    elif value is None:
        shown = "unknown"
    elif isinstance(value, (dict, list, tuple)):
        shown = json.dumps(value, sort_keys=True, default=str)
    else:
        shown = str(value)
    return f"{label}: {shown}"


def _generic_contract(command: str, result: Any) -> str:
    """Render the common result shape and retain any command-specific facts."""
    if not isinstance(result, dict):
        return _row(command, result)
    ordered = ("status", "ok", "name", "root", "verdict", "satisfied",
               "phase", "build_digest", "archive", "statement", "signature")
    lines = [command]
    for key in ordered:
        if key in result:
            lines.append(_row(key, result[key]))
    for key in sorted(result.keys() - set(ordered)):
        lines.append(_row(key, result[key]))
    return "\n".join(lines)


def _render(command: str, result: Any) -> str:
    return _generic_contract(command, result)


def _r_verify(result: Any) -> str:
    return _render("verify", result)


def _r_audit(result: Any) -> str:
    return _render("audit", result)


def _r_assess(result: Any) -> str:
    return _render("assess", result)


def _r_rebuild(result: Any) -> str:
    return _render("rebuild", result)


def _r_seal(result: Any) -> str:
    return _render("seal", result)


def _r_crosscheck(result: Any) -> str:
    return _render("crosscheck", result)


def _r_record(result: Any) -> str:
    return _render("record", result)


def _r_sign(result: Any) -> str:
    return _render("sign", result)


def _r_export(result: Any) -> str:
    return _render("export", result)


def _r_pack(result: Any) -> str:
    return _render("pack", result)


def _r_attest(result: Any) -> str:
    return _render("attest", result)


def _r_attest_check(result: Any) -> str:
    return _render("attest check", result)


def _r_hooks(result: Any) -> str:
    return _render("hooks", result)


def _r_import(result: Any) -> str:
    return _render("import", result)


def _r_init(result: Any) -> str:
    return _render("init", result)


def _r_pull(result: Any) -> str:
    return _render("pull", result)


def _r_review(result: Any) -> str:
    return _render("review", result)


def _r_sign_check(result: Any) -> str:
    return _render("sign check", result)


def _t_init(result: Any) -> str:
    if isinstance(result, dict):
        return "init: " + str(result.get("status", result.get("path", "ready")))
    return "init: " + str(result)
