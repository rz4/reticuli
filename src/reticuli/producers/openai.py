"""An agentic OpenAI producer for v2 claims — the cross-vendor rebuilder.

Ported from the v1 lab's agentic OpenAI producer with two changes: it reads
the v2 recipe (reticuli.toml, or claim.toml for claims sealed before the
rename), and read_file takes an offset so the model can read checks larger
than one chunk.

Runs INSIDE a claim directory (cwd = the room). Drives a bounded tool-use
loop: the model may read the room's files, write its generated outputs, and
run the gate until it passes or the turn cap is hit. Respects
OPENAI_BASE_URL. Env: RETICULI_MODEL (default gpt-5), RETICULI_OUTPUT (the
output this call must produce), RETICULI_AGENT_TURNS (default 40),
RETICULI_USAGE (ledger drop file), RETICULI_PRICE
("input,output[,cache_read]" usd per million tokens). RETICULI_DRY_PROMPT=1
prints the exact prompt the claim induces and exits without calling any API.
"""
import json
import math
import os
import re
import sys
import tomllib

from . import _gate

CHUNK = 20000

#: What every provider accepts as a tool name. The strictest limit seen is
#: Bedrock's 64 characters; the character class is the common denominator.
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


#: Total seconds this producer may spend waiting out a degraded API, across
#: ALL calls. Patience used to be per-call, and the docstring's promise that
#: "a blip costs minutes, never the session" was exactly inverted by a
#: sustained outage: with four 120-second sleeps available to every call in a
#: forty-turn loop, each affected attempt slept until the kernel's one-hour
#: producer timeout killed it. Measured 2026-10-15 -- ledger timestamps
#: exactly sixty minutes apart, three attempts per layer, three hours spent
#: and nothing learned, and the result filed as a producer failure. A budget
#: makes a degraded API fail FAST, so the harness can record it as
#: infrastructure instead of letting it impersonate capability slowly.
PATIENCE_BUDGET = float(os.environ.get("RETICULI_PATIENCE", "300"))

#: Longest single wait. The gateway publishes a 60-second rate-limit window
#: and sends it as `retry-after`, so waiting longer than that buys nothing
#: and spends the patience budget on sleep instead of work. The previous
#: constant was 120 -- twice the window, flat, and unjittered.
CAP_WAIT = float(os.environ.get("RETICULI_MAX_WAIT", "60"))
_waited = {"seconds": 0.0}


def _retry_after(exc):
    """The wait the SERVER asked for, if it said. A gateway that publishes
    its own window knows better than any constant compiled in here."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    try:
        value = float(headers.get("retry-after") or headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None
    return value if 0 < value <= CAP_WAIT else None


def _patient(call, tries=6, base=1.0):
    """Outlive a transient outage; refuse to outlive a sustained one.

    Backoff is exponential WITH JITTER, which is the gateway's own documented
    advice and not a stylistic choice: a flat, unjittered wait makes parallel
    producers sleep in lockstep and retry in one wave, and the limit being
    hit is per USER across every project and key -- so eleven lineages
    retrying together is one client hammering one bucket. Measured
    2026-10-15: synchronised 120-second waits across eleven parallel
    producers produced stalls correlated enough to look like a shared
    capability wall at one layer. They were a thundering herd.

    Patience is also budgeted for the RUN, not for each call, so one bad
    hour cannot be bought a few minutes at a time.
    """
    import random
    import time
    delay = base
    for attempt in range(tries):
        try:
            return call()
        except Exception as exc:
            if attempt == tries - 1:
                raise
            asked = _retry_after(exc)
            wait = asked if asked is not None else min(delay, CAP_WAIT)
            # jitter: uniform in [50%, 100%] of the interval, so clients that
            # failed together do not come back together
            wait *= 0.5 + random.random() * 0.5
            if _waited["seconds"] + wait > PATIENCE_BUDGET:
                print(f"producer: giving up on a degraded API after "
                      f"{_waited['seconds']:.0f}s of waiting "
                      f"({exc.__class__.__name__}); the patience budget of "
                      f"{PATIENCE_BUDGET:.0f}s is spent, so this is an "
                      f"infrastructure failure and not a capability result",
                      file=sys.stderr)
                raise
            source = "server-asked" if asked is not None else "backoff"
            print(f"producer: transient API failure, retrying in {wait:.1f}s "
                  f"({exc.__class__.__name__}, {source}); waited "
                  f"{_waited['seconds']:.0f}s of {PATIENCE_BUDGET:.0f}s",
                  file=sys.stderr)
            time.sleep(wait)
            _waited["seconds"] += wait
            delay = min(delay * 2, CAP_WAIT)


def _fail(msg: str) -> None:
    print(f"producer_openai: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    model = os.environ.get("RETICULI_MODEL", "gpt-5")
    out = os.environ["RETICULI_OUTPUT"]
    max_turns = int(os.environ.get("RETICULI_AGENT_TURNS", "40"))
    matrix = bool(os.environ.get("RETICULI_GATE_MATRIX"))

    # The recipe under whichever of its two names the room carries: new
    # claims are reticuli.toml, and claims sealed before the rename stay
    # readable as claim.toml -- the same two-name rule the kernel applies.
    recipe_name = "reticuli.toml" if os.path.isfile("reticuli.toml") else "claim.toml"
    with open(recipe_name, "rb") as f:
        recipe = tomllib.load(f)
    gate = next((s for s in recipe["step"] if s["kind"] == "gate"), None)
    inputs = recipe["claim"].get("inputs", [])
    supplied = [s["output"] for s in recipe["step"]
                if s["kind"] == "produce" and "from" in s]
    own = [s["output"] for s in recipe["step"]
           if s["kind"] == "produce" and "from" not in s]
    gate_cmd = gate["run"] if gate else ""
    gate_out = gate["output"] if gate else ""

    def present(p):
        return bool(p) and os.path.isfile(p)

    def claim_done():
        return present(gate_out) if gate_out else bool(own) and all(present(p) for p in own)

    if present(out) and claim_done():
        return 0

    task = f"""You are reconstructing the source files of a content-addressed claim so its \
