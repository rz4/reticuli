"""The routing table, and the one refusal boundary.

`main` is a thin table plus the shared boundary every verb's refusals pass
through: a `ClaimError` from any layer becomes one `ret: <verb>: <fact>` line,
an unknown verb gets the answer git gives (name the mistake, suggest the near
miss, exit 2), and an interrupt is an exit code rather than a traceback.
"""
import difflib
import sys

from .. import kernel
from . import parser
from . import verbs as _verbs
from .output import _err

#: verb -> handler. Everything that dispatches is in exactly one row.
ROUTES = {
    "init": _verbs._handle_init,
    "run": _verbs._handle_run,
    "status": _verbs._dispatch_status,
    "pack": _verbs._dispatch_pack,
    "pull": _verbs._handle_pull,
    "export": _verbs._handle_export,
    "import": _verbs._handle_import,
    "verify": _verbs._handle_verify,
    "audit": _verbs._dispatch_audit,
    "assess": _verbs._handle_assess,
    "rebuild": _verbs._handle_rebuild,
    "crosscheck": _verbs._dispatch_crosscheck,
    "record": _verbs._handle_record,
    "sign": _verbs._handle_sign,
    "hook": _verbs._handle_hook,
    "help": _verbs._handle_help,
    "completion": _verbs._handle_completion,
}


def _unknown(name: str) -> int:
    """Name the mistake, suggest the near miss, exit 2."""
    print(f"ret: '{name}' is not a ret command.", file=sys.stderr)
    near = difflib.get_close_matches(name, parser.verbs(), n=1, cutoff=0.6)
    if near:
        print(f"The most similar command is '{near[0]}'.", file=sys.stderr)
    print("See 'ret -h' for the fourteen verbs.", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    known = set(parser.verbs())
    if argv and not argv[0].startswith("-") and argv[0] not in known:
        return _unknown(argv[0])
    top, _sub = parser._parser()
    if not argv:
        top.print_help()
        return 2
    try:
        args = top.parse_args(argv)
    except SystemExit as leaving:
        return int(leaving.code or 0)
    name = parser.ALIASES.get(args.cmd, args.cmd)
    if getattr(args, "full_help", False):
        return parser._help_topic(name)
    handler = ROUTES.get(name)
    if handler is None:
        top.print_help()
        return 2
    try:
        return int(handler(args) or 0)
    except kernel.ClaimError as refusal:
        _err(name, str(refusal))
        return 1
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        _err(name, "interrupted")
        return 130
