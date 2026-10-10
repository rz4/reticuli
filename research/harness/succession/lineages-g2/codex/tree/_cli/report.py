"""Human readable summaries for action commands.

The command layer owns exit codes and JSON envelopes.  These functions only
turn the result dictionaries returned by the lower layers into display text.
"""

from __future__ import annotations

import datetime as _datetime
import json
from collections.abc import Mapping

from .. import render


def _value(value):
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _row(label, value=None):
    """Format a labeled fact; a mapping may supply both fields."""
    if value is None and isinstance(label, Mapping):
        return "  ".join(f"{key}: {_value(item)}" for key, item in label.items())
    return f"{label}: {_value(value)}"


def _when(value):
    """Describe a UTC timestamp without requiring a particular host locale."""
    if value is None or value == "":
        return "unknown"
    try:
        if isinstance(value, (int, float)):
            instant = _datetime.datetime.fromtimestamp(value, _datetime.timezone.utc)
        else:
            instant = _datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return instant.astimezone(_datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _generic_contract(verb, result=None, *, fields=()):
    """Render a verb's outcome and its useful, present result fields."""
    if result is None and isinstance(verb, Mapping):
        result, verb = verb, "result"
    if not isinstance(result, Mapping):
        return f"{verb}: {_value(result)}"
    state = result.get("verdict", result.get("status"))
    if state is None:
        state = "ok" if result.get("ok", result.get("satisfied", True)) else "failed"
    lines = [f"{verb}: {state}"]
    selected = fields or tuple(key for key in result if key not in ("ok", "status", "verdict"))
    for key in selected:
        if key in result:
            lines.append(_row(key.replace("_", " "), result[key]))
    return "\n".join(lines)


def _r_verify(result):
    return _generic_contract("verify", result, fields=("name", "root", "recomputed"))


def _r_audit(result):
    return _generic_contract("audit", result, fields=("root", "gates", "layers", "environment"))


def _r_assess(result):
    return _generic_contract("assess", result, fields=("measured", "not_measured", "not_applicable"))


def _r_rebuild(result):
    return _generic_contract("rebuild", result, fields=("root", "build_digest", "gates", "quarantine", "rebuilt_components"))


def _r_seal(result):
    return _generic_contract("seal", result, fields=("name", "root"))


def _r_crosscheck(result):
    return _generic_contract("crosscheck", result, fields=("roots", "audited", "rejected", "incomplete", "cost", "mutation_score", "independence"))


def _r_record(result):
    return _generic_contract("record", result, fields=("name", "root", "build_digest", "gates", "when"))


def _r_sign(result):
    return _generic_contract("sign", result, fields=("statement", "signature", "sign_root"))


def _r_export(result):
    return _generic_contract("export", result, fields=("path", "root"))


def _r_pack(result):
    return _generic_contract("pack", result, fields=("path", "root"))


def _r_attest(result):
    return _generic_contract("attest", result, fields=("principal", "root", "build_digest", "statement", "signature"))


def _r_attest_check(result):
    return _generic_contract("attest check", result, fields=("attestations",))


def _r_hooks(result):
    return _generic_contract("hooks", result, fields=("wired",))


def _r_import(result):
    return _generic_contract("import", result, fields=("path", "root"))


def _r_init(result):
    return _generic_contract("init", result, fields=("path", "name", "root"))


def _r_pull(result):
    return _generic_contract("pull", result, fields=("path", "root", "materialized"))


def _r_review(result):
    return _generic_contract("review", result, fields=("root", "build_digest", "sign_root", "audit", "proof"))


def _r_sign_check(result):
    return _generic_contract("sign check", result, fields=("authorizations",))


def _t_init(result):
    """One line for a newly initialized draft or workspace."""
    if isinstance(result, Mapping):
        return "init " + _value(result.get("path", result.get("name", ".")))
    return "init " + _value(result)
