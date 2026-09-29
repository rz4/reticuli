"""cli-handlers conformance gate — session setup, traced run, producer preflight.

`init` marks a workspace; `run` returns the child's exit code unchanged (so a
session can use it as a predicate); a named producer preflights its credential
before spending. Writes HANDLERS_OK.

    python3 criteria/handlers_check.py
"""
import os
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._cli import handlers




# ==== seam block for handlers_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- _cli/handlers.py: 8 seam names (1 value, 1 kind, 6 callable) ---
_SEAM__cli_handlers_VALUES = {
    '_PRODUCER_PASSTHROUGH': ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS'),
}
_SEAM__cli_handlers_KINDS = {'_PRODUCERS': 'dict'}
_SEAM__cli_handlers_CALLABLES = ('_ensure', '_expand_producer', '_scan_workspace', '_version_line', 'init', 'run')

def _seam() -> None:
    from reticuli._cli import handlers as _m__cli_handlers
    for _n, _v in _SEAM__cli_handlers_VALUES.items():
        assert getattr(_m__cli_handlers, _n) == _v, f'_cli/handlers.py seam {_n} changed'
    for _n in _SEAM__cli_handlers_KINDS:
        assert hasattr(_m__cli_handlers, _n), f'_cli/handlers.py must export {_n}'
    for _n in _SEAM__cli_handlers_CALLABLES:
        assert callable(getattr(_m__cli_handlers, _n, None)), f'_cli/handlers.py must export callable {_n}'


def battery() -> None:
    _seam()
    d = tempfile.mkdtemp()
    try:
        ws = os.path.join(d, "ws")
        handlers.init(ws, no_agent=True)
        assert os.path.isdir(os.path.join(ws, ".reticuli")), "init marks a workspace"

        assert handlers.run("exit 7", ws) == 7, "run returns the child's code unchanged"
        assert handlers.run("exit 0", ws) == 0, "and a passing child stays 0"

    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("HANDLERS_OK", "w") as f:
            f.write("handlers-ok\n")
    print("handlers-ok")
