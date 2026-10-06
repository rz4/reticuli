"""Human-readable summaries of CLI command results.

The command handlers own the result dictionaries.  These functions only turn
those results into text, so JSON output can keep the original data intact.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _row(label, value):
    """Format one labelled fact."""
    return f"{label}: {value}"


def _when(value):
    """Show a recorded timestamp without changing its meaning."""
    if not value:
        return "unknown"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _generic_contract(command, data=None):
    """Render the common status and identity fields of a command result."""
    if data is None:
        data = command
        command = "result"
    if not isinstance(data, dict):
        return f"{command}: {data}"
    lines = [f"{command}: {data.get('status', 'ok' if data.get('ok', True) else 'failed')}"]
    for key in ("name", "root", "phase", "verdict", "detail"):
        if data.get(key) is not None:
            lines.append(_row(key, data[key]))
    return "\n".join(lines)


def _render(command, data):
    return _generic_contract(command, data)


def _r_verify(data): return _render("verify", data)
def _r_audit(data): return _render("audit", data)
def _r_assess(data): return _render("assess", data)
def _r_rebuild(data): return _render("rebuild", data)
def _r_seal(data): return _render("seal", data)
def _r_crosscheck(data): return _render("crosscheck", data)
def _r_record(data): return _render("record", data)
def _r_sign(data): return _render("sign", data)
def _r_export(data): return _render("export", data)
def _r_pack(data): return _render("pack", data)
def _r_attest(data): return _render("attest", data)
def _r_attest_check(data): return _render("attest-check", data)
def _r_hooks(data): return _render("hooks", data)
def _r_import(data): return _render("import", data)
def _r_init(data): return _render("init", data)
def _r_pull(data): return _render("pull", data)
def _r_review(data): return _render("review", data)
def _r_sign_check(data): return _render("sign-check", data)


def _t_init(data):
    return _r_init(data)
