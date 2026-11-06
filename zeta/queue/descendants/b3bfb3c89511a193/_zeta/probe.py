"""Drive one population member in a subprocess and record what it did.

A member is a package tree implementing the kernel surface. Members cannot be
imported into one process -- several of them are packages named `tree` -- so
each observation runs a small driver under the member's own import path.

The OUTCOME is what the member did: a value, or an in-band refusal. The
EQUIVALENCE used to class members deliberately ignores refusal message text.
The specification requires a reader to refuse "in band and with a reason";
it does not fix the sentence, so two members refusing the same input with
different wording agree for classing purposes and the wording is reported
separately as a note.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

DRIVER = r'''
import importlib, json, os, sys
request = json.loads(sys.stdin.readline())
tree = os.path.realpath(request["tree"])


def _within(path):
    return bool(path) and os.path.realpath(path).startswith(tree.rstrip(os.sep) + os.sep)


# The member is staged as `reticuli` and this runs under -I -S, so there is no
# ambient reticuli to answer: a reconstruction's `from reticuli._kernel import
# run` resolves to ITS OWN tree, and a relative `from ._kernel import run`
# does too. That is the fix for the import-resolution trap -- loading a member
# under some other name let its absolute imports fall through to the editable
# install, and the probe reported shipped behaviour as the member's
# (research/harness/closure/grade2-the-crown-jewel.md).
sys.path.insert(0, request["stage"])
try:
    module = importlib.import_module("reticuli.kernel")
    if not _within(getattr(module, "__file__", "") or ""):
        print(json.dumps({"kind": "misresolved", "error_type": "WrongImport",
                          "error_message": "reticuli.kernel resolved outside the member tree"}))
        raise SystemExit(0)
except Exception as exc:
    print(json.dumps({"kind": "unavailable", "error_type": type(exc).__name__,
                      "error_message": str(exc)[:400]}))
    raise SystemExit(0)
try:
    function = getattr(module, request["call"])
except AttributeError as exc:
    print(json.dumps({"kind": "absent", "error_type": "AttributeError",
                      "error_message": str(exc)[:400]}))
    raise SystemExit(0)
# CONTAIN THE CODE THAT RUNS, as a second line behind the staging. Even staged
# correctly, this refuses a function whose code object lives outside the tree
# -- belt and suspenders. It cannot catch a one-line facade that DELEGATES to
# foreign code (the delegator's own code is legitimately under the tree), which
# is why the staging above, not this check, is the real fix: with no ambient
# reticuli reachable, there is no foreign code to delegate to.
_f = function
while hasattr(_f, "__wrapped__"):
    _f = _f.__wrapped__
_code = getattr(_f, "__code__", None)
_src = _code.co_filename if _code is not None else None
if _src is not None and not _within(_src):
    print(json.dumps({"kind": "misresolved", "error_type": "ForeignCode",
                      "error_message": f"{request['call']} runs code outside the member tree"}))
    raise SystemExit(0)
try:
    result = function(*request["args"])
except BaseException as exc:
    print(json.dumps({"kind": "refused", "error_type": type(exc).__name__,
                      "error_message": str(exc)[:400]}))
    raise SystemExit(0)
if isinstance(result, bytes):
    shown = {"bytes": result.decode("utf-8", "backslashreplace")}
elif isinstance(result, (str, int, float, bool)) or result is None:
    shown = {"plain": result}
else:
    try:
        shown = {"json": json.loads(json.dumps(result, sort_keys=True, default=repr))}
    except Exception:
        shown = {"repr": repr(result)[:4000]}
print(json.dumps({"kind": "value", "value": shown}, sort_keys=True))
'''

TIMEOUT = 20.0


def observe(member, call, args):
    """Run one call against one member. Never raises on member misbehaviour.

    Two drivers, because two kinds of member exist. A `python-package` member
    is a tree implementing the kernel surface, reached through a driver under
    its own import path. A `process` member is an external program -- another
    implementation of some tool entirely -- reached by running it.

    A python-package member may also name the interpreter to run under. That
    is what makes deployment pressure possible with a single implementation:
    the claim's host contract admits a range of interpreters, so the same
    bytes under each of them are several things the claim equally permits, and
    a behavioural difference between them is the root failing to determine
    behaviour across its own declared contract.
    """
    if member.get("driver") == "process":
        return _observe_process(member, call, args)
    if member.get("driver") == "substitution":
        return _observe_substitution(member, call, args)
    return _observe_package(member, call, args)


def _observe_substitution(member, call, args):
    """Substitute one realization of a dependency under a consumer and re-earn.

    This is the oracle-bearing observation the repair lane is reserved for. A
    `substitution` member is one realization of a dependency claim; the
    pressure names the CONSUMER claim and the output under which the
    dependency's bytes are substituted. The observation re-earns the
    consumer's gate with this realization in place (`audit(produce_from)`, the
    same composition the kernel uses for mutation).

    The one thing this must get right is WHAT COUNTS AS A VERDICT, because the
    whole repair lane turns on it and the failure directions are not
    symmetric. A verdict is recorded -- `satisfies_oracle` set -- only when the
    consumer's gates were actually run against the substituted bytes and
    returned a clean pass or a genuine failure. Everything else is NOT a
    verdict and carries no bit:

      - the substitution did not take (the output names no produce step of the
        consumer): a configuration error, not a member failing the consumer;
      - a gate came back `environment` (the host cannot test) or `mismatch`
        (the consumer's OWN pinned bytes drifted) or `claim_ok` is false (the
        consumer's root no longer recomputes): the consumer could not deliver
        a verdict, so there is nothing to attribute to the realization.

    Collapsing any of those into "the realization broke the consumer" would
    manufacture a repair out of a typo, a missing host tool, or a drifted
    consumer -- the exact trap the probe discipline refuses. `classify` reads
    an absent bit as "not measured", so a not-a-verdict observation is simply
    excluded from the oracle decision.
    """
    if call != "audit_consumer":
        # This driver answers one question. A pressure from any other source
        # pointed at a consumer population is a configuration mistake, not an
        # oracle verdict -- say so, and carry no bit.
        return {"kind": "unavailable", "error_type": "WrongDriver",
                "error_message": f"substitution driver cannot answer {call!r}"}
    consumer, output = (list(args) + [None, None])[:2]
    src = member.get("reticuli_src")
    inserted = bool(src) and src not in sys.path
    if inserted:
        sys.path.insert(0, src)
    try:
        try:
            from reticuli import kernel
        except ImportError as exc:
            return {"kind": "unavailable", "error_type": type(exc).__name__,
                    "error_message": str(exc)[:400]}
        if not isinstance(consumer, str) or not consumer:
            return {"kind": "unavailable", "error_type": "BadConsumer",
                    "error_message": f"consumer path is not a path: {consumer!r}"}
        bytes_path = str(Path(member["path"]).resolve())
        if not Path(bytes_path).is_file():
            return {"kind": "unavailable", "error_type": "FileNotFoundError",
                    "error_message": f"no realization bytes at {bytes_path}"}
        # The output must be a produce step of the consumer, or `produce_from`
        # silently substitutes nothing and the gate passes on the consumer's
        # OWN bytes -- a false "keeps the consumer" for every member.
        try:
            recipe = kernel.load_recipe(consumer)
            outputs = {s.get("output") for s in (recipe.get("step") or [])
                       if s.get("kind") == "produce"}
        except (kernel.ClaimError, OSError) as exc:
            return {"kind": "unavailable", "error_type": type(exc).__name__,
                    "error_message": str(exc)[:400]}
        if output not in outputs:
            return {"kind": "unavailable", "error_type": "NoSuchOutput",
                    "error_message": f"{output!r} is not a produce step of the "
                                     f"consumer; nothing would be substituted"}
        try:
            verdict = kernel.audit(consumer, produce_from={output: bytes_path})
        except kernel.ClaimError as exc:
            # The consumer claim could not be audited at all (unreadable
            # recipe, missing input). Not a verdict about the realization.
            return {"kind": "unavailable", "error_type": type(exc).__name__,
                    "error_message": str(exc)[:400]}
    finally:
        if inserted:
            try:
                sys.path.remove(src)
            except ValueError:
                pass
    statuses = [g.get("status") for g in verdict.get("gates", [])]
    if not verdict.get("claim_ok", True) or not statuses \
            or any(s in ("environment", "mismatch") for s in statuses):
        # The consumer itself could not deliver a clean verdict. Not measured.
        return {"kind": "unavailable", "error_type": "ConsumerUndecided",
                "error_message": f"consumer did not deliver a verdict: "
                                 f"claim_ok={verdict.get('claim_ok')}, "
                                 f"gates={statuses}"}
    # Now, and only now, a real verdict: every gate ran and passed, or at
    # least one genuinely failed on the substituted bytes.
    kept = all(s == "ok" for s in statuses)
    return {"kind": "value",
            "value": {"consumer": "ok" if kept else "breaks"},
            "satisfies_oracle": kept}


def _resolve(name):
    """Find a program here, where the real PATH is, and hand the child an
    absolute path. The child runs with a minimal environment on purpose, so a
    bare name it inherited nothing to resolve would simply not be found -- and
    reporting "no such interpreter" for a program that is installed is a lie
    the instrument would tell about itself.
    """
    if os.sep in str(name):
        return str(name)
    return shutil.which(name)


def _observe_package(member, call, args):
    """Probe a member's kernel, staged so its OWN code answers.

    The member's package directory (`<path>/<package>`) is symlinked in under
    the name `reticuli` and the driver runs `-I -S`: isolated AND without
    site, so the editable install's `.pth` is never processed and no ambient
    `reticuli` can answer a reconstruction's absolute `from reticuli._kernel
    import ...`. Both import styles then resolve to the member's own tree. The
    staging is the fix; the driver's code-containment check is the backstop.
    """
    pkg_dir = (Path(member["path"]) / member["package"]).resolve()
    if not (pkg_dir / "__init__.py").is_file():
        return {"kind": "unavailable", "error_type": "NotAPackage",
                "error_message": f"no package at {pkg_dir}"}
    runner = _resolve(member.get("python") or sys.executable)
    if runner is None:
        return {"kind": "unavailable", "error_type": "FileNotFoundError",
                "error_message": f"no interpreter named {member.get('python')}"}
    stage = tempfile.mkdtemp(prefix="zeta-stage-")
    try:
        try:
            os.symlink(pkg_dir, Path(stage) / "reticuli")
        except OSError as exc:
            return {"kind": "unavailable", "error_type": type(exc).__name__,
                    "error_message": f"cannot stage member: {exc}"}
        # Containment is judged against the member's DECLARED path, not the
        # resolved package dir: a package symlinked in from outside the
        # declared tree has its code `outside`, and that is exactly the escape
        # to refuse (a member declared here whose code secretly lives
        # elsewhere). For an ordinary trial the package sits under its own
        # path, so this is identical; only the symlink-escape differs.
        request = {"call": call, "args": args, "stage": stage,
                   "tree": str(Path(member["path"]).resolve())}
        env = {"PATH": os.defpath, "PYTHONHASHSEED": "0",
               "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1"}
        try:
            done = subprocess.run([runner, "-I", "-S", "-c", DRIVER],
                                  input=json.dumps(request) + "\n", text=True,
                                  capture_output=True, timeout=TIMEOUT, env=env)
        except FileNotFoundError:
            return {"kind": "unavailable", "error_type": "FileNotFoundError",
                    "error_message": f"no interpreter at {runner}"}
        except subprocess.TimeoutExpired:
            return {"kind": "timeout", "error_type": "Timeout",
                    "error_message": f"member exceeded {TIMEOUT:g}s"}
        line = done.stdout.strip().splitlines()
        if not line:
            return {"kind": "crashed", "error_type": "NoOutput",
                    "error_message": (done.stderr or "")[-400:]}
        try:
            return json.loads(line[-1])
        except ValueError:
            return {"kind": "crashed", "error_type": "BadOutput",
                    "error_message": line[-1][:400]}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _observe_process(member, call, args):
    """One external program, one program text, one input document.

    `call` is the subcommand or mode (unused by the jq family, which takes its
    program as an argument); `args` is [program, stdin]. A non-zero exit is an
    in-band refusal: the tool was asked something it would not answer. Only a
    signal or a timeout counts as a crash.
    """
    program, document = (list(args) + ["", ""])[:2]
    binary = _resolve(member["command"])
    if binary is None:
        return {"kind": "unavailable", "error_type": "FileNotFoundError",
                "error_message": f"no program named {member['command']}"}
    command = [binary, *member.get("flags", []), program]
    try:
        done = subprocess.run(command, input=document, text=True,
                              capture_output=True, timeout=TIMEOUT,
                              env={"PATH": os.defpath, "NO_COLOR": "1"})
    except FileNotFoundError:
        return {"kind": "unavailable", "error_type": "FileNotFoundError",
                "error_message": f"no program at {member['command']}"}
    except subprocess.TimeoutExpired:
        return {"kind": "timeout", "error_type": "Timeout",
                "error_message": f"member exceeded {TIMEOUT:g}s"}
    if done.returncode < 0:
        return {"kind": "crashed", "error_type": f"Signal{-done.returncode}",
                "error_message": (done.stderr or "")[-400:]}
    if done.returncode != 0:
        # The exit code is part of the refusal: tools in one family disagree
        # about which code means which failure, and that disagreement is
        # itself a finding rather than noise to normalise away.
        return {"kind": "refused", "error_type": f"Exit{done.returncode}",
                "error_message": (done.stderr or "").strip()[-400:]}
    return {"kind": "value", "value": {"out": done.stdout}}


def behaviour_key(outcome):
    """The equivalence a split is computed over. Refusal wording is excluded."""
    if outcome["kind"] == "value":
        payload = {"kind": "value", "value": outcome["value"]}
    else:
        # Every non-value outcome is "this member did not return a result".
        # The exception class is kept because it distinguishes an in-band
        # refusal from a crash; the message is not, because no criterion
        # pins the sentence.
        payload = {"kind": outcome["kind"], "error_type": outcome["error_type"]}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()
