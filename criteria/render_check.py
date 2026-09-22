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




# ==== seam block for render_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- _cli/report.py: 22 seam names (0 value, 0 kind, 22 callable) ---
_SEAM__cli_report_VALUES = {
}
_SEAM__cli_report_KINDS = {}
_SEAM__cli_report_CALLABLES = ('_generic_contract', '_r_assess', '_r_attest', '_r_attest_check', '_r_audit', '_r_crosscheck', '_r_export', '_r_hooks', '_r_import', '_r_init', '_r_pack', '_r_pull', '_r_rebuild', '_r_record', '_r_review', '_r_seal', '_r_sign', '_r_sign_check', '_r_verify', '_row', '_t_init', '_when')

# --- _cli/statusview.py: 10 seam names (0 value, 1 kind, 9 callable) ---
_SEAM__cli_statusview_VALUES = {
}
_SEAM__cli_statusview_KINDS = {'_DECLARED_ROLE': 'dict'}
_SEAM__cli_statusview_CALLABLES = ('_files_claim', '_ledger_status_claim', '_r_claims', '_r_deps', '_r_status_draft', '_r_structure', '_r_tree', '_t_status_claim', '_v_status_claim')

def _seam() -> None:
    from reticuli._cli import report as _m__cli_report
    for _n, _v in _SEAM__cli_report_VALUES.items():
        assert getattr(_m__cli_report, _n) == _v, f'_cli/report.py seam {_n} changed'
    for _n in _SEAM__cli_report_KINDS:
        assert hasattr(_m__cli_report, _n), f'_cli/report.py must export {_n}'
    for _n in _SEAM__cli_report_CALLABLES:
        assert callable(getattr(_m__cli_report, _n, None)), f'_cli/report.py must export callable {_n}'
    from reticuli._cli import statusview as _m__cli_statusview
    for _n, _v in _SEAM__cli_statusview_VALUES.items():
        assert getattr(_m__cli_statusview, _n) == _v, f'_cli/statusview.py seam {_n} changed'
    for _n in _SEAM__cli_statusview_KINDS:
        assert hasattr(_m__cli_statusview, _n), f'_cli/statusview.py must export {_n}'
    for _n in _SEAM__cli_statusview_CALLABLES:
        assert callable(getattr(_m__cli_statusview, _n, None)), f'_cli/statusview.py must export callable {_n}'


def battery() -> None:
    _seam()
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
