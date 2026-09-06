"""The kernel: the whole invariant, and nothing else.

A claim is valid iff an independent *redo* satisfies the same check as the
original. Everything composes toward `three_machine`.

The one idea that keeps it small — **the root is the claim.** A record's identity
is `hash(recipe + dry seeds + pinned verdicts)`, and it *excludes* the free
outputs (the implementation). So two valid realizations of one claim share a
root, and the three-machine test collapses to root equality. The basin of
attraction is exactly the preimage of the root.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import tomllib

STORE = ".reticuli"
RECIPE = "reticuli.toml"
LEDGER = os.path.join(STORE, "ledger.jsonl")
MINT = os.path.join(STORE, "mint")           # authorization material (statements + sigs)
NAMESPACE = "reticuli"                       # the ssh-keygen -Y signing namespace
TOLERANCE = 2.0                 # comparable cost: 1/2 <= C3/C1 <= 2, unless the claim declares
GATE_TIMEOUT = 300.0            # a gate's wall-clock ceiling (s); the record may declare its own
# A gate runs with a SCRUBBED environment — only these host vars pass through,
# so a hostile gate cannot read an inherited credential (an API key, a token)
# and write it into its room to exfiltrate at export. Producers are NOT scrubbed
# (they are your command). The record's own RETICULI_* and a room-local HOME/
# TMPDIR are added on top. RETICULI_JAILED (the inherited-jail signal) is not in
# the allowlist, so a record's gate can never inject it — only our own _jailed,
# below, sets it, and it is a single, well-known name any conforming kernel
# reads, so the self-hosted jail handshake survives an independent regeneration.
_ENV_PASS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SYSTEMROOT")
_JAILED = "RETICULI_JAILED"          # the inherited-jail signal (internal; never set this yourself)


def _gate_env(extra: dict) -> dict:
    """A scrubbed base environment for a record's gate: a minimal host allowlist
    plus the caller's `extra`. RETICULI_JAILED is not in the allowlist, so an
    ambient value cannot ride in through a record; _jailed sets it only when it
    truly wraps."""
    env = {k: os.environ[k] for k in _ENV_PASS if k in os.environ}
    env.setdefault("PATH", os.defpath)
    env.update(extra)
    env.pop(_JAILED, None)
    return env


def _gate_timeout(recipe: dict) -> float:
    """A gate's time limit: the record's declared `[record] gate_timeout`, else
    RETICULI_GATE_TIMEOUT, else the default. A hostile record cannot RAISE it
    past the environment's ceiling — the smaller of the two wins."""
    declared = recipe.get("record", {}).get("gate_timeout")
    env = os.environ.get("RETICULI_GATE_TIMEOUT")
    ceiling = float(env) if env else GATE_TIMEOUT
    return min(float(declared), ceiling) if declared is not None else ceiling


class ReticuliError(Exception):
    """A refusal with a reason — the only kind of error the kernel raises."""


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _hf(path: str) -> str:
    """Hash a declared file's bytes — the one BYTES boundary (as _safe is the one
    PATH boundary). A record file must be a REGULAR file with a SINGLE link, so
    the content it seals lives inside the record and nowhere else. This refuses
    the filesystem adversaries a path check cannot see: a FIFO or device (read
    blocks or misbehaves — a DoS or nonsense in the claim), a directory or
    socket, and — the one _safe misses — a HARDLINK to an inode outside the
    record (path stays inside, st_nlink > 1 betrays the second name, and its
    bytes would be sealed as if they were the record's own). A record is
    self-contained; its own seeds and outputs are freshly written, so nlink == 1
    holds for every honest file and only an adversary's aliased inode fails it."""
    try:
        st = os.lstat(path)                       # lstat: never traverse a final symlink here
    except OSError as e:
        raise ReticuliError(f"declared file missing: {path!r} ({e})") from e
    if not stat.S_ISREG(st.st_mode):
        raise ReticuliError(f"declared file is not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ReticuliError(
            f"declared file has {st.st_nlink} hard links (must be self-contained): {path!r}")
    try:
        with open(path, "rb") as f:
            return _h(f.read())
    except OSError as e:
        raise ReticuliError(f"declared file unreadable: {path!r} ({e})") from e


def _out(step: dict) -> str:
    return step["output"]


def _seeds(recipe: dict) -> list[str]:
    """Dry seeds live under [record] (they are part of the record's identity)."""
    return recipe.get("record", {}).get("inputs", [])


