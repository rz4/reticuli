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
_SEAM__cli_handlers_KINDS = {'_PRODUCERS': 'dict', '_CLI_PRODUCERS': 'dict'}
_SEAM__cli_handlers_CALLABLES = ('_ensure', '_expand_producer', '_scan_workspace', '_version_line', 'init', 'run')

def _seam() -> None:
    from reticuli._cli import handlers as _m__cli_handlers
    for _n, _v in _SEAM__cli_handlers_VALUES.items():
        assert getattr(_m__cli_handlers, _n) == _v, f'_cli/handlers.py seam {_n} changed'
    for _n in _SEAM__cli_handlers_KINDS:
        assert hasattr(_m__cli_handlers, _n), f'_cli/handlers.py must export {_n}'
    for _n in _SEAM__cli_handlers_CALLABLES:
        assert callable(getattr(_m__cli_handlers, _n, None)), f'_cli/handlers.py must export callable {_n}'


def _producer_names() -> None:
    """Both producer tables, exercised through the verb that reads them.

    Every name in either table must expand to its adapter module, and a name
    in neither must pass through verbatim. The bug this pins: `codex` shipped
    as an adapter while only the SDK table existed, so `--producer codex`
    took the verbatim path and ran the bare `codex` binary — which opens an
    interactive UI and dies on the piped prompt. An adapter no name reaches
    is unreachable, and the failure arrived in the tool's voice, not ours.
    """
    import shutil

    # Imported by name, not reached through the module object: this is the
    # surface surface_check.py consumes, and closure_check.py reads imports
    # to decide whether the owning check exercises it.
    from reticuli._cli.handlers import (_CLI_PRODUCERS, _PRODUCERS,
                                        _expand_producer)

    real_which = shutil.which
    shutil.which = lambda binary: f"/usr/bin/{binary}"   # preflight, not launch
    saved = {k: os.environ.get(k) for k in ("RETICULI_MODEL", "RETICULI_VENDOR")}
    try:
        assert _CLI_PRODUCERS and _PRODUCERS, \
            "both producer families must be populated"

        for name in _CLI_PRODUCERS:
            command, env = _expand_producer(name)
            assert f"reticuli.producers.{name}" in command, \
                f"--producer {name} must reach its adapter, not the bare binary"
            assert command.split()[0] != name, \
                f"--producer {name} expanded to the {name} binary itself"
            assert env and env.get("PYTHONPATH"), \
                f"the {name} adapter must import this reticuli"

        for name, key_var in _PRODUCERS.items():
            assert isinstance(key_var, str) and key_var, \
                f"the {name} producer must name the key it forwards"

        verbatim = "python3 my_producer.py --flag"
        command, env = _expand_producer(verbatim)
        assert command == verbatim and env is None, \
            "a producer is any program; the name table must not swallow commands"

        shutil.which = lambda binary: None
        try:
            _expand_producer(next(iter(_CLI_PRODUCERS)))
        except Exception as exc:                     # ClaimError, by contract
            assert "PATH" in str(exc), \
                f"a missing CLI must say so plainly; said {exc}"
        else:
            raise AssertionError(
                "a CLI producer whose binary is absent must refuse up front, "
                "before a room is built or any money moves")
    finally:
        shutil.which = real_which
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def battery() -> None:
    _seam()
    d = tempfile.mkdtemp()
    try:
        ws = os.path.join(d, "ws")
        handlers.init(ws, no_agent=True)
        assert os.path.isdir(os.path.join(ws, ".reticuli")), "init marks a workspace"

        assert handlers.run("exit 7", ws) == 7, "run returns the child's code unchanged"
        assert handlers.run("exit 0", ws) == 0, "and a passing child stays 0"

        _producer_names()

    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("HANDLERS_OK", "w") as f:
            f.write("handlers-ok\n")
    print("handlers-ok")
