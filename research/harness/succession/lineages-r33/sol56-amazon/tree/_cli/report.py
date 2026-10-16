"""Human renderers for action-oriented command results.

The command implementations return ordinary dictionaries.  This module keeps
all presentation of those dictionaries in one place: renderers are pure (they
return text and do not write to a stream), tolerate partial diagnostic results,
and use a stable ordering for otherwise unordered mappings.
"""
from __future__ import annotations

import datetime as _datetime
import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

from reticuli.render import duration, short


def _text(value: Any) -> str:
    """Give a compact, deterministic human spelling to a result value."""
    if value is None:
        return "-"
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(item) for item in value) if value else "-"
    return str(value)


def _row(label: Any, value: Any = None, *, indent: int = 0,
         width: int = 0) -> str:
    """Render one labelled report row.

    ``width`` can be supplied by callers rendering several rows; when omitted
    no incidental padding is introduced.  Multi-line values remain readable
    by aligning continuation lines below the value.
    """
    name = str(label)
    left = name.ljust(max(len(name), int(width)))
    prefix = " " * max(0, int(indent)) + left + ": "
    value_text = _text(value)
    lines = value_text.splitlines() or [""]
    continuation = " " * len(prefix)
    return "\n".join([prefix + lines[0]] +
                     [continuation + line for line in lines[1:]])


