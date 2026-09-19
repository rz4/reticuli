"""The failure paths honor the CLI contract (docs/cli-style.md).

Two guarantees a script depends on and a person barely notices:

  - `--json` always prints the envelope on stdout, on refusal as on success —
    `ok: false`, stderr empty — so `ret <verb> --json | jq` never chokes on an
    empty stdout for the "is this even a claim?" refusals automation hits first;
  - every error line is `ret: <verb>: <fact>`, the greppable prefix intact even
    on the usage refusals that print by hand.

    pytest tests/test_error_contract.py
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ret(*argv: str, cwd: str | None = None):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    return subprocess.run([sys.executable, "-m", "reticuli", *argv], check=False,
                          cwd=cwd or ROOT, env=env, capture_output=True, text=True)


def test_json_refusal_is_the_envelope_on_stdout() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for verb in ("verify", "audit", "status", "assess"):
            r = _ret(verb, os.path.join(tmp, "nope"), "--json")
            assert r.returncode == 1, f"{verb}: a refusal exits 1"
            assert r.stderr == "", \
                f"{verb}: --json keeps stderr empty, the report is on stdout"
            env = json.loads(r.stdout)              # the assertion IS the parse
            assert env["ok"] is False and env["command"] == verb
            assert env["status"] == "error" and env["root"] is None
            assert env["data"].get("error"), "the fact rides under data.error"


def test_json_refusal_on_damaged_recipe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "reticuli.toml"), "w") as f:
            f.write("not = [valid\n")
        r = _ret("verify", tmp, "--json")
        assert r.returncode == 1 and r.stderr == ""
        env = json.loads(r.stdout)
        assert env["ok"] is False and "damaged" in env["data"]["error"]


def test_error_lines_keep_the_verb_colon_prefix() -> None:
    r = _ret("run", "")
    assert r.returncode == 2 and r.stderr.startswith("ret: run: "), r.stderr
    r = _ret("crosscheck", "only-one")
    assert r.returncode == 2 and r.stderr.startswith("ret: crosscheck: "), r.stderr


def test_flag_pack_refuses_dash_o_instead_of_ignoring_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "impl.py"), "w") as f:
            f.write("def f():\n    return 1\n")
        with open(os.path.join(tmp, "check.py"), "w") as f:
            f.write("import impl\nassert impl.f() == 1\n")
        r = _ret("pack", tmp, "--generated", "impl.py", "--input", "check.py",
                 "--gate", f"{sys.executable} check.py && printf ok > OK",
                 "--output", "OK", "-o", os.path.join(tmp, "elsewhere.claim"))
        assert r.returncode == 2, "a flag-declared pack with -o is a usage error"
        assert r.stderr.startswith("ret: pack: ") and "-o" in r.stderr
        assert not os.path.exists(os.path.join(tmp, "elsewhere.claim")), \
            "and it wrote nothing, rather than sealing somewhere unasked"


if __name__ == "__main__":
    test_json_refusal_is_the_envelope_on_stdout()
    test_json_refusal_on_damaged_recipe()
    test_error_lines_keep_the_verb_colon_prefix()
    test_flag_pack_refuses_dash_o_instead_of_ignoring_it()
    print("error-contract-ok")