def load_recipe(d: str) -> dict:
    """Parse the record's recipe, refusing hostile bytes with a ReticuliError
    rather than leaking a raw TOML/OS crash, and validating the minimal shape the
    kernel relies on: a [record] table with a name, every step a table with a
    kind (produce/gate steps naming an output, a gate a run). A record's own
    recipe is untrusted input — malformed is refused here, not crashed on
    downstream where the failure is a bare KeyError with no reason attached."""
    try:
        with open(os.path.join(d, RECIPE), "rb") as f:
            recipe = tomllib.load(f)
    except (OSError, ValueError) as e:
        raise ReticuliError(f"unreadable recipe in {d}: {e}") from e
    rec = recipe.get("record")
    if not isinstance(rec, dict) or not isinstance(rec.get("name"), str):
        raise ReticuliError(f"malformed recipe in {d} ([record] name required)")
    for step in recipe.get("step", []):
        if not isinstance(step, dict) or "kind" not in step:
            raise ReticuliError(f"malformed recipe step in {d} (a step needs a kind)")
        if step["kind"] not in ("produce", "gate"):
            raise ReticuliError(
                f"unknown step kind in {d}: {step['kind']!r} (expected 'produce' or 'gate')")
        if "output" not in step:
            raise ReticuliError(f"malformed {step['kind']} step in {d} (an output is required)")
        if step["kind"] == "gate" and "run" not in step:
            raise ReticuliError(f"malformed gate step in {d} (a run is required)")
    return recipe


def _safe(root: str, name: str) -> str:
    """Join a recipe-declared path under `root`, refusing any that escapes it.
    A record's own recipe is untrusted input: an absolute path, a `..` climb, or
    a symlink whose target leaves the record would let the kernel read or write
    outside the record *before* any gate sandbox is relevant. Every recipe path
    (seed, output) crosses here, so confinement is one boundary, checked once per
    use. Returns the plain join for safe names; raises for the rest."""
    if os.path.isabs(name) or not name:
        raise ReticuliError(f"unsafe recipe path (absolute or empty): {name!r}")
    root_r = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root_r, name))
    if full != root_r and not full.startswith(root_r + os.sep):
        raise ReticuliError(f"unsafe recipe path (escapes the record root): {name!r}")
    return os.path.join(root, name)


# -- the claim: recipe + dry seeds + pinned verdicts (free outputs excluded) --


def claim(recipe: dict, d: str) -> str:
    """The root. Two realizations that pass the same checks hash to the same
    value; the free implementation never enters it."""
    parts: dict[str, str] = {"recipe": json.dumps(recipe, sort_keys=True)}
    for seed in _seeds(recipe):
        parts[f"seed:{seed}"] = _hf(_safe(d, seed))
    for step in recipe.get("step", []):
        if step.get("class", "exact") != "free":          # a pinned verdict
            parts[f"pin:{_out(step)}"] = _hf(_safe(d, _out(step)))
    return _h(json.dumps(parts, sort_keys=True).encode())


def _signers() -> str | None:
    """The trust anchor: an ssh allowed-signers file naming the identities you
    trust to authorize a mint. RETICULI_SIGNERS, else ~/.config/reticuli/
    allowed_signers, else none — and with none, nothing is authorized *to you*.
    Trust is verifier-relative by construction; the tool never invents it."""
    p = os.environ.get("RETICULI_SIGNERS")
    if p and os.path.isfile(os.path.expanduser(p)):
        return os.path.expanduser(p)
    default = os.path.expanduser(os.path.join("~", ".config", "reticuli", "allowed_signers"))
    return default if os.path.isfile(default) else None


def phase(d: str) -> str:
    """vapor (no record) · liquid (sealed) · solid (authorized AND proven — see
    minted()). A `proof` on the manifest is residue, never phase on its own; a
    hand-written proof or a signature from an untrusted key does not make a
    solid. Because trust is verifier-relative, a record with no reachable trust
    anchor is liquid *to you* even if others have vouched for it."""
    m = os.path.join(d, STORE, "manifest.json")
    if not os.path.isfile(m):
        return "vapor"
    read_manifest(d)             # a present-but-corrupt manifest is refused, never a silent "liquid"
    claim(load_recipe(d), d)     # phase agrees with verify on validity: a record whose recipe is
    #                              malformed, escapes confinement, or names a missing seed/pin has no
    #                              phase to report — refuse it here rather than answer a positive "liquid"
    return "solid" if minted(d)["ok"] else "liquid"