check passes. There is NO reference implementation — infer the required API and semantics \
from the check files ALONE.

Your files to create (standard library only, correct over clever): {own}
The check/input files (already present — read them first, IN FULL): {inputs}
Files supplied by lower layers (read, import from, do NOT modify): {supplied}
The gate command is:  {gate_cmd}
It must succeed and create:  {gate_out}

A check file may be much longer than one read chunk ({CHUNK} chars). read_file takes an \
optional integer `offset`; keep reading at increasing offsets until you reach end-of-file. \
Read the ENTIRE check before designing — its header docstrings specify exact byte-level \
serializations you must reproduce.

Use the tools: read_file to inspect, write_file to create your files, run_gate to test. \
Iterate until run_gate reports success, then stop. Never modify the check/input files."""

    if matrix:
        task += """

IMPORTANT — run_gate runs the SAME gate command under every host condition the claim must \
hold in, and reports each separately ([bare] and [sandbox-inherited]). It reports success only \
when ALL of them pass. Behavior that depends on the host environment must be correct in each \
one: satisfying the environment you happen to be running in, while breaking another, is not a \
pass. When one environment fails, do not simply invert the behavior — find the rule that makes \
both correct at once."""

    if os.environ.get("RETICULI_DRY_PROMPT"):
        # Print the exact prompt this claim induces and stop: the one thing a
        # person reviewing an agent workflow most often asks to see, and the
        # documentation captures it from here rather than paraphrasing it.
        print(task)
        return 0

    tools = [
        {"type": "function", "function": {"name": "read_file",
            "description": f"Read a file in the claim directory. Returns up to {CHUNK} chars "
                           "from `offset` (default 0); an empty result means end-of-file.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "offset": {"type": "integer"}},
                "required": ["path"]}}},
        {"type": "function", "function": {"name": "write_file",
            "description": "Write (create/overwrite) one of your source files.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"]}}},
        {"type": "function", "function": {"name": "run_gate",
            "description": "Run the gate command; returns exit code and output.",
            "parameters": {"type": "object", "properties": {}}}},
    ]

    def _safe(path):
        full = os.path.realpath(path)
        here = os.path.realpath(".")
        if full != here and not full.startswith(here + os.sep):
            raise ValueError(f"path escapes the claim: {path}")
        return path

    def _do(name, args):
        # A malformed tool call is the MODEL's mistake to correct, not this
        # program's to die of. Witnessed 2026-10-15: a producer emitted
        # write_file carrying only `path`, and the KeyError killed the whole
        # attempt -- so a recoverable protocol slip was recorded as a
        # capability failure, and the model never learned what it got wrong.
        # Every argument is now checked and reported back in band.
        if not isinstance(args, dict):
            return f"error: {name} arguments must be a JSON object"
        if name in ("read_file", "write_file"):
            path = args.get("path")
            if not isinstance(path, str) or not path.strip():
                return f"error: {name} requires a string `path`"
        if name == "read_file":
            try:
                off = max(0, int(args.get("offset") or 0))
                with open(_safe(path), encoding="utf-8") as f:
                    return f.read()[off:off + CHUNK]
            except (OSError, ValueError, TypeError) as e:
                return f"error: {e}"
        if name == "write_file":
            content = args.get("content")
            if not isinstance(content, str):
                return ("error: write_file requires a string `content`; "
                        "send the whole file body in this one call")
            try:
                p = _safe(path)
            except ValueError as e:
                return f"error: {e}"
            if p in inputs:
                return "refused: cannot modify a check/input file"
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            return f"wrote {p} ({len(content)} bytes)"
        if name == "run_gate":
            # Through the kernel's jail -- see producers/_gate.py. This used
            # to be a bare `subprocess.run(shell=True)` with the caller's
            # whole environment, which meant a stranger's recipe ran against
            # the operator's home and the API key this session is holding.
            # The matrix legs live there too: a conforming claim must hold
            # both where a jail applies and where one does not, and success
            # requires every leg to pass.
            return _gate.run(gate_cmd, recipe, matrix=matrix)
        return "unknown tool"

    from openai import OpenAI  # lazy: import-safe even where the SDK is absent

    client = OpenAI()
    messages = [{"role": "user", "content": task}]
    tally = {"calls": 0, "tokens": 0, "input": 0, "output": 0, "cached": 0}
    for _ in range(max_turns):
        resp = _patient(lambda: client.chat.completions.create(
            model=model, messages=messages, tools=tools))
        _tally(tally, resp.usage)
        msg = resp.choices[0].message
        # A tool name the provider will not accept poisons the WHOLE attempt,
        # not just its own turn: the history is replayed on every subsequent
        # request, so one malformed name becomes a 400 on every turn after it.
        # Witnessed 2026-10-15 against a Bedrock-served model, whose refusal
        # ("toolUse.name failed to satisfy constraint") was nearly recorded as
        # the producer failing the layer. Offending calls are dropped from the
        # history, along with the replies that would orphan their ids, and the
        # model is told in band.
        dumped = msg.model_dump(exclude_none=True)
        calls = [tc for tc in (msg.tool_calls or [])
                 if _TOOL_NAME.match(tc.function.name or "")]
        rejected = len(msg.tool_calls or []) - len(calls)
        if rejected:
            if calls:
                dumped["tool_calls"] = [tc.model_dump(exclude_none=True)
                                        for tc in calls]
            else:
                dumped.pop("tool_calls", None)
        messages.append(dumped)
        if rejected:
            messages.append({"role": "user", "content": (
                f"{rejected} tool call(s) were dropped: a tool name must be "
                f"1-64 characters of letters, digits, underscore or hyphen. "
                f"Call read_file, write_file or run_gate by exactly those "
                f"names.")})
        if not calls:
            if not rejected:
                messages.append({"role": "user",
                                 "content": "Use write_file then run_gate; stop when it passes."})
            continue
        for tc in calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _do(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            if tc.function.name == "run_gate" and result.startswith("exit=0"):
                _report(tally)
                if present(out):
                    return 0
    _report(tally)
    if not claim_done():
        why = f"the gate never produced {gate_out}" if gate_out else "the claim is incomplete"
        _fail(f"agent finished but {why} (turn cap or gate never passed)")
    if not present(out):
        _fail(f"agent finished but did not write {out} (turn cap or gate never passed)")
    return 0


def _tally(tally: dict, usage) -> None:
    """Accumulate one response's usage.

    Input and output are counted SEPARATELY because they are not the same
    good: on a metered gateway output runs five to twenty times the price of
    input, and this producer's shape is input-heavy — it re-reads the same
    check files every turn. A total alone cannot be priced.

    Cached input is counted separately again, for the same reason: a provider
    that serves a re-read prompt from cache charges a tenth or less, and the
    cached share is most of the prompt by the end of a long gate loop.
    """
    tally["calls"] += 1
    if not usage:
        return

    def _n(value):
        return value if isinstance(value, int) else 0

    prompt = _n(getattr(usage, "prompt_tokens", 0))
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = _n(getattr(details, "cached_tokens", 0))
    tally["input"] += max(0, prompt - cached)
    tally["cached"] += min(cached, prompt)
    # reasoning tokens are billed as output and are already inside
    # completion_tokens, so they are not added again here
    tally["output"] += _n(getattr(usage, "completion_tokens", 0))
    tally["tokens"] += _n(getattr(usage, "total_tokens", 0)) or (
        prompt + _n(getattr(usage, "completion_tokens", 0)))


def _report(tally: dict) -> None:
    """Write the cost the kernel will ledger.

    The kernel accepts only `calls`, `tokens` and `usd`; anything else in
    this file is dropped. The split counts and the prices they were charged
    at are written anyway, as provenance — a dollar figure nobody can
    recompute is a number, not a measurement.

    RETICULI_PRICE is "input,output[,cache_read]" in usd per million tokens.
    With no price there is no usd key: an unpriced run reports tokens and
    stays honestly one rung down the cost ladder rather than guessing.
    """
    upath = os.environ.get("RETICULI_USAGE")
    if not upath or not tally.get("calls"):
        return
    rec = {"calls": tally["calls"], "tokens": tally["tokens"],
           "input_tokens": tally["input"], "output_tokens": tally["output"],
           "cached_input_tokens": tally["cached"]}
    price = os.environ.get("RETICULI_PRICE")
    if price:
        try:
            rates = [float(x) for x in price.split(",")]
        except ValueError:
            rates = []
        if len(rates) in (2, 3) and all(math.isfinite(r) and r >= 0
                                        for r in rates):
            # with no cache-read rate quoted, cached input is charged as
            # input: overstating a cost is a safer default than hiding one
            cache_rate = rates[2] if len(rates) == 3 else rates[0]
            usd = (tally["input"] * rates[0]
                   + tally["output"] * rates[1]
                   + tally["cached"] * cache_rate) / 1e6
            if math.isfinite(usd):
                rec["usd"] = round(usd, 6)
                rec["usd_rates"] = {"input": rates[0], "output": rates[1],
                                    "cache_read": cache_rate}
    with open(upath, "w", encoding="utf-8") as f:
        json.dump(rec, f, sort_keys=True)


if __name__ == "__main__":
    sys.exit(main())
