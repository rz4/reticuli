"""CLI verb handlers: session setup, traced run, producer preflight.

Each function here is the plain business logic behind one `ret` verb
(`spec/layers.md`'s CLI table) -- ordinary parameters in, a data dict (or,
for `run`, the child's own exit code) out. Nothing here touches argparse
or `--json`; that rendering is `output.py`/`report.py`/`statusview.py`'s
job, consuming what these functions return.

`init` marks a workspace as a session (`.reticuli/`, plus the agent
handshake unless `no_agent` withholds it). `run` executes a command
inside a session and traces it as a `bash` event -- the same event
`reticuli.authoring.build_claim` later reads to find the gate command --
and always returns the child's own exit code, so a caller can use it as
a predicate. `rebuild` is where a named producer is expanded and its
credential preflighted *before* anything is spent: `_PRODUCERS` names
the producers this build knows, `_expand_producer` resolves a name (or
passes a literal command straight through), and `_PRODUCER_PASSTHROUGH`
lists the environment variables a caller's shell may hand a producer
past the gate's own scrub (`spec/claim-format.md`'s gate contract).

Reaches only `reticuli.kernel`'s pinned public surface and the other
layers' own public functions -- never a `reticuli._kernel` private
(`spec/layers.md`). Stdlib only.
"""
import json
import os
import platform
import subprocess
import time

from reticuli import kernel, _util
from reticuli import registry as _registry
from reticuli import transfer as _transfer
from reticuli import attest as _attest
from reticuli import authoring
from reticuli import pack as _pack
from reticuli import hooks as _hooks
from . import views as _views
from . import statusview as _statusview

VERSION = "2.2"

# -- producers: named, credentialed, preflighted before anything is spent ----

_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")

_PRODUCERS = {
    "codex": {"cmd": "codex exec --full-auto -", "credential": "OPENAI_API_KEY",
              "vendor": "openai", "model": "gpt-5-codex"},
    "claude": {"cmd": "claude -p --dangerously-skip-permissions",
               "credential": "ANTHROPIC_API_KEY", "vendor": "anthropic",
               "model": "claude"},
}


def _ensure(condition, message: str) -> None:
    """Refuse with `message` -- the one-voice reason every handler raises
    through -- if `condition` is false."""
    if not condition:
        raise kernel.ClaimError(message)


def _version_line() -> str:
    """One line identifying this build: name, version, interpreter."""
    return f"reticuli {VERSION} (python {platform.python_version()})"


def _expand_producer(producer: str) -> str:
    """A producer name or a literal shell command, resolved to what
    `kernel.rebuild` should run.

    A name registered in `_PRODUCERS` preflights its credential -- refused
    before a subprocess is ever started, not after it has already spent --
    and expands to its command. Anything else passes through unchanged: an
    ad hoc producer needs no registration.
    """
    spec = _PRODUCERS.get(producer)
    if spec is None:
        return producer
    credential = spec.get("credential")
    if credential:
        _ensure(os.environ.get(credential),
                f"producer {producer!r} needs ${credential} set before it can spend")
    return spec["cmd"]


def _scan_workspace(ws: str) -> list:
    """Every claim directory `ws` holds: sealed and transferred claims
    from its store, plus `ws` itself if it carries an unsealed recipe."""
    found = []
    for sub in ("sealed", "deps"):
        base = os.path.join(ws, kernel.STORE, sub)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name)
            if os.path.isdir(p):
                found.append(p)
    if os.path.isfile(os.path.join(ws, kernel.RECIPE)) or \
            os.path.isfile(os.path.join(ws, "claim.toml")):
        found.append(ws)
    return found


# -- init: mark a workspace as a session --------------------------------------


def init(ws: str, name: str = None, *, no_agent: bool = False) -> dict:
    """Mark `ws` as a session workspace: create its store directory and,
    unless `no_agent` withholds it, wire the agent handshake
    (`reticuli.hooks.install`) that feeds the session's trace."""
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)
    wired = None
    if not no_agent:
        wired = _hooks.install(ws)
    return {"name": name or os.path.basename(os.path.normpath(ws)) or ws,
            "path": ws, "hooks": wired}


# -- run: a traced command, exit code unchanged -------------------------------


def run(cmd: str, ws: str) -> int:
    """Run `cmd` inside session `ws`, tracing it as a `bash` event
    (the same event `authoring.build_claim` reads to find its gate
    command), and returning the child's own exit code unchanged -- so a
    session can use it as a predicate."""
    proc = subprocess.run(cmd, shell=True, cwd=ws)
    entry = {"event": "bash", "cmd": cmd, "ts": time.time()}
    _util.locked_append(os.path.join(ws, authoring.TRACE), json.dumps(entry, sort_keys=True))
    return proc.returncode


# -- hook: the agent handshake's own verb -------------------------------------


def hook(payload: dict):
    """One hook payload, mapped to a trace event (`reticuli.hooks.event`)."""
    return _hooks.event(payload)


def hooks(proj: str) -> dict:
    """Wire the agent handshake into `proj` (`reticuli.hooks.install`)."""
    return _hooks.install(proj)


