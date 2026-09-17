"""An agentic Anthropic producer for v2 claims — the other cross-vendor rebuilder.

A sibling of the OpenAI producer with the same room contract: it runs INSIDE
a claim directory (cwd = the room), drives a bounded tool-use loop — the
model may read the room's files, write its generated outputs, and run the
gate until it passes or the turn cap is hit — and reports what it cost
through RETICULI_USAGE.

Env: RETICULI_MODEL (default claude-opus-5), RETICULI_OUTPUT (the output this
call must produce), RETICULI_AGENT_TURNS (default 40), RETICULI_USAGE (ledger
drop file), RETICULI_PRICE ("in,out" usd/Mtok — claude-opus-5 is "5,25"),
RETICULI_GATE_MATRIX (run the gate under every host condition), and
ANTHROPIC_API_KEY, which must be handed in explicitly — the kernel scrubs the
environment, and docs/producers.md shows the wrapper pattern.
"""
import json
import os
import subprocess
import sys
import tomllib

CHUNK = 20000


def _patient(call, tries=5, wait=120):
    """The API is remote and sometimes briefly gone; a producer half-way
    through a kernel must outlive a transient outage. This retries only what
    the SDK's own retries gave up on, waits long enough for a gateway to
    recover, and re-raises when patience runs out -- so a blip costs minutes,
    never the session."""
    import time
    for attempt in range(tries):
        try:
            return call()
        except Exception as exc:
            if attempt == tries - 1:
                raise
            print(f"producer: transient API failure, retrying in {wait}s "
                  f"({exc.__class__.__name__})", file=sys.stderr)
            time.sleep(wait)


def _fail(msg: str) -> None:
    print(f"producer_anthropic: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    from anthropic import Anthropic  # lazy: import-safe where the SDK is absent

    model = os.environ.get("RETICULI_MODEL", "claude-opus-5")
    out = os.environ["RETICULI_OUTPUT"]
    max_turns = int(os.environ.get("RETICULI_AGENT_TURNS", "40"))
    matrix = bool(os.environ.get("RETICULI_GATE_MATRIX"))

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

    tools = [
        {"name": "read_file",
         "description": f"Read a file in the claim directory. Returns up to {CHUNK} chars "
                        "from `offset` (default 0); an empty result means end-of-file.",
         "input_schema": {"type": "object", "properties": {
             "path": {"type": "string"}, "offset": {"type": "integer"}},
             "required": ["path"]}},
        {"name": "write_file",
         "description": "Write (create/overwrite) one of your source files.",
         "input_schema": {"type": "object", "properties": {
             "path": {"type": "string"}, "content": {"type": "string"}},
             "required": ["path", "content"]}},
        {"name": "run_gate",
         "description": "Run the gate command; returns exit code and output.",
         "input_schema": {"type": "object", "properties": {}}},
    ]

    def _safe(path):
        full = os.path.realpath(path)
        here = os.path.realpath(".")
        if full != here and not full.startswith(here + os.sep):
            raise ValueError(f"path escapes the claim: {path}")
        return path

    def _do(name, args):
        if name == "read_file":
            try:
                off = max(0, int(args.get("offset") or 0))
                with open(_safe(args["path"]), encoding="utf-8") as f:
                    return f.read()[off:off + CHUNK]
            except (OSError, ValueError) as e:
                return f"error: {e}"
        if name == "write_file":
            p = _safe(args["path"])
            if p in inputs:
                return "refused: cannot modify a check/input file"
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(args["content"])
            return f"wrote {p} ({len(args['content'])} bytes)"
        if name == "run_gate":
            if not matrix:
                r = subprocess.run(gate_cmd, shell=True, capture_output=True,
                                   text=True, check=False)
                tail = (r.stdout + r.stderr)[-4000:]
                return f"exit={r.returncode}\n{tail}"
            worst, parts = 0, []
            for label, extra in (("bare", {}), ("sandbox-inherited", {"RETICULI_JAILED": "1"})):
                env = dict(os.environ, **extra)
                if not extra:
                    env.pop("RETICULI_JAILED", None)
                r = subprocess.run(gate_cmd, shell=True, capture_output=True,
                                   text=True, env=env, check=False)
                worst = worst or r.returncode
                parts.append(f"[{label}] exit={r.returncode}\n{(r.stdout + r.stderr)[-2000:]}")
            return f"exit={worst}\n" + "\n".join(parts)
        return "unknown tool"

    client = Anthropic()
    messages = [{"role": "user", "content": task}]
    usage_tok = 0
    for _ in range(max_turns):
        # Streaming, because a single write_file carrying a whole kernel can
        # be tens of thousands of output tokens. Thinking is left at the
        # model's default (adaptive on current models).
        def _turn():
            with client.messages.stream(model=model, max_tokens=64000,
                                        messages=messages, tools=tools) as stream:
                return stream.get_final_message()
        resp = _patient(_turn)
        if resp.usage:
            usage_tok += (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "refusal":
            _report(usage_tok)
            _fail("the model declined the request "
                  f"({getattr(resp.stop_details, 'category', None)})")
        if resp.stop_reason == "pause_turn":
            continue                      # resend with the paused turn last

        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            messages.append({"role": "user",
                             "content": "Use write_file then run_gate; stop when it passes."})
            continue
        results, passed = [], False
        for call in calls:
            result = _do(call.name, call.input or {})
            results.append({"type": "tool_result", "tool_use_id": call.id,
                            "content": result})
            if call.name == "run_gate" and result.startswith("exit=0"):
                passed = True
        messages.append({"role": "user", "content": results})
        if passed:
            _report(usage_tok)
            if present(out):
                return 0
    _report(usage_tok)
    if not claim_done():
        why = f"the gate never produced {gate_out}" if gate_out else "the claim is incomplete"
        _fail(f"agent finished but {why} (turn cap or gate never passed)")
    if not present(out):
        _fail(f"agent finished but did not write {out} (turn cap or gate never passed)")
    return 0


def _report(tokens: int) -> None:
    upath = os.environ.get("RETICULI_USAGE")
    if upath and tokens:
        rec = {"tokens": tokens}
        price = os.environ.get("RETICULI_PRICE")     # "in,out" usd/Mtok, optional
        try:
            if price:
                i, o = (float(x) for x in price.split(","))
                rec["usd"] = round(tokens / 1e6 * (i + o) / 2, 6)
        except ValueError:
            pass
        with open(upath, "w", encoding="utf-8") as f:
            json.dump(rec, f)


if __name__ == "__main__":
    sys.exit(main())