def minted(d: str, signers: str | None = None) -> dict:
    """The local solid test — solid means AUTHORIZED and PROVEN, both verifiable
    here and now. A record is solid iff it carries a mint authorization that:
    (1) is signed by a TRUSTED identity — the signature verifies against an
    allowed-signers file (arg, else RETICULI_SIGNERS, else the default); with no
    anchor nothing is authorized to you; (2) names this record's sealed root;
    (3) binds the stored review packet by its signed digest — the reviewed
    bundle cannot be swapped; (4) whose packet's realization digest still
    describes the free bytes on disk — the mint froze THIS crystal, and a
    drifted crystal is not it; and (5) whose packet records a three-machine
    proof — authorization vouches, the recorded proof couples 'it reproduced' to
    'a human accepts it'. WHO you trust is yours (the signers file); the
    cross-component chain fold is attest.mint_check's."""
    signers = signers or _signers()
    base = os.path.join(d, MINT)
    names = (sorted(n for n in os.listdir(base) if n.endswith(".mint.json"))
             if os.path.isdir(base) else [])
    if not names:
        return {"ok": False, "statements": [], "signers": signers}
    root = read_manifest(d)["root"]
    digest = realization_digest(d)
    out = []
    for name in names:
        path, why = os.path.join(base, name), []
        try:
            st = _read(path)
        except (OSError, ValueError):
            out.append({"statement": name, "ok": False, "why": ["unreadable"]})
            continue
        if st.get("root") != root:
            why.append("statement names a different root")
        try:
            packet = _read(path[: -len(".mint.json")] + ".packet.json")
            if _h(json.dumps(packet, sort_keys=True).encode()) != st.get("packet_digest"):
                why.append("stored packet does not match the signed digest")
            elif packet.get("realization_digest") != digest:
                why.append("realization drifted since the mint")
            elif not packet.get("proof"):
                why.append("no three-machine proof recorded (authorized, not proven)")
        except (OSError, ValueError):
            why.append("review packet missing or unreadable")
        if not signers:
            why.append("no trust anchor (set RETICULI_SIGNERS); not authorized to you")
        else:
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                r = subprocess.run(
                    ["ssh-keygen", "-Y", "verify", "-f", os.path.expanduser(signers),
                     "-I", st.get("identity", ""), "-n", NAMESPACE, "-s", path + ".sig"],
                    input=raw, capture_output=True, check=False)
                if r.returncode != 0:
                    why.append("signature not from a trusted signer")
            except OSError:
                why.append("signature not checkable")
        out.append({"statement": name, "identity": st.get("identity"),
                    "ok": not why, "why": why})
    return {"ok": any(x["ok"] for x in out), "statements": out, "signers": signers}


# -- seal / verify: identity ------------------------------------------------


def seal(d: str, proof: dict | None = None, components: list | None = None) -> dict:
    """Freeze the realization in `d` into a record: compute the root, write the
    manifest. Deterministic — commits like a lockfile."""
    recipe = load_recipe(d)
    # The manifest is pure identity: name + root (+ proof, + component links).
    # It carries no free-output hashes, so editing the implementation (free)
    # never churns it — a self-hosted record stays byte-stable and git-clean.
    manifest = {"name": recipe["record"]["name"], "root": claim(recipe, d)}
    if proof:
        manifest["proof"] = proof
    if components:
        manifest["components"] = components
    os.makedirs(os.path.join(d, STORE), exist_ok=True)
    _write(os.path.join(d, STORE, "manifest.json"), manifest)
    return manifest


def read_manifest(d: str) -> dict:
    """Read the record's manifest, refusing hostile bytes with a ReticuliError
    rather than a raw parse crash: a corrupt or malformed manifest is a damaged
    record, not a verifier bug. The manifest is pure identity — name + root
    (+ optional proof/components) — so both must be present as strings."""
    path = os.path.join(d, STORE, "manifest.json")
    try:
        m = _read(path)
    except (OSError, ValueError) as e:
        raise ReticuliError(f"unreadable manifest in {d}: {e}") from e
    if not isinstance(m, dict) or not isinstance(m.get("name"), str) \
            or not isinstance(m.get("root"), str):
        raise ReticuliError(f"malformed manifest in {d} (name and root required)")
    return m


