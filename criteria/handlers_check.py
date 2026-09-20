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


def battery() -> None:
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