# -- status: a claim's full state, or a whole workspace's --------------------


def status(d: str, *, workspace: bool = False) -> dict:
    """A claim's full state (`_cli.views._claim_view`), or -- with
    `workspace` -- every claim `_scan_workspace` finds inside `d`."""
    if workspace:
        return {"claims": [_views._claim_view(c) for c in _scan_workspace(d)]}
    return _views._claim_view(d)


def tree(d: str) -> list:
    """`d`'s declared files, each tagged with its step class and whether
    its bytes are present (`_cli.statusview._files_claim`)."""
    return _statusview._files_claim(d)


# -- seal / verify ------------------------------------------------------------


def seal(d: str) -> dict:
    """Freeze `d` into a claim: compute the root, write the manifest."""
    _ensure(os.path.isdir(d), f"no such claim directory: {d!r}")
    kernel.seal(d)
    return kernel.read_manifest(d)


def verify(d: str) -> dict:
    """Recompute `d`'s root from the bytes present and compare it with
    the sealed manifest -- identity only, no gate is executed."""
    data = dict(kernel.verify(d))
    try:
        data.setdefault("name", kernel.read_manifest(d).get("name"))
    except kernel.ClaimError:
        pass
    return data


# -- rebuild: the producer-preflighted verb -----------------------------------


def rebuild(d: str, producer: str, into: str, **kwargs) -> dict:
    """Regrow `d`'s generated outputs with `producer` -- a registered name
    (preflighted for its credential, then expanded to its command) or a
    literal shell command passed straight through -- forwarding the
    passthrough environment variables a caller's own shell carries, and
    recording a registered producer's vendor and model to the ledger."""
    _ensure(os.path.isdir(d), f"no such claim directory: {d!r}")
    spec = _PRODUCERS.get(producer)
    cmd = _expand_producer(producer)

    producer_env = dict(kwargs.pop("producer_env", None) or {})
    for key in _PRODUCER_PASSTHROUGH:
        if key in os.environ:
            producer_env.setdefault(key, os.environ[key])

    result = kernel.rebuild(d, cmd, into, producer_env=producer_env, **kwargs)

    if spec is not None:
        kernel.ledger(into, {"event": "producer", "vendor": spec.get("vendor"),
                              "model": spec.get("model", producer)})
    return result


# -- audit / crosscheck: deep by default, --shallow opts out ------------------


def audit(d: str, *, shallow: bool = False, **kwargs) -> dict:
    """Re-execute every gate, cold and sandboxed; composed claims audit
    recursively unless `shallow` opts out (`spec/verification.md`)."""
    data = dict(kernel.audit(d, **kwargs))
    if not shallow and _registry.components_of(d):
        deep = _registry.audit_deep(d)
        data["ok"] = bool(data.get("ok")) and bool(deep.get("ok"))
        data["layers"] = deep.get("layers", [])
    try:
        manifest = kernel.read_manifest(d)
        data.setdefault("name", manifest.get("name"))
        data.setdefault("root", manifest.get("root"))
    except kernel.ClaimError:
        pass
    return data


def crosscheck(m1: str, m2: str, m3: str, *, shallow: bool = False, **kwargs) -> dict:
    """The three-machine test; directory legs re-earn their deep audit
    too unless `shallow` opts out."""
    if shallow:
        return kernel.crosscheck(m1, m2, m3, **kwargs)
    return _registry.crosscheck_deep(m1, m2, m3, **kwargs)


# -- sign / attest -------------------------------------------------------------


def sign(d: str, key: str, principal: str, ws: str = None) -> dict:
    """The signing ceremony: authorization over `d`'s whole chain."""
    return _attest.sign(d, key, principal, ws=ws)


def attest(d: str, key: str, principal: str) -> dict:
    """A plain signed statement of this build."""
    return _attest.attest(d, key, principal)


# -- pull / export / import ---------------------------------------------------


def pull(src: str, dest: str, ws: str = None) -> dict:
    """Bring claim `src` into `dest`, with its whole closure in the store."""
    return _registry.pull(src, dest, ws=ws)


def export(d: str, tar_path: str, blind: bool = False) -> dict:
    """Package `d`'s declared content into a byte-deterministic tar."""
    _transfer.export(d, tar_path, blind=blind)
    return {"path": tar_path, "blind": blind}


def import_(tar_path: str, dest: str) -> dict:
    """Extract `tar_path` into `dest`, and reverify."""
    return _transfer.import_(tar_path, dest)


# -- claims: a workspace's sealed store ---------------------------------------


def claims(ws: str) -> list:
    """Every sealed claim in `ws`'s store: name, root, live phase."""
    return _registry.claims(ws)


# -- pack: a project as a self-claim ------------------------------------------


def pack(root: str, name: str, generated: list, inputs: list, gate: str,
         gate_output: str, **kwargs) -> dict:
    """Turn `root` into a sealed claim in place."""
    return _pack.pack(root, name, generated, inputs, gate, gate_output, **kwargs)