def verify(d: str) -> dict:
    """Recompute the root from the bytes on disk; it must equal the sealed root.
    Needs no ledger — a git-cloned record verifies from its committed identity.
    """
    if phase(d) == "vapor":
        raise ReticuliError(f"no record in {d} (seal first)")
    recipe = load_recipe(d)
    manifest = read_manifest(d)
    got = claim(recipe, d)
    return {"name": manifest["name"], "root": manifest["root"],
            "recomputed": got, "ok": got == manifest["root"],
            "phase": phase(d)}


# -- realize: an independent redo (M3) --------------------------------------


def realize(d: str, producer: str, into: str, seed_from: dict | None = None,
            produce_from: dict | None = None, exist_ok: bool = False) -> dict:
    """Seed a clean room from the record's dry inputs, run each produce step
    with a fresh producer and each gate cold, then seal. A faithful redo lands
    on the same root.

    seed_from maps a seed path to a *freshly rehydrated* source (from a
    recursively-rehydrated component) instead of the carried bytes — this is how
    DAG-aware rehydrate threads a dependency's output up to its dependent.
    produce_from does the same for a *free* produce step whose `from` is a
    component: the bytes are supplied by the rehydrated component instead of the
    producer, so the output stays free (never pinned) yet layered. exist_ok
    tolerates a target already holding rehydrated deps (under .reticuli/deps).

    Every oracle call and gate is accounted to the target's ledger — cost is
    residue of the event, never part of the claim.
    """
    seed_from = seed_from or {}
    produce_from = produce_from or {}
    recipe = load_recipe(d)
    # absolute, because the producer runs with cwd=into: a relative RETICULI_USAGE
    # would resolve against the producer's cwd, not ours, and the redo's cost
    # (tokens/usd the producer reports) would be written where we never read it.
    into = os.path.abspath(into)
    if os.path.exists(os.path.join(into, RECIPE)) or (os.path.exists(into) and not exist_ok):
        raise ReticuliError(f"target exists: {into}")
    os.makedirs(into, exist_ok=True)
    shutil.copyfile(os.path.join(d, RECIPE), os.path.join(into, RECIPE))
    for seed in _seeds(recipe):
        _copy(seed_from.get(seed) or _safe(d, seed), _safe(into, seed))
    # component-supplied free code goes in first, so a producer can build on it
    for step in recipe.get("step", []):
        if step["kind"] == "produce" and _out(step) in produce_from:
            _copy(produce_from[_out(step)], _safe(into, _out(step)))
    usage_path = os.path.join(into, STORE, "usage.json")
    os.makedirs(os.path.join(into, STORE), exist_ok=True)
    for step in recipe.get("step", []):
        out = _out(step)
        out_path = _safe(into, out)             # refuse an output name that escapes the room
        if step["kind"] == "produce" and out in produce_from:
            _ledger_add(into, {"event": "reuse", "output": out})
            continue
        t0 = time.monotonic()
        if step["kind"] == "gate":
            # a record's gate runs through the one gate entry point: scrubbed
            # environment (a hostile gate cannot exfiltrate an inherited secret),
            # bounded wall-clock, inside the quarantine
            r, jailed_as = run_gate(step["run"], into, recipe,
                                    {"RETICULI_REQUEST": step.get("request", ""),
                                     "RETICULI_OUTPUT": out})
        else:
            # the producer is YOUR command, not the record's — it keeps your env
            env = {**os.environ, "RETICULI_REQUEST": step.get("request", ""),
                   "RETICULI_OUTPUT": out, "RETICULI": "1", "RETICULI_USAGE": usage_path}
            r = subprocess.run(producer, shell=True, cwd=into, env=env,
                               capture_output=True, text=True, check=False)
        if r.returncode != 0 or not os.path.isfile(out_path):
            raise ReticuliError(
                f"redo failed at {out}: {(r.stderr or r.stdout).strip()[:200]}")
        entry = {"event": "gate" if step["kind"] == "gate" else "oracle",
                 "output": out, "seconds": round(time.monotonic() - t0, 3)}
        if step["kind"] == "gate":
            entry["quarantine"] = jailed_as
        else:
            entry.update({"calls": 1, **_usage(usage_path)})
        _ledger_add(into, entry)
    return {**seal(into), "into": into, "cost": cost(into)}


