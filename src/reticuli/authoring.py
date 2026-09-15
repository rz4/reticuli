"""Authoring: propose a claim from a session's trace, then certify it cold.

The trace has zero authority. Authoring proposes a recipe from what the session
did, rebuilds it in a clean workspace, re-runs the gates cold, and seals only if
the pinned verdicts reproduce. A wrong proposal simply fails to certify; no claim
forms.
"""
from __future__ import annotations

import json
import os
import re
import shutil

from . import _util, kernel, render

TRACE = os.path.join(kernel.STORE, "draft.jsonl")

# A read/inspect tool consumes its arguments; it never *produces* them. So a gate
# is a command that WRITES its output (a redirect target, or a non-read-only
# program) — never `ls VERIFIED` merely naming it.
_READ_ONLY = frozenset({"ls", "cat", "rm", "head", "tail", "grep", "wc", "stat",
                        "echo", "printf", "find", "diff", "cmp", "file"})
_REDIRECT = re.compile(r'\d*>>?\s*["\']?([^\s"\';|&<>()]+)')


def _writes(cmd: str, out: str) -> bool:
    base = os.path.basename(out)
    if any(os.path.basename(m.group(1)) == base for m in _REDIRECT.finditer(cmd)):
        return True
    prog = next((os.path.basename(t) for t in cmd.split() if "=" not in t or not t.split("=")[0].isidentifier()), "")
    return base in cmd and prog not in _READ_ONLY


def _names_a_file(session: str, rel: str) -> bool:
    """Does `rel` name a real file in the session, matching case EXACTLY?

    `os.path.isfile` is case-insensitive on macOS and Windows, so the shell
    token `ok` in `printf ok > OK` tests true against the file `OK`. Declaring
    that token as a pinned input would make the SAME session seal to different
    roots on different filesystems, and the claim would name an input a
    case-sensitive host cannot find at all. Identity must not depend on the
    host's filesystem, so each path component is matched against its
    directory's real entries.
    """
    if not rel or os.path.isabs(rel):
        return False
    current = session
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            return False
        try:
            if part not in os.listdir(current):
                return False
        except OSError:
            return False
        current = os.path.join(current, part)
    return os.path.isfile(current)


def _events(session: str) -> list[dict]:
    path = os.path.join(session, TRACE)
    out: list[dict] = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return out


def _confined(root: str, name: str) -> str:
    """`_util.safe_path` speaking the kernel's refusal. A trace-derived path is
    untrusted input, so an escape is a refusal with a reason — never a raw
    ValueError surfacing from a helper."""
    try:
        return _util.safe_path(root, name)
    except ValueError as exc:
        raise kernel.ClaimError(str(exc)) from None


def _hash_path(path: str) -> str:
    """sha256 of a file's bytes. The kernel's own file hash is private to it, so
    the layers hash through `_util` (spec/identity.md is the authority for both)."""
    with open(path, "rb") as f:
        return _util.hash_bytes(f.read())


def _detect_components(session: str, inputs: list[str]) -> list:
    """Which sealed sub-claims these pinned inputs came from — the exchange
    layer's registry answers that. Exchange is not ported yet; until it is, a
    claim simply declares no components."""
    try:
        from . import registry
    except ImportError:
        return []
    return registry.detect_components(session, inputs)


def propose(session: str, accepted: list[str], name: str,
            claim: list[str] | None = None,
            generated: list[str] | None = None) -> dict:
    """Propose a recipe in trace order: produce steps for model-written files
    (generated), a gate for each accepted output some command writes, the read
    files as pinned inputs. Order matters — a gate's inputs are produced before
    it runs.

    The trace suggests a class; it never decides one. `claim` forces files into
    the pinned inputs (the check IS the claim, whoever typed it) and `generated`
    forces files into produce steps (an implementation is generated even when no
    hook saw it written). Provenance never decides class — declaration does."""
    claim = [os.path.normpath(c) for c in (claim or [])]
    generated = [os.path.normpath(f) for f in (generated or [])]
    ev = _events(session)
    prompts = [e["text"] for e in ev if e.get("event") == "prompt" and e.get("text")]

    write_at: dict[str, int] = {}
    for i, e in enumerate(ev):
        if e.get("event") == "write" and e.get("path"):
            write_at.setdefault(e["path"], i)
    for c in claim:                     # a claimed file is never a produce step
        write_at.pop(c, None)
    for f in generated:                 # a generated file is a produce step, hook or no hook
        if f not in write_at and _names_a_file(session, f):
            write_at[f] = -1
    gate_at: dict[str, tuple[int, str]] = {}
    for i, e in enumerate(ev):
        if e.get("event") == "bash" and e.get("cmd"):
            for out in accepted:
                if out not in gate_at and _writes(e["cmd"], out):
                    gate_at[out] = (i, e["cmd"])

    ordered: list[tuple[int, dict]] = []
    for path, i in write_at.items():
        if path not in gate_at:
            ordered.append((i, {"kind": "produce", "output": path,
                                "request": prompts[-1] if prompts else "produced interactively",
                                "class": "generated"}))
    for out, (i, cmd) in gate_at.items():
        ordered.append((i, {"kind": "gate", "output": out, "run": cmd, "class": "validated"}))
    steps = [s for _, s in sorted(ordered, key=lambda x: x[0])]

    produced = [s["output"] for s in steps if s["kind"] == "produce"]
    gates = [s["run"] for s in steps if s["kind"] == "gate"]
    for a in accepted:
        if a in produced and not any(a in g for g in gates):
            raise kernel.ClaimError(
                f"'{a}' is declared as an input to no gate (no check, no claim)")

    bashes = [e["cmd"] for e in ev if e.get("event") == "bash" and e.get("cmd")]
    reads = [e["path"] for e in ev if e.get("event") == "read" and e.get("path")]
    named = {t.strip(";,()|&<>'\"") for c in bashes for t in c.replace('"', " ").replace("'", " ").split()}
    inputs = [f for f in dict.fromkeys(claim + reads + sorted(named))
              if f and f not in write_at and f not in accepted
              and _names_a_file(session, f)]
    recipe = {"claim": {"name": name, "inputs": inputs}, "step": steps}
    vacuous = kernel.vacuous_gates(recipe)
    if vacuous:
        raise kernel.ClaimError(
            f"vacuous gate for {', '.join(vacuous)}: every script it executes is generated, so "
            "the verdict would depend on no claim and the root would fit any implementation "
            "that prints ok. Name the check: `--claim <check.py>`.")
    return recipe


