"""The probe battery: fingerprint an implementation's unpinned surface.

The subject claim's gate (C_0) pins the happy path only. Generation 0 makes
eight deliberate, undocumented choices on the surface the gate is silent
about — the "intent bits". Each probe below targets one bit; a fingerprint
is the implementation's behavior on all of them, and a bit SURVIVES in a
later generation when its probe outcomes still match generation 0's.

None of these inputs appear in the gate. Nothing here is pinned; the whole
point is to measure what happens where the gate cannot see.

    python3 probes.py --fingerprint path/to/parser.py    # JSON on stdout

The battery runs the implementation in a subprocess (untrusted generated
code; a hang or crash is an outcome, not a harness failure).
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN0 = HERE / "claims" / "L" / "parser.py"

#: (bit, probe name, input text) — each bit may have several probes.
PROBES = [
    ("coercion", "coercion_int", "port = 8080"),
    ("coercion", "coercion_neg", "n = -3"),
    ("duplicates", "duplicates", "k = a\nk = b"),
    ("colon_sep", "colon_sep", "host: example"),
    ("key_case", "key_case", "Path = /tmp"),
    ("bad_line", "bad_line", "plainword\nk = v"),
    ("inline_hash", "inline_hash", "k = v # note"),
    ("continuation", "continuation", "k = one \\\ntwo"),
    ("section", "section", "[db]\nhost = local"),
]

BITS = ["coercion", "duplicates", "colon_sep", "key_case",
        "bad_line", "inline_hash", "continuation", "section"]

#: Generation 0's outcome per probe, pinned literally and re-checked against
#: the actual generation-0 file by --selfcheck.
GEN0_EXPECTED = {
    "coercion_int": {"port": 8080},
    "coercion_neg": {"n": -3},
    "duplicates": {"k": "a"},
    "colon_sep": {"host": "example"},
    "key_case": {"path": "/tmp"},
    "bad_line": {"k": "v"},
    "inline_hash": {"k": "v # note"},
    "continuation": {"k": "one two"},
    "section": {"db.host": "local"},
}


def _canon(value) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return repr(value)


def _run_probes(parser_path: str) -> dict:
    """In-process probe run — called only inside the subprocess."""
    spec = importlib.util.spec_from_file_location("parser", parser_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["parser"] = module
    spec.loader.exec_module(module)
    outcomes = {}
    for _bit, name, text in PROBES:
        try:
            outcomes[name] = {"out": _canon(module.parse(text))}
        except Exception as exc:  # noqa: BLE001 — the outcome IS the data
            outcomes[name] = {"error": type(exc).__name__}
    return outcomes


def fingerprint(parser_path: str, timeout: float = 30.0) -> dict:
    """Probe outcomes for one implementation, via a throwaway subprocess."""
    proc = subprocess.run(
        [sys.executable, str(HERE / "probes.py"), "--fingerprint", parser_path],
        capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        return {"__load__": {"error": (proc.stderr or "load failed")[-300:]}}
    return json.loads(proc.stdout)


def survived(outcomes: dict) -> dict:
    """Per intent bit: True when every probe for that bit matches gen 0."""
    verdict = {}
    for bit in BITS:
        names = [n for b, n, _ in PROBES if b == bit]
        verdict[bit] = all(
            outcomes.get(n, {}).get("out") == _canon(GEN0_EXPECTED[n])
            for n in names)
    return verdict


if __name__ == "__main__":
    if "--fingerprint" in sys.argv:
        path = sys.argv[sys.argv.index("--fingerprint") + 1]
        print(json.dumps(_run_probes(path), sort_keys=True))
    elif "--selfcheck" in sys.argv:
        got = fingerprint(str(GEN0))
        for _bit, name, _text in PROBES:
            want = _canon(GEN0_EXPECTED[name])
            have = got.get(name, {}).get("out")
            assert have == want, f"{name}: gen0 gives {have}, pinned {want}"
        assert all(survived(got).values())
        print("probes-selfcheck-ok")
    else:
        sys.exit(__doc__)