# -- quarantine: a record's gates are not your shell -------------------------

_PROFILE = """(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "{room}") (subpath "/dev"))
"""

_BWRAP: bool | None = None


def _bwrap_ok() -> bool:
    global _BWRAP                      # probed once — a present-but-broken bwrap is "none"
    if _BWRAP is None:
        _BWRAP = bool(shutil.which("bwrap")) and subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
            capture_output=True, check=False).returncode == 0
    return _BWRAP


def jail(cmd: str, room: str) -> tuple[list[str] | str, str]:
    """Wrap a gate command in the platform's jail: writes confined to the room,
    network denied. Producers are never jailed — you chose that command; a
    pulled record's gates you did not. RETICULI_QUARANTINE: auto (default) uses
    a jail when the platform has one, require refuses to run without one, off
    opts out. Whichever happened, the ledger records it."""
    mode = os.environ.get("RETICULI_QUARANTINE", "auto")
    if mode == "off":
        return cmd, "off"
    if os.environ.get(_JAILED):               # jails don't nest; the outer one holds
        return cmd, "inherited"
    room = os.path.realpath(room)
    if sys.platform == "darwin":
        profile = _PROFILE.format(room=room.replace('"', '\\"'))
        return ["sandbox-exec", "-p", profile, "/bin/sh", "-c", cmd], "seatbelt"
    if _bwrap_ok():
        return ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", "--bind", room, room, "--unshare-net",
                "--die-with-parent", "/bin/sh", "-c", cmd], "bubblewrap"
    if mode == "require":
        raise ReticuliError("quarantine required, but no jail here (sandbox-exec or bwrap)")
    return cmd, "none"


def _jailed(cmd: str, room: str, env: dict,
            timeout: float | None = None) -> tuple[subprocess.CompletedProcess, str]:
    """Run a gate in the jail, time-bounded, with a scrubbed environment. TMPDIR
    and HOME move inside the room so well-behaved temp/home use stays confined;
    the jail refuses the rest. When we wrap, we set the inherited-jail signal
    (RETICULI_JAILED) in the child env so a nested kernel does not re-apply a
    jail — a single well-known name, so an independently regenerated kernel
    reads the same handshake and the self-host does not nest."""
    wrapped, status = jail(cmd, room)
    if isinstance(wrapped, list):            # we wrapped: room-local tmp/home + the signal
        tmp = os.path.join(os.path.realpath(room), STORE, "tmp")
        os.makedirs(tmp, exist_ok=True)
        env = {**env, "TMPDIR": tmp, "HOME": tmp, _JAILED: status}
    elif status == "inherited":              # carry the outer jail's context forward
        env = {**env, **{k: os.environ[k]
                         for k in ("TMPDIR", "HOME", _JAILED)
                         if k in os.environ}}
    return _run_bounded(wrapped, shell=isinstance(wrapped, str), cwd=room,
                        env=env, timeout=timeout), status


def run_gate(cmd: str, room: str, recipe: dict,
             extra: dict | None = None) -> tuple[subprocess.CompletedProcess, str]:
    """THE ONE ENTRY POINT for running a record's gate. It owns the execution
    contract so every caller obeys it identically: a SCRUBBED environment
    (_gate_env — a hostile gate cannot read an inherited secret and seal it into
    a verdict), a BOUNDED wall-clock (_gate_timeout — it cannot hang the
    verifier), inside the QUARANTINE (_jailed). realize, audit, condense, and
    pack all run gates through here; an authoring module that reaches for _jailed
    directly would bypass the scrub and the bound, so the authoring check forbids
    it."""
    env = _gate_env({"RETICULI": "1", **(extra or {})})
    return _jailed(cmd, room, env, timeout=_gate_timeout(recipe))


def _run_bounded(argv, *, shell: bool, cwd: str, env: dict,
                 timeout: float | None) -> subprocess.CompletedProcess:
    """subprocess.run with a wall-clock ceiling that kills the whole process
    group (a gate that forks children cannot outlive the limit). A timeout is a
    failed gate (returncode 124), not an exception — realize reports it as a
    redo failure and audit as a verdict that did not reproduce."""
    with subprocess.Popen(argv, shell=shell, cwd=cwd, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, start_new_session=True) as p:
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                p.kill()
            p.communicate()
            return subprocess.CompletedProcess(
                argv, 124, "", f"gate exceeded the {timeout}s time limit")
    return subprocess.CompletedProcess(argv, p.returncode, out, err)


