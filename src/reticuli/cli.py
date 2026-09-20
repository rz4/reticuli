"""ret — the command line. Fourteen verbs, one concept each:

    observe work -> declare a claim -> test it -> reconstruct it
    -> compare realizations -> preserve evidence

Output has three levels. The default is one terse line (`packed 91c7…`,
`fresh 91c7…`, `earned 91c7… gates=9/9`); `-v` explains in fact sheets and
tables; `--json` is the machine envelope {command, ok, status, root, data}.
Exit codes are boring: 0 the operation and its predicate held, 1 the operation
ran but the predicate failed, 2 the invocation was invalid.

Folded spellings from the earlier grammar still dispatch (seal, hooks,
tree, claims, attest) but are aliases, listed only by `ret help -a`;
the fourteen are the grammar."""
from __future__ import annotations

from ._cli.dispatch import *
from ._cli.dispatch import (  # noqa: F401
    _dispatch_audit,
    _dispatch_crosscheck,
    _dispatch_pack,
    _dispatch_status,
)
from ._cli.handlers import *
from ._cli.handlers import (  # noqa: F401
    _PRODUCER_PASSTHROUGH,
    _PRODUCERS,
    _ensure,
    _expand_producer,
    _scan_workspace,
    _version_line,
)

# the command line, assembled: seven role modules re-exported so
# reticuli.cli.X stays the stable surface.
from ._cli.output import *
from ._cli.output import (  # noqa: F401
    _confirm,
    _err,
    _finish,
    _line,
    _Progress,
    _rel,
    _warn_block,
)
from ._cli.parser import *
from ._cli.parser import (  # noqa: F401
    _DESC,
    _EPILOG,
    _FULL_HELP,
    _add_verbose_json,
    _completion,
    _help_all,
    _help_topic,
    _parser,
)
from ._cli.report import *
from ._cli.report import (  # noqa: F401
    _generic_contract,
    _r_assess,
    _r_attest,
    _r_attest_check,
    _r_audit,
    _r_crosscheck,
    _r_export,
    _r_hooks,
    _r_import,
    _r_init,
    _r_pack,
    _r_pull,
    _r_rebuild,
    _r_record,
    _r_review,
    _r_seal,
    _r_sign,
    _r_sign_check,
    _r_verify,
    _row,
    _t_init,
    _when,
)
from ._cli.statusview import *
from ._cli.statusview import (  # noqa: F401
    _DECLARED_ROLE,
    _files_claim,
    _ledger_status_claim,
    _r_claims,
    _r_deps,
    _r_status_draft,
    _r_structure,
    _r_tree,
    _t_status_claim,
    _v_status_claim,
)
from ._cli.views import *
from ._cli.views import (  # noqa: F401
    _claim_view,
    _deciding_words,
    _gate_ok,
    _next_step,
    _phase,
    _read_residue,
    _signatures,
    _verdict,
    _verified,
)
