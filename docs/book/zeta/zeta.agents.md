# `zeta/agents/__init__.py`

**Agents: zeta's outer shell, standing to zeta as zeta stands to reticuli.**

An agent here is a long-lived process that keeps zeta's derived state caught
up with the repository and REPORTS what it cannot decide. The boundary is the
same one zeta itself lives under, one level out:

  - an agent rewrites only DERIVED files: population registries, coverage
    reports, and its own observation log. Each is recomputable from the
    repository at any time; losing one loses bookkeeping, never evidence.
  - an agent never appends to the promotion ledger, never mints a queue
    entry, and never touches a pinned file. Proposing is the sources' job,
    promoting is the keyholder's, and recording a promotion is part of
    promoting.

Nothing trusted may depend on this package: the criteria must keep passing
with zeta/agents deleted. Agents run on academy-py (Globus Labs' middleware
for stateful agents on federated infrastructure), but the judgment lives in
plain functions that import nothing from it, so every decision is testable
without an event loop and the middleware stays what it is -- a transport.

---
*Woven from `zeta/agents/__init__.py` by `docs/weave.py`. The implementation is generated -- one member of the claim's equivalence class -- so this page is derived twice over: regenerate it, never edit it.*
