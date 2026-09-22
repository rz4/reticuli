"""cli-parser conformance gate — the argv grammar.

The parser registers exactly the fourteen porcelain verbs, the folded aliases,
and the plumbing; `verbs()` and the help agree; retired v1 verbs are gone;
completion is generated from the grammar so it cannot drift. Writes PARSER_OK.

    python3 criteria/parser_check.py
"""
import contextlib
import io
import os
import sys

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._cli import parser

RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate", "inspect",
           # retired 2026-09-22 -- folded into porcelain: seal -> pack --accept,
           # hooks -> init (wires the agent), tree -> status --tree,
           # claims -> status --claims.
           "seal", "hooks", "tree", "claims")




# ==== seam block for parser_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- _cli/parser.py: 10 seam names (2 value, 2 kind, 6 callable) ---
_SEAM__cli_parser_VALUES = {
    '_DESC': 'Reticuli records and reproduces software claims.\n\nAuthoring\n    init        initialize a workspace\n    run         run and observe a command\n    status      show work, claims, and unresolved inputs\n    pack        create a claim from a project\n\nComposition and transport\n    pull        add another claim as a dependency\n    export      write a portable claim archive\n    import      restore a claim archive\n\nVerification\n    verify      verify claim identity\n    audit       rerun acceptance criteria\n    assess      measure specification strength\n\nReconstruction\n    rebuild     rebuild an implementation from a claim\n    crosscheck  compare independent realizations\n\nEvidence\n    record      write an execution record\n    sign        authorize a claim or proof',
    '_EPILOG': "See 'ret <command> -h' for command usage.\nSee 'ret help <command>' for detailed help; 'ret help -a' lists everything,\nincluding accepted older spellings.",
}
_SEAM__cli_parser_KINDS = {'ALIASES': 'dict', '_FULL_HELP': 'dict'}
_SEAM__cli_parser_CALLABLES = ('_add_verbose_json', '_completion', '_help_all', '_help_topic', '_parser', 'verbs')

def _seam() -> None:
    from reticuli._cli import parser as _m__cli_parser
    for _n, _v in _SEAM__cli_parser_VALUES.items():
        assert getattr(_m__cli_parser, _n) == _v, f'_cli/parser.py seam {_n} changed'
    for _n in _SEAM__cli_parser_KINDS:
        assert hasattr(_m__cli_parser, _n), f'_cli/parser.py must export {_n}'
    for _n in _SEAM__cli_parser_CALLABLES:
        assert callable(getattr(_m__cli_parser, _n, None)), f'_cli/parser.py must export callable {_n}'


def battery() -> None:
    _seam()
    p, _ = parser._parser()
    got = set(parser.verbs())
    expected = set(parser.PORCELAIN) | set(parser.ALIASES) | {"hook", "help", "completion"}
    assert got == expected, f"parser/verbs disagree: {got ^ expected}"
    assert len(parser.PORCELAIN) == 14, f"fourteen porcelain verbs: {parser.PORCELAIN}"
    for gone in RETIRED:
        assert gone not in got, f"the v1 verb {gone!r} must stay retired"
    help_text = p.format_help()
    for group in ("Authoring", "Verification", "Reconstruction", "Evidence"):
        assert group in help_text, f"help group missing: {group}"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        parser._completion("bash")
    out = buf.getvalue()
    assert "crosscheck" in out and "complete -F" in out, "completion carries the grammar"


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("PARSER_OK", "w") as f:
            f.write("parser-ok\n")
    print("parser-ok")
