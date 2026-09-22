"""ret command line — the dispatch layer: the thin routing table and the shared refusal/signal boundary. The verb handlers live in _cli/verbs.py; this looks one up and calls it, and turns a raised ClaimError into the --json refusal envelope or a stderr line."""
from __future__ import annotations

import json
import os
import sys

from .. import kernel, render
from ..render import paint
from .handlers import _version_line
from .parser import _FULL_HELP, ALIASES, _help_topic, _parser
from .verbs import (
    _dispatch_audit,
    _dispatch_crosscheck,
    _dispatch_pack,
    _dispatch_status,
    _handle_assess,
    _handle_attest,
    _handle_completion,
    _handle_export,
    _handle_help,
    _handle_hook,
    _handle_import,
    _handle_init,
    _handle_pull,
    _handle_rebuild,
    _handle_record,
    _handle_run,
    _handle_sign,
    _handle_verify,
)

# the verb switch as a table: a verb (and its aliases) maps to its handler
TABLE = {
    "help": _handle_help, "init": _handle_init, "completion": _handle_completion,
    "hook": _handle_hook, "run": _handle_run,
    "pack": _dispatch_pack,
    "verify": _handle_verify, "audit": _dispatch_audit,
    "status": _dispatch_status,
    "assess": _handle_assess, "rebuild": _handle_rebuild,
    "crosscheck": _dispatch_crosscheck, "pull": _handle_pull,
    "attest": _handle_attest, "sign": _handle_sign, "export": _handle_export,
    "record": _handle_record, "import": _handle_import,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--version", "-V"):
        print(_version_line())
        return 0
    if not argv:
        # bare `ret`: show the command map, the way `git` does — the classic
        # first move should teach the verbs, not print an argparse error with
        # nothing to act on.
        p, _ = _parser()
        print(p.format_help())
        return 0
    # `-h` is concise usage (argparse); `--help` and `ret help` are the fuller
    # account — the conventional two-level help of mature Unix tools.
    if "--help" in argv:
        head = argv[0] if argv and not argv[0].startswith("-") else None
        if head and (head in _FULL_HELP or head in ALIASES or head == "hook"):
            return _help_topic(head)
        p, _ = _parser()
        print(p.format_help())
        return 0
    p, choices = _parser()
    if argv and not argv[0].startswith("-") and argv[0] not in choices:
        # git-shaped: name the mistake, suggest the near misses, exit 2
        import difflib
        close = difflib.get_close_matches(
            argv[0], sorted(set(choices) - {"hook"}), n=3, cutoff=0.6)
        print(f"ret: {argv[0]!r} is not a ret command. See 'ret -h'.",
              file=sys.stderr)
        if close:
            render.init_color(None)
            print(paint("hint: the most similar "
                        + ("commands are: " if len(close) > 1 else "command is: ")
                        + ", ".join(close), "hint", stderr=True), file=sys.stderr)
        return 2
    args = p.parse_args(argv)
    render.init_color(getattr(args, "color", None))
    render.FULL_HASHES = bool(getattr(args, "verbose", False))
    j = getattr(args, "json", False)
    handler = TABLE.get(args.cmd)
    if handler is None:
        return 2
    try:
        return handler(args)
    except kernel.ClaimError as e:
        # one voice for every refusal: `ret: <verb>: <fact>`, never doubled
        # when the layer below already named the verb
        msg = str(e)
        if msg.startswith(f"{args.cmd}: "):
            msg = msg[len(args.cmd) + 2:]
        if j:
            # the envelope holds on the refusal path too: ok:false on stdout,
            # stderr empty, so `ret <verb> --json | jq` never chokes on an empty
            # stdout for the "is this even a claim?" refusals automation hits
            # first. A `hint:` line, if the fact carried one, rides under data.
            fact, _, hint = msg.partition("\nhint:")
            data = {"error": fact.strip()}
            if hint.strip():
                data["hint"] = hint.strip()
            print(json.dumps({"command": args.cmd, "ok": False,
                              "status": "error", "root": None, "data": data},
                             indent=2, sort_keys=True))
        else:
            print(f"ret: {args.cmd}: {msg}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:               # a grown tool dies quietly: 128+SIGINT
        print(file=sys.stderr)
        return 130
    except BrokenPipeError:                 # `ret … | head`: the reader left; not an error
        try:
            # silence the interpreter's own flush at exit
            sys.stdout = open(os.devnull, "w")   # noqa: SIM115
        except OSError:
            pass
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