def _when(value: Any, now: Any = None) -> str:
    """Render a record timestamp relative to *now*.

    Unparseable values are returned verbatim, which is preferable for a
    diagnostic renderer to hiding the source value.  ``now`` is accepted as a
    datetime or an epoch number to make tests and embedding deterministic.
    """
    if isinstance(value, Mapping):
        value = value.get("when") or value.get("earned") or value.get("earned_at")
    if value is None:
        return "-"
    try:
        if isinstance(value, str):
            point = _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif isinstance(value, _datetime.datetime):
            point = value
        else:
            point = _datetime.datetime.fromtimestamp(float(value), _datetime.timezone.utc)
        if point.tzinfo is None:
            point = point.replace(tzinfo=_datetime.timezone.utc)
        if now is None:
            current = _datetime.datetime.now(_datetime.timezone.utc)
        elif isinstance(now, _datetime.datetime):
            current = now if now.tzinfo else now.replace(tzinfo=_datetime.timezone.utc)
        else:
            current = _datetime.datetime.fromtimestamp(float(now), _datetime.timezone.utc)
        seconds = (current - point).total_seconds()
        if seconds < 0:
            return "in " + duration(-seconds)
        return duration(seconds) + " ago"
    except (TypeError, ValueError, OverflowError, OSError):
        return str(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _lines(*rows: str) -> str:
    return "\n".join(row for row in rows if row)


def _root_line(value: Mapping[str, Any]) -> str:
    root = value.get("root")
    return _row("root", root) if root is not None else ""


def _status(value: Mapping[str, Any], default: str = "ok") -> str:
    explicit = value.get("verdict", value.get("status"))
    if explicit is not None:
        return str(explicit)
    if "ok" in value:
        return default if value.get("ok") else "failed"
    return default


def _details(value: Mapping[str, Any], omitted: set[str]) -> list[str]:
    return [_row(key.replace("_", " "), value[key])
            for key in sorted(value) if key not in omitted]


def _generic_contract(command: str, result: Any, *, verbose: bool = False,
                      fields: Sequence[str] = ()) -> str:
    """Render the common result contract used by simple action verbs."""
    value = _mapping(result)
    heading = f"{command}: {_status(value)}"
    rows = [heading]
    used = {"ok", "status", "verdict"}
    for field in fields:
        if field in value:
            rows.append(_row(field.replace("_", " "), value[field]))
            used.add(field)
    if "root" in value and "root" not in used:
        rows.append(_row("root", value["root"]))
        used.add("root")
    if verbose:
        rows.extend(_details(value, used))
    return _lines(*rows)


def _r_verify(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    state = "holds" if value.get("ok") else "mismatch"
    rows = [f"verify: {state}", _root_line(value)]
    if not value.get("ok") and value.get("recomputed") is not None:
        rows.append(_row("recomputed", value["recomputed"]))
    if value.get("changed"):
        rows.append(_row("changed", value["changed"]))
    if verbose:
        rows.extend(_details(value, {"ok", "root", "recomputed", "changed"}))
    return _lines(*rows)


def _r_audit(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    rows = [f"audit: {_status(value, 'earned')}", _root_line(value)]
    gates = value.get("gates")
    if isinstance(gates, Sequence) and not isinstance(gates, (str, bytes)):
        for gate in gates:
            if isinstance(gate, Mapping):
                name = gate.get("output", gate.get("gate", "gate"))
                status = gate.get("status", "unknown")
                quarantine = gate.get("quarantine", gate.get("sandbox"))
                suffix = f" ({quarantine})" if quarantine else ""
                rows.append(_row(name, str(status) + suffix, indent=2))
                if verbose:
                    for key in ("missing", "stderr", "stdout"):
                        if gate.get(key):
                            rows.append(_row(key, gate[key], indent=4))
    if value.get("layers"):
        rows.append(_row("layers", len(value["layers"])))
    if value.get("detail"):
        rows.append(_row("detail", value["detail"]))
    return _lines(*rows)


def _r_assess(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    rows = ["assess: " + ("measured" if value.get("ok") else "incomplete")]
    labels = (("measured", "measured"), ("not_measured", "not measured"),
              ("not_applicable", "not applicable"))
    for key, label in labels:
        section = value.get(key)
        if not isinstance(section, Mapping):
            continue
        if not section and verbose:
            rows.append(_row(label, "-"))
        for name in sorted(section):
            rows.append(_row(f"{label} {name}", section[name]))
    return _lines(*rows)


def _r_rebuild(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    rows = [_generic_contract("rebuild", value, fields=("root", "build_digest"))]
    production = value.get("production")
    if isinstance(production, Sequence) and not isinstance(production, (str, bytes)):
        for item in production:
            if not isinstance(item, Mapping):
                continue
            label = item.get("output", "produce")
            word = item.get("status", "unknown")
            if item.get("seconds") is not None:
                word = f"{word} in {duration(item['seconds'])}"
            rows.append(_row(label, word, indent=2))
            if verbose and item.get("stderr"):
                rows.append(_row("stderr", item["stderr"], indent=4))
    gates = value.get("gates")
    if verbose and gates:
        rows.append(_row("gates", gates))
    return _lines(*rows)


def _r_seal(result: Any, verbose: bool = False) -> str:
    return _generic_contract("seal", result, verbose=verbose,
                             fields=("name", "root"))


def _r_crosscheck(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    rows = [f"crosscheck: {_status(value, 'accept')}"]
    roots = value.get("roots")
    if isinstance(roots, Mapping):
        for machine in sorted(roots):
            rows.append(_row(machine, roots[machine]))
    for key in ("equivalence", "reuse", "audited"):
        if key in value:
            rows.append(_row(key, value[key]))
    for key in ("rejected", "incomplete"):
        if value.get(key):
            rows.append(_row(key, value[key]))
    if value.get("independence") is not None:
        rows.append(_row("independence", value["independence"]))
    if verbose:
        rows.extend(_details(value, {"satisfied", "ok", "verdict", "status",
                                     "roots", "equivalence", "reuse", "audited",
                                     "rejected", "incomplete", "independence"}))
    return _lines(*rows)


def _r_record(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    rows = ["record: " + _status(value, "written")]
    for key in ("name", "root", "build_digest", "path", "signature"):
        if key in value:
            rows.append(_row(key.replace("_", " "), value[key]))
    if value.get("when") is not None:
        rows.append(_row("when", value["when"]))
    if verbose:
        rows.extend(_details(value, {"ok", "status", "verdict", "name", "root",
                                     "build_digest", "path", "signature", "when"}))
    return _lines(*rows)


def _r_sign(result: Any, verbose: bool = False) -> str:
    return _generic_contract("sign", result, verbose=verbose,
                             fields=("identity", "root", "sign_root", "signature"))


def _r_sign_check(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    rows = ["sign check: " + ("authorized" if value.get("ok") else "refused")]
    auth = value.get("authorizations", [])
    if isinstance(auth, Sequence) and not isinstance(auth, (str, bytes)):
        for item in auth:
            if isinstance(item, Mapping):
                rows.append(_row(item.get("identity", item.get("signer", "signature")),
                                 item.get("verdict", "authorized" if item.get("ok") else "refused"),
                                 indent=2))
                if verbose and item.get("packet_holds") is not None:
                    rows.append(_row("packet holds", item["packet_holds"], indent=4))
    return _lines(*rows)


def _r_attest(result: Any, verbose: bool = False) -> str:
    return _generic_contract("attest", result, verbose=verbose,
                             fields=("identity", "root", "build_digest", "statement", "signature"))


def _r_attest_check(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    rows = ["attest check: " + ("signed" if value.get("ok") else "refused")]
    attestations = value.get("attestations", [])
    if isinstance(attestations, Sequence) and not isinstance(attestations, (str, bytes)):
        for item in attestations:
            if isinstance(item, Mapping):
                label = item.get("identity", item.get("statement", "attestation"))
                rows.append(_row(label, item.get("verdict", "signed" if item.get("ok") else "refused"), indent=2))
                if verbose and item.get("drifted"):
                    rows.append(_row("drifted", True, indent=4))
    return _lines(*rows)


def _r_export(result: Any, verbose: bool = False) -> str:
    return _generic_contract("export", result, verbose=verbose,
                             fields=("path", "root"))


def _r_import(result: Any, verbose: bool = False) -> str:
    return _generic_contract("import", result, verbose=verbose,
                             fields=("name", "root", "path"))


def _r_pack(result: Any, verbose: bool = False) -> str:
    return _generic_contract("pack", result, verbose=verbose,
                             fields=("name", "root", "build_digest"))


def _r_pull(result: Any, verbose: bool = False) -> str:
    return _generic_contract("pull", result, verbose=verbose,
                             fields=("path", "root", "materialized"))


def _r_hooks(result: Any, verbose: bool = False) -> str:
    return _generic_contract("hooks", result, verbose=verbose,
                             fields=("status", "path", "wired"))


def _r_review(result: Any, verbose: bool = False) -> str:
    return _generic_contract("review", result, verbose=verbose,
                             fields=("root", "build_digest", "sign_root", "proof"))


def _t_init(result: Any) -> str:
    value = _mapping(result)
    path = value.get("path", result if isinstance(result, (str, os.PathLike)) else ".")
    return "init: " + os.fspath(path)


def _r_init(result: Any, verbose: bool = False) -> str:
    value = _mapping(result)
    if not value:
        return _t_init(result)
    return _generic_contract("init", value, verbose=verbose,
                             fields=("path", "name", "status"))


__all__ = [
    "_generic_contract", "_r_assess", "_r_attest", "_r_attest_check",
    "_r_audit", "_r_crosscheck", "_r_export", "_r_hooks", "_r_import",
    "_r_init", "_r_pack", "_r_pull", "_r_rebuild", "_r_record",
    "_r_review", "_r_seal", "_r_sign", "_r_sign_check", "_r_verify",
    "_row", "_t_init", "_when",
]
