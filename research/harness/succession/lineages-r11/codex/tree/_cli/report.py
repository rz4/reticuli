"""Text views of results returned by the command line's action verbs.

The result dictionaries remain the source of truth.  These helpers only turn
them into readable text; JSON output is handled by :mod:`._cli.output`.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _row(label, value):
    """Render one indented field, including false and zero values."""
    return f"  {label}: {value}"


def _when(value):
    """Render a timestamp without changing timestamps already in text form."""
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _generic_contract(verb, result, verbose=False):
    """Provide a stable terse summary and an optional field-by-field view."""
    if not isinstance(result, dict):
        return f"{verb}: {result}"
    status = result.get("verdict", result.get("status"))
    if status is None:
        status = "ok" if result.get("ok", True) else "failed"
    root = result.get("root")
    lines = [f"{verb}: {status}" + (f" {root}" if root else "")]
    if verbose:
        lines.extend(_row(key, value) for key, value in result.items()
                     if key not in ("root", "status", "verdict"))
    return "\n".join(lines)


def _renderer(verb):
    def render(result, verbose=False):
        return _generic_contract(verb, result, verbose)
    render.__name__ = f"_r_{verb.replace('-', '_')}"
    return render


_r_verify = _renderer("verify")
_r_audit = _renderer("audit")
_r_assess = _renderer("assess")
_r_rebuild = _renderer("rebuild")
_r_seal = _renderer("seal")
_r_crosscheck = _renderer("crosscheck")
_r_record = _renderer("record")
_r_sign = _renderer("sign")
_r_export = _renderer("export")
_r_pack = _renderer("pack")
_r_attest = _renderer("attest")
_r_attest_check = _renderer("attest check")
_r_hooks = _renderer("hooks")
_r_import = _renderer("import")
_r_init = _renderer("init")
_r_pull = _renderer("pull")
_r_review = _renderer("review")
_r_sign_check = _renderer("sign check")


def _t_init(result):
    """Terse initialization summary."""
    return _r_init(result)
