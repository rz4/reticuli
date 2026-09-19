"""On-ramp legibility: the first commands a newcomer runs teach, and the
guidance leads somewhere that works.

  - bare `ret` prints the command map and exits 0, not an argparse error;
  - `ret init --agent generic` prints the wiring contract on its DEFAULT output,
    not only under -v — a contract the caller cannot see cannot be followed;
  - the hook is wired to an absolute, PATH-independent command, never bare `ret`
    (which no-ops when a venv is not active as the harness fires);
  - the "prove it" next-step names --record-proof, so following it advances the
    claim instead of repeating the same rung.

    pytest tests/test_onramp.py
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import cli, hooks


def _ret(*argv: str, cwd: str | None = None):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    return subprocess.run([sys.executable, "-m", "reticuli", *argv], check=False,
                          cwd=cwd or ROOT, env=env, capture_output=True, text=True)


def test_bare_ret_prints_the_command_map() -> None:
    r = _ret()
    assert r.returncode == 0, "bare ret is not an error, it is an invitation"
    assert "init" in r.stdout and "verify" in r.stdout, \
        "and it lists the verbs, the way `git` does"


def test_generic_contract_is_on_the_default_init_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = _ret("init", "--agent", "generic", cwd=tmp)
        assert r.returncode == 0
        out = r.stdout
        assert "hook" in out and '"event"' in out, \
            "the JSON-event contract prints without needing -v"
        assert "write" in out and "prompt" in out, "the event kinds are named"


def test_hook_command_is_absolute_never_bare_ret() -> None:
    cmd = hooks._hook_command()
    assert cmd != "ret hook", "a bare wiring no-ops when the venv is not active"
    assert os.path.isabs(cmd.split()[0].strip("'\"")), \
        "the command names an absolute interpreter, resolvable at fire time"
    assert hooks._is_reticuli_hook(cmd), "and it is still recognized as ours"


def test_prove_it_next_step_records_the_proof() -> None:
    view = {"ok": True, "audited": {"when": "x"}, "deciding": {"when": "x"},
            "proof": None, "signatures": 0}
    step = cli._next_step(view)
    assert "crosscheck" in step and "--record-proof" in step, \
        "following the suggestion must advance the claim, not repeat the rung"


def _seal_a_claim(proj: str) -> None:
    with open(os.path.join(proj, "impl.py"), "w") as f:
        f.write("def f():\n    return 1\n")
    with open(os.path.join(proj, "check.py"), "w") as f:
        f.write("import impl\nassert impl.f() == 1\n")
    r = _ret("pack", proj, "--generated", "impl.py", "--input", "check.py",
             "--gate", f"{sys.executable} check.py && printf ok > OK",
             "--output", "OK", cwd=proj)
    assert r.returncode == 0, f"the claim seals: {r.stderr}"


def test_success_confirmation_is_tty_only() -> None:
    import pty
    with tempfile.TemporaryDirectory() as proj:
        _seal_a_claim(proj)
        # piped (stderr not a tty): the silence rule holds — nothing, exit 0
        r = _ret("verify", proj)
        assert r.returncode == 0 and r.stdout == "" and r.stderr == "", \
            "piped, a passing verify prints nothing on either stream"
        # under a pty, stderr carries the one-line confirmation. pty.spawn
        # inherits os.environ, so the child finds reticuli via PYTHONPATH.
        out: list[bytes] = []

        def _read(fd: int) -> bytes:
            data = os.read(fd, 1024)
            out.append(data)
            return data

        saved = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = os.path.join(ROOT, "src")
        try:
            status = pty.spawn(
                [sys.executable, "-m", "reticuli", "verify", proj], _read)
        finally:
            if saved is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = saved
        assert os.waitstatus_to_exitcode(status) == 0
        text = b"".join(out).decode(errors="replace")
        assert "fresh" in text, \
            "in a terminal, a passing verify confirms itself on stderr"


if __name__ == "__main__":
    test_bare_ret_prints_the_command_map()
    test_generic_contract_is_on_the_default_init_output()
    test_hook_command_is_absolute_never_bare_ret()
    test_prove_it_next_step_records_the_proof()
    test_success_confirmation_is_tty_only()
    print("onramp-ok")
