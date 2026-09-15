"""An agentic OpenAI producer for v2 claims — the cross-vendor rebuilder.

Ported from reticuli-lab's scripts/producer_openai_agentic.py with two
changes: it reads the v2 recipe (claim.toml, [claim] keys), and read_file
takes an offset so the model can read checks larger than one chunk.

Runs INSIDE a claim directory (cwd = the room). Drives a bounded tool-use
loop: the model may read the room's files, write its generated outputs, and
run the gate until it passes or the turn cap is hit. Respects
OPENAI_BASE_URL. Env: RETICULI_MODEL (default gpt-5), RETICULI_OUTPUT (the
output this call must produce), RETICULI_AGENT_TURNS (default 40),
RETICULI_USAGE (ledger drop file), RETICULI_PRICE ("in,out" usd/Mtok).
"""
import json
import os
import subprocess
import sys
import tomllib

CHUNK = 20000


def _fail(msg: str) -> None:
    print(f"producer_openai: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    from openai import OpenAI  # lazy: import-safe even where the SDK is absent

    model = os.environ.get("RETICULI_MODEL", "gpt-5")
    out = os.environ["RETICULI_OUTPUT"]
    max_turns = int(os.environ.get("RETICULI_AGENT_TURNS", "40"))

    with open("claim.toml", "rb") as f:
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
            r = subprocess.run(gate_cmd, shell=True, capture_output=True, text=True, check=False)
            tail = (r.stdout + r.stderr)[-4000:]
            return f"exit={r.returncode}\n{tail}"
        return "unknown tool"

    client = OpenAI()
    messages = [{"role": "user", "content": task}]
    usage_tok = 0
    for _ in range(max_turns):
        resp = client.chat.completions.create(model=model, messages=messages, tools=tools)
        if resp.usage:
            usage_tok += resp.usage.total_tokens
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            messages.append({"role": "user",
                             "content": "Use write_file then run_gate; stop when it passes."})
            continue
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _do(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            if tc.function.name == "run_gate" and result.startswith("exit=0"):
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
