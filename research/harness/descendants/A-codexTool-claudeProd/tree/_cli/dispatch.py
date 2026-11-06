"""The routing table, and the shared refusal boundary.

`main` is a thin table plus one boundary.  Every verb's own refusal arrives
here as a `ClaimError` and leaves as `ret: <verb>: <fact>` — one voice for
every refusal, from every layer, so a reader never has to learn which part of
the tool is talking.

An unknown verb gets the git answer: name the mistake, suggest the near miss,
exit 2.  A retired v1 spelling is simply unknown, which is what retirement
means.
"""
import sys

from .. import kernel
from . import handlers, output, parser, verbs as _verbs

#: verb -> handler.  A table rather than a switch, so the surface layer adds
#: no behaviour of its own: the handlers are the sub-claim beneath it.
TABLE = {
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


def main(argv=None) -> int:
    """Route one invocation, and own the refusal boundary."""
    raw = list(sys.argv[1:] if argv is None else argv)
    top, _table = parser._parser()
    if not raw or raw[0] in ("-h", "--help"):
        print(top.format_help(), end="")
        return 0
    if raw[0] == "--version":
        print(handlers._version_line())
        return 0

    verb = parser.ALIASES.get(raw[0], raw[0])
    if verb not in TABLE:
        output._warn_block(raw[0], _verbs.suggest(raw[0]).splitlines())
        return 2
    raw[0] = verb

    try:
        args = top.parse_args(raw)
    except SystemExit as exit_:
        # `-h` on a verb exits 0 after printing usage, so the code must be
        # read rather than coerced: `exit_.code or 2` turns that 0 into a 2.
        if exit_.code is None:
            return 2
        try:
            return int(exit_.code)
        except (TypeError, ValueError):
            return 2
    if getattr(args, "full_help", False):
        return parser._help_topic(verb)

    try:
        return TABLE[verb](args)
    except kernel.ClaimError as exc:
        return output._refusal(verb, exc, args)
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        output._err(verb, "interrupted")
        return 130
