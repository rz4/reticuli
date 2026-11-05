"""The routing table, and the refusal boundary around it.

`main` is deliberately thin: a table from verb to handler, plus the one
place a refusal becomes the one-voice line. Keeping the hub thin is what
let the verb handlers move into their own claim; keeping the boundary here
is what makes "every refusal looks the same" a property of the surface
rather than a habit of each handler.

An UNKNOWN verb gets the answer git gives: name the mistake, suggest the
near miss, exit 2. The retired metaphor vocabulary lands there too, which
is exactly right -- it is not a ret command any more.
"""
import difflib
import os
import sys

from .. import kernel
from . import handlers
from . import output
from . import parser as parser_mod
from . import verbs as verb_handlers

TABLE = {
    "init": verb_handlers._handle_init,
    "run": verb_handlers._handle_run,
    "status": verb_handlers._dispatch_status,
    "pack": verb_handlers._dispatch_pack,
    "pull": verb_handlers._handle_pull,
    "export": verb_handlers._handle_export,
    "import": verb_handlers._handle_import,
    "verify": verb_handlers._handle_verify,
    "audit": verb_handlers._dispatch_audit,
    "assess": verb_handlers._handle_assess,
    "rebuild": verb_handlers._handle_rebuild,
    "crosscheck": verb_handlers._dispatch_crosscheck,
    "record": verb_handlers._handle_record,
    "sign": verb_handlers._handle_sign,
    "hook": verb_handlers._handle_hook,
    "help": verb_handlers._handle_help,
    "completion": verb_handlers._handle_completion,
}


def _unknown(name: str) -> int:
    near = difflib.get_close_matches(name, parser_mod.verbs(), n=1,
                                     cutoff=0.5)
    said = f"ret: {name!r} is not a ret command."
    if near:
        said += f" Did you mean {near[0]!r}?"
    print(said, file=sys.stderr)
    print("See 'ret -h' for the fourteen verbs, or 'ret help -a' for "
          "everything.", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        top, _sub = parser_mod._parser()
        top.print_help()
        return 0
    if argv[0] in ("--version", "-V"):
        print(handlers._version_line())
        return 0
    if argv[0] in ("-h", "--help"):
        top, _sub = parser_mod._parser()
        top.print_help()
        return 0
    if argv[0] in parser_mod.ALIASES:
        argv[0] = parser_mod.ALIASES[argv[0]]
    if argv[0] not in TABLE:
        return _unknown(argv[0])
    # `--help` on a verb is the FULLER account; `-h` stays concise usage.
    if "--help" in argv[1:]:
        return parser_mod._help_topic(argv[0]) or 0

    top, _sub = parser_mod._parser()
    try:
        args = top.parse_args(argv)
    except SystemExit as leaving:
        return int(leaving.code or 0)
    if getattr(args, "color", None) and args.color != "auto":
        os.environ["RETICULI_COLOR"] = args.color
    handler = TABLE.get(args.cmd)
    if handler is None:
        return _unknown(str(args.cmd))
    try:
        return int(handler(args) or 0)
    except kernel.ClaimError as exc:
        return output._refuse(str(args.cmd), str(exc), args)
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        print("ret: interrupted", file=sys.stderr)
        return 130


def verbs() -> list:
    return parser_mod.verbs()
