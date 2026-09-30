"""reticuli.cli: the CLI entrypoint (spec/layers.md, surface layer).

A thin seam: everything the fourteen-verb grammar needs lives in
`reticuli._cli.dispatch`; this module only re-exports what a rebuild is
pinned by (`main`) and what the acceptance check inspects directly
(`verbs`).
"""
from ._cli.dispatch import main, verbs

__all__ = ["main", "verbs"]
