"""The subject of the experiment: a model writing code and its own tests.

One call per task, given the specification and nothing else, asked for an
implementation and a test suite together. That pairing is the whole point --
the study is about what happens when the same process produces the artifact
and its oracle, so the two must come from one reply and not from two
independent ones.

Repair turns are allowed, because an agent that runs its tests and fixes what
they catch is the realistic case and the interesting one: it guarantees the
suite passes at the end, which is precisely the situation where a green result
carries no information. How many turns each task needed is recorded -- a model
that never had to repair anything and one that iterated four times have
produced differently-fitted suites.

Two backends, neither of which needs an API key in the environment:

    claude      the `claude` CLI, on the operator's own subscription auth
    openai      the OpenAI SDK, honouring OPENAI_BASE_URL for a gateway

Both report tokens and, where the backend knows it, dollars: an experiment
that spends money should say how much.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

#: A reply must carry both files. Anything else is a failed authoring turn and
#: is recorded as one rather than being patched up by the harness.
FILES = ("impl.py", "check.py")

_FENCE = re.compile(
    r"^###\s+(?P<name>[A-Za-z0-9_.\-/]+)\s*$\s*```[a-zA-Z0-9_+-]*\n(?P<body>.*?)^```",
    re.MULTILINE | re.DOTALL)

REPAIR = """\
Your test suite does not pass against your implementation.

```
{detail}
```

Reply with both files again, corrected, in the same format.
"""


class AuthorError(RuntimeError):
    """The model did not produce a usable pair of files."""


def split(reply: str) -> dict:
    """The two files out of one reply, by the filename heading above each."""
    found = {m.group("name").strip(): m.group("body")
             for m in _FENCE.finditer(reply)}
    missing = [f for f in FILES if f not in found]
    if missing:
        raise AuthorError(f"the reply named no {', '.join(missing)} "
                          f"(found: {sorted(found) or 'no fenced files'})")
    return {name: found[name] for name in FILES}


# ------------------------------------------------------------------ backends


def _claude(prompt: str, model: str) -> tuple[str, dict]:
    """The `claude` CLI. ANTHROPIC_API_KEY is stripped so the call runs on the
    operator's subscription auth, which is how every other producer here
    behaves -- and it means a study run competes with their own quota, which
    the README says out loud."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = subprocess.run(["claude", "-p", prompt, "--model", model,
                           "--output-format", "json"], env=env, check=False,
                          capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        raise AuthorError(f"claude exited {proc.returncode}: "
                          f"{(proc.stderr or proc.stdout).strip()[:200]}")
    try:
        envelope = json.loads(proc.stdout)
    except ValueError:
        return proc.stdout, {}
    if envelope.get("is_error") or envelope.get("subtype") == "error":
        raise AuthorError(f"error envelope: {str(envelope.get('result'))[:200]}")
    usage = envelope.get("usage") or {}
    spend = {"tokens": int(usage.get("input_tokens", 0))
             + int(usage.get("output_tokens", 0))}
    if isinstance(envelope.get("total_cost_usd"), int | float):
        spend["usd"] = envelope["total_cost_usd"]
    return envelope.get("result") or "", spend


def _openai(prompt: str, model: str) -> tuple[str, dict]:
    """The OpenAI SDK. Lazily imported, so the claude backend works on a
    machine that has never installed it. Honours OPENAI_BASE_URL: the lab's
    access is through a gateway that plain urllib cannot reach."""
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}])
    usage = getattr(response, "usage", None)
    spend = {"tokens": int(getattr(usage, "total_tokens", 0) or 0)}
    return (response.choices[0].message.content or ""), spend


BACKENDS = {"claude": _claude, "openai": _openai}


# -------------------------------------------------------------------- author


def write(room: str, files: dict) -> None:
    for name, body in files.items():
        with open(os.path.join(room, name), "w", encoding="utf-8") as f:
            f.write(body if body.endswith("\n") else body + "\n")


def run_check(room: str, timeout: float = 60.0) -> tuple[bool, str]:
    """The model's own suite, against the model's own code.

    Bytecode caching is disabled, and that is not a tidiness measure. CPython
    invalidates a .pyc by mtime-and-size, both at one-second resolution: a
    harness that rewrites impl.py several times a second -- which anything
    searching over variants of a file does -- will silently re-import the
    previous version whenever the new one happens to be the same length.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        proc = subprocess.run([sys.executable, "check.py"], cwd=room, check=False,
                              env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"check.py did not finish within {timeout:.0f}s"
    if proc.returncode == 0:
        return True, ""
    # The TAIL of the output: a traceback's opening lines are boilerplate and
    # the line that says what went wrong is the last one.
    detail = (proc.stderr or proc.stdout or "").strip()
    return False, ("…" + detail[-1200:]) if len(detail) > 1200 else detail


def author(room: str, *, backend: str, model: str, repairs: int = 2) -> dict:
    """One task: ask for the pair, let the model repair what its tests catch."""
    call = BACKENDS[backend]
    with open(os.path.join(room, "TASK.md"), encoding="utf-8") as f:
        prompt = f.read()

    spend = {"tokens": 0, "usd": 0.0}
    history: list = []
    for turn in range(repairs + 1):
        reply, cost = call(prompt, model)
        spend["tokens"] += cost.get("tokens", 0)
        spend["usd"] += cost.get("usd", 0.0)
        try:
            files = split(reply)
        except AuthorError as exc:
            history.append({"turn": turn, "outcome": f"unusable reply: {exc}"})
            if turn == repairs:
                return {"ok": False, "turns": turn + 1, "spend": spend,
                        "history": history, "why": str(exc)}
            prompt = REPAIR.format(detail=str(exc))
            continue
        write(room, files)
        passed, detail = run_check(room)
        history.append({"turn": turn, "outcome": "gate passed" if passed
                        else f"gate failed: {detail[:160]}"})
        if passed:
            return {"ok": True, "turns": turn + 1, "spend": spend,
                    "history": history, "why": None}
        if turn < repairs:
            prompt = REPAIR.format(detail=detail)
    return {"ok": False, "turns": repairs + 1, "spend": spend,
            "history": history,
            "why": "the model's own tests never passed against its own code"}
