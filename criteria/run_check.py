"""Kernel-run conformance gate — confined gate execution and the cost ledger.

`run_gate` runs a claim's gate under a platform sandbox, timed and with a
scrubbed environment, and reports its status and which sandbox applied. The
ledger records what a run cost and `cost` totals it. Writes RUN_OK.

    python3 criteria/run_check.py        (from the repository root)
"""
import os
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import run

SANDBOXES = {"none", "seatbelt", "bubblewrap", "inherited"}




# ==== seam block for run_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- _kernel/run.py: 25 seam names (1 value, 1 kind, 23 callable) ---
_SEAM__kernel_run_VALUES = {
    '_REQ_OPS': ('<=', '>=', '==', '!=', '~=', '<', '>'),
}
_SEAM__kernel_run_KINDS = {'_BWRAP_OK': 'NoneType'}
_SEAM__kernel_run_CALLABLES = ('_bwrap_usable', '_env_cache_dir', '_have', '_in_band', '_independence_line', '_kill_tree', '_ledger_path', '_quote_sb', '_run', '_sandbox_argv', '_scrub_env', '_tool_version', '_version_ok', '_version_tuple', 'cost', 'furnish', 'gate_timeout', 'independence', 'ledger', 'preflight', 'run_gate', 'sandbox', 'sandbox_backend')

def _seam() -> None:
    from reticuli._kernel import run as _m__kernel_run
    for _n, _v in _SEAM__kernel_run_VALUES.items():
        assert getattr(_m__kernel_run, _n) == _v, f'_kernel/run.py seam {_n} changed'
    for _n in _SEAM__kernel_run_KINDS:
        assert hasattr(_m__kernel_run, _n), f'_kernel/run.py must export {_n}'
    for _n in _SEAM__kernel_run_CALLABLES:
        assert callable(getattr(_m__kernel_run, _n, None)), f'_kernel/run.py must export callable {_n}'


def battery() -> None:
    _seam()
    assert run.sandbox_backend() in SANDBOXES, \
        "a sandbox backend is named (or inherited, when already jailed)"
    d = tempfile.mkdtemp()
    try:
        out = run.run_gate("printf v > V", d, None)
        assert out["status"] == "ok", f"a passing gate is ok: {out}"
        assert out["quarantine"] in SANDBOXES, f"the sandbox is recorded: {out}"
        assert os.path.isfile(os.path.join(d, "V")), "the gate's output is present"

        out = run.run_gate("exit 3", d, None)
        assert out["status"] == "failed", f"a failing gate is failed: {out}"

        run.ledger(d, {"kind": "producer", "calls": 1, "tokens": 10})
        assert any(e.get("kind") == "producer" for e in run.ledger_events(d)), \
            "the ledger records what a run cost"
        c = run.cost(d)
        assert c.get("calls") == 1 and c.get("tokens") == 10, \
            f"cost totals the ledger: {c}"

        # THE DECLARED TIMEOUT IS THE CEILING, IN BOTH DIRECTIONS
        # (2026-10-04, the final bundle; witnessed 2026-09-29 when a
        # conforming regrown kernel combined the declaration with a
        # sixty-second default by min(), leaving it structurally unable
        # to audit the repository that declares its own window). A claim
        # that declares gate_timeout gets exactly that ceiling: the
        # declaration may raise it past any implementation default, and
        # a gate past the declared ceiling still times out.
        saved_cap = os.environ.pop("RETICULI_GATE_TIMEOUT", None)
        try:
            assert run.gate_timeout({"claim": {"gate_timeout": 1800}}) == 1800, \
                "a declared gate_timeout IS the ceiling, not a suggestion " \
                "an implementation default may undercut"
            slow = {"claim": {"name": "slow", "gate_timeout": 30},
                    "step": [{"kind": "gate", "output": "OK",
                              "run": "sleep 1.5 && printf ok > OK",
                              "class": "validated"}]}
            out = run.run_gate("sleep 1.5 && printf ok > OK", d, slow)
            assert out["status"] == "ok", \
                f"a gate inside its declared window passes: {out['status']}"
            out = run.run_gate("sleep 1.5 && printf ok > OK", d,
                               {"claim": {"gate_timeout": 0.2}})
            assert out["status"] == "timeout", \
                "and the declaration still bounds: past it is a timeout"
        finally:
            if saved_cap is not None:
                os.environ["RETICULI_GATE_TIMEOUT"] = saved_cap
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("RUN_OK", "w", encoding="utf-8") as f:
            f.write("run-ok\n")
    print("run-ok")
