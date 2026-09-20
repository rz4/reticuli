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

RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate", "inspect")


def battery() -> None:
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