def build_claim(session: str, accepted: list[str], into: str, name: str | None = None,
                claim: list[str] | None = None, generated: list[str] | None = None,
                mutation_floor: float | None = None,
                requires: list[str] | None = None) -> dict:
    name = name or os.path.basename(os.path.abspath(session).rstrip(os.sep)) or "claim"
    recipe = propose(session, accepted, name, claim, generated)
    if mutation_floor is not None:
        recipe["claim"]["mutation_floor"] = float(mutation_floor)
    if requires:
        recipe["claim"]["requires"] = list(requires)
    warm = {a: _hash_path(os.path.join(session, a)) for a in accepted
            if _names_a_file(session, a)}

    build = into + ".building"
    if os.path.exists(build):
        shutil.rmtree(build)
    os.makedirs(build)
    with open(os.path.join(build, kernel.RECIPE), "w", encoding="utf-8") as f:
        f.write(render.dump_recipe(recipe))
    # confinement BEFORE the copy: a trace-derived input/output path is untrusted
    # (a traced read of ../secret would otherwise be copied out of the workspace on
    # the way to the seal that refuses it), so every path crosses the confinement
    # boundary first — the same boundary rebuild and audit use.
    for inp in _util.declared_inputs(recipe):
        _util.copy_into(_confined(session, inp), _confined(build, inp))
    for step in recipe["step"]:
        if step["kind"] == "produce":
            _util.copy_into(_confined(session, step["output"]),
                            _confined(build, step["output"]))

    for step in recipe["step"]:
        if step["kind"] == "gate":
            r = kernel.run_gate(step["run"], build, recipe)   # scrubbed + bounded, via the one entry point
            if r["returncode"] != 0:
                shutil.rmtree(build)
                raise kernel.ClaimError(
                    f"cold gate failed: {(r['stderr'] or r['stdout']).strip()[:150]}")

    for a, warm_h in warm.items():
        cold = os.path.join(build, a)
        cls = next((s.get("class", "pinned") for s in recipe["step"] if s["output"] == a), "generated")
        if cls != "generated" and os.path.isfile(cold) and _hash_path(cold) != warm_h:
            shutil.rmtree(build)
            raise kernel.ClaimError(f"cold result does not match accepted (nondeterministic '{a}')")

    # the session's cost, as the trace shows it: one oracle call per prompt,
    # the trace's wall-clock span — the claim's C1, kept as local residue
    ev = _events(session)
    prompts = sum(1 for e in ev if e.get("event") == "prompt")
    ts = [e["ts"] for e in ev if isinstance(e.get("ts"), (int, float))]
    if prompts:
        for _ in range(prompts):
            _util.ledger_add(build, {"event": "oracle", "calls": 1})
        if len(ts) >= 2:
            _util.ledger_add(build, {"event": "trace", "seconds": round(max(ts) - min(ts), 3)})

    links = _detect_components(session, _util.declared_inputs(recipe))
    manifest = kernel.seal(build)
    if links:
        # v2's `seal` takes no components argument, so the links are written onto
        # the sealed manifest here — residue beside the identity, never inside it
        # (spec/claim-format.md: manifest = {name, root} plus optional components).
        manifest["components"] = links
        _util.write_json(os.path.join(build, kernel.MANIFEST), manifest)
    if os.path.exists(into):
        shutil.rmtree(into)
    os.rename(build, into)
    return {"ok": True, "name": name, "root": manifest["root"], "into": into,
            "steps": recipe["step"], "inputs": _util.declared_inputs(recipe),
            "components": links}
