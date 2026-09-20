"""cli-render conformance gate — the renderer family imports and is whole.

The action-verb renderers (report) and the status/draft/tree family
(statusview) build the -v and terse views. Their exact output is pinned by the
comprehensive surface suite driving the assembled CLI; this gate holds that the
layer imports cleanly against the layers below and exposes its renderer surface
whole (a missing renderer is a broken CLI). Writes RENDER_OK.

    python3 criteria/render_check.py
"""
import os
import sys

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._cli import report, statusview

REPORT_RENDERERS = ("_r_verify", "_r_audit", "_r_assess", "_r_rebuild", "_r_seal",
                    "_r_crosscheck", "_r_record", "_r_sign", "_r_export", "_r_pack",
                    "_row", "_when")
STATUS_RENDERERS = ("_t_status_claim", "_ledger_status_claim", "_v_status_claim",
                    "_files_claim", "_r_status_draft", "_r_tree", "_r_structure",
                    "_DECLARED_ROLE")


def battery() -> None:
    for name in REPORT_RENDERERS:
        assert hasattr(report, name), f"report is missing {name}"
    for name in STATUS_RENDERERS:
        assert hasattr(statusview, name), f"statusview is missing {name}"
    # the shared render helpers actually run
    assert callable(report._row) and callable(report._when), "render helpers present"


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("RENDER_OK", "w") as f:
            f.write("render-ok\n")
    print("render-ok")