# -- the cost ledger: residue of the event, never part of the claim ----------


def _ledger_add(d: str, entry: dict) -> None:
    os.makedirs(os.path.join(d, STORE), exist_ok=True)
    with open(os.path.join(d, LEDGER), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _usage(path: str) -> dict:
    """Optional oracle-reported usage ({tokens, usd}), consumed once per call."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            u = json.load(f)
    except (json.JSONDecodeError, OSError):
        u = {}
    os.remove(path)
    u = u if isinstance(u, dict) else {}
    return {k: u[k] for k in ("tokens", "usd") if isinstance(u.get(k), (int, float))}


def cost(d: str) -> dict | None:
    """Total the machine's ledger — the paid cost of its realization event:
    oracle calls, wall seconds, and tokens/usd where a producer reported them.
    None if nothing was measured. The root never sees any of this."""
    path = os.path.join(d, LEDGER)
    if not os.path.isfile(path):
        return None
    totals = {"calls": 0, "seconds": 0.0, "tokens": 0, "usd": 0.0}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            for k in totals:
                if isinstance(e.get(k), (int, float)):
                    totals[k] += e[k]
    totals["seconds"] = round(totals["seconds"], 3)
    totals["usd"] = round(totals["usd"], 6)
    return {k: v for k, v in totals.items() if v} or {"calls": 0}


def _comparable(c1: dict | None, c3: dict | None, tol: float) -> dict:
    """C3/C1 in the strongest unit both machines measured (usd > tokens > calls
    > seconds), within [1/tol, tol]. An unmeasured machine is reported, not
    failed: comparable is None and does not gate the test."""
    if not c1 or not c3:
        missing = " and ".join(m for m, c in (("M1", c1), ("M3", c3)) if not c)
        return {"tolerance": tol, "comparable": None,
                "note": f"unmeasured: no ledger on {missing}"}
    unit = next((u for u in ("usd", "tokens", "calls", "seconds")
                 if c1.get(u) and c3.get(u)), None)
    if unit is None:
        return {"tolerance": tol, "comparable": None, "note": "no shared measured unit"}
    ratio = round(c3[unit] / c1[unit], 3)
    return {"unit": unit, "c1": c1[unit], "c3": c3[unit], "ratio": ratio,
            "tolerance": tol, "comparable": (1.0 / tol) <= ratio <= tol}


# -- audit: the verdicts must reproduce, not merely be carried ---------------


def audit(d: str) -> dict:
    """The deep check. verify() proves *identity* — the root holds over the
    bytes present. audit() proves the verdicts are *earned by* those bytes: it
    rebuilds a scratch room from the record's recipe, seeds, and produce
    outputs (no verdicts carried in), re-runs every gate jailed, and requires
    each pinned output to reproduce the record's bytes exactly. A verdict that
    was copied rather than produced does not survive it."""
    v = verify(d)
    recipe = load_recipe(d)
    steps = recipe.get("step", [])
    room = tempfile.mkdtemp(prefix="reticuli-audit-")
    gates, ok = [], v["ok"]
    try:
        shutil.copyfile(os.path.join(d, RECIPE), os.path.join(room, RECIPE))
        for seed in _seeds(recipe):
            _copy(_safe(d, seed), _safe(room, seed))
        for step in steps:
            if step["kind"] == "produce" and os.path.isfile(_safe(d, _out(step))):
                _copy(_safe(d, _out(step)), _safe(room, _out(step)))
        for step in steps:
            if step["kind"] != "gate":
                continue
            out = _out(step)
            r, jailed_as = run_gate(step["run"], room, recipe)
            produced = _safe(room, out)
            reproduced = (r.returncode == 0 and os.path.isfile(produced)
                          and os.path.isfile(_safe(d, out))
                          and _hf(produced) == _hf(_safe(d, out)))
            gates.append({"output": out, "ok": reproduced, "quarantine": jailed_as})
            ok = ok and reproduced
    finally:
        shutil.rmtree(room, ignore_errors=True)
    return {"name": v["name"], "root": v["root"], "fresh": v["ok"],
            "gates": gates, "ok": ok}


# -- three_machine: THE INVARIANT -------------------------------------------


def three_machine(m1: str, m2: str, m3: str) -> dict:
    """M1 a claim, M2 a byte-reuse, M3 an independent redo. Valid iff all three
    share a root — the redo reproduced the claim, the reuse proves the record is
    self-contained — AND every machine's gates re-run clean against its own
    bytes (audit: a carried verdict does not survive), and, where both machines
    kept a ledger, the redo's cost is comparable within the claim's declared
    tolerance. Root equality alone is identity; audit makes it evidence.

    The three machines must be three distinct directories: one record handed in
    thrice trivially "agrees with itself", which proves nothing, so identical
    paths (by realpath, catching symlink and `.`/`..` aliases) are refused.
    Independence beyond distinctness — that M3's bytes were produced, not copied
    from M1 — cannot be shown from content and is reported as unestablished."""
    real = {name: os.path.realpath(m) for name, m in (("M1", m1), ("M2", m2), ("M3", m3))}
    if len(set(real.values())) < 3:
        raise ReticuliError(
            "three_machine needs three distinct machines; got aliased paths: "
            + ", ".join(f"{n}={p}" for n, p in real.items()))
    roots = {name: verify(m)["root"] for name, m in (("M1", m1), ("M2", m2), ("M3", m3))}
    audited = {name: audit(m)["ok"] for name, m in (("M1", m1), ("M2", m2), ("M3", m3))}
    integrity = all(verify(m)["ok"] for m in (m1, m2, m3))
    reuse = _outputs(m2) == _outputs(m1)          # M2 carries M1's outputs, byte-for-byte
    equivalence = len(set(roots.values())) == 1    # ONE claim across all three machines
    tol = float(load_recipe(m1).get("record", {}).get("tolerance", TOLERANCE))
    cost_ = _comparable(cost(m1), cost(m3), tol)
    return {"roots": roots, "integrity": integrity, "reuse": reuse,
            "equivalence": equivalence, "audited": audited, "cost": cost_,
            "independence": "unestablished (distinct paths only; "
                            "content cannot prove M3 was not copied from M1)",
            "satisfied": integrity and reuse and equivalence
            and all(audited.values()) and cost_["comparable"] is not False}


def freeze_dry(m1: str, m2: str, m3: str) -> dict:
    """Prove, then record: on a passing three-machine test, seal the proof onto
    M1 as residue — a fact about bytes at prove time, readable but not locally
    re-verifiable (M2 and M3 are gone). It does NOT make the record solid:
    solid is a verifiable authorization, the mint ceremony's act."""
    result = three_machine(m1, m2, m3)
    result["proof_recorded"] = False
    if result["satisfied"]:
        seal(m1, proof={"kind": "three-machine",
                        "m2": result["roots"]["M2"], "m3": result["roots"]["M3"]})
        result["proof_recorded"] = True
    return result


def _outputs(d: str) -> dict:
    recipe = load_recipe(d)
    return {_out(s): _hf(_safe(d, _out(s))) for s in recipe.get("step", [])}


# -- the mint: solid identity, bottom-anchored -------------------------------


def realization_digest(d: str) -> str:
    """The chosen crystal: a hash of this record's OWN free bytes — every free
    produce output not supplied by a component (`from`). The root ignores these
    (that freedom is the basin); the mint freezes them. `from` outputs belong to
    the component and are covered by folding the component's mint, so they are
    excluded here to avoid double-counting."""
    recipe = load_recipe(d)
    own = [[_out(s), _hf(_safe(d, _out(s)))]
           for s in recipe.get("step", [])
           if s["kind"] == "produce" and "from" not in s and s.get("class") == "free"
           and os.path.isfile(_safe(d, _out(s)))]
    return _h(json.dumps(sorted(own), sort_keys=True).encode())


def mint_node(root: str, digest: str, component_mints: list[str]) -> str:
    """THE FOLD. A rung's mint binds its claim root, its realization digest (the
    frozen bytes the root ignores), and the mints of everything beneath it. The
    kernel's mint is the genesis — the most significant digit — and a disturbance
    at any height moves that rung's mint and every mint above it, never one below:
    the lowest mint that moved names the floor the change entered on. Liquid
    records leave this uncomputed; minting is where bytes freeze."""
    return _h(json.dumps([root, digest, sorted(component_mints)], sort_keys=True).encode())


# -- small io helpers -------------------------------------------------------


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path: str, obj: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def _copy(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copyfile(src, dst)
