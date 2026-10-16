# `zeta/agents/watcher.py`

**The root watcher as an academy agent: a loop around reconcile.cycle.**

This file is deliberately thin. Everything the watcher decides lives in
reconcile.py as plain functions; what academy adds is the standing process --
an autonomous loop with state, and actions a person (or later, a peer agent)
can call on a running watcher through a handle. If academy goes away, the
judgment survives as `python3 -m agents --once`.

```python
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from academy.agent import Agent, action, loop

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents import reconcile


class RootWatcher(Agent):
    """Keeps zeta's derived state caught up with the repository root.

    `battery=False` by default in the standing loop: the mutant battery is
    one full gate run per mutant, and a watcher that silently starts half an
    hour of compute on a poll is a surprise. The loop still REPORTS coverage
    drift every cycle; closing it is one `reconcile_now(battery=True)` away,
    or a restart with battery on for an operator who wants it automatic.
    """

    def __init__(self, repo=".", interval=300.0, battery=False):
        super().__init__()
        self.repo = str(repo)
        self.interval = float(interval)
        self.battery = bool(battery)
        self.last = None
        self.cycles = 0

    def _run(self, battery):
        report = reconcile.cycle(self.repo, battery=battery)
        self.last = report
        self.cycles += 1
        return report

    @loop
    async def watch(self, shutdown: asyncio.Event) -> None:
        while not shutdown.is_set():
```

a thread, because reconcile does file IO and may run gates;
the event loop stays responsive to handle calls meanwhile

```python
            report = await asyncio.to_thread(self._run, self.battery)
            keyholder = [d for d in report["remaining"]
                         if d.get("fix") == "keyholder"]
            line = (f"watch: root {report['repo_root'][:12]} "
                    f"drifts={len(report['drifts'])} "
                    f"acted={len(report['actions'])} "
                    f"for-keyholder={len(keyholder)}")
            print(line, flush=True)
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    @action
    async def status(self) -> dict:
        """The last cycle's report, without running a new one."""
        return {"cycles": self.cycles, "last": self.last}

    @action
    async def reconcile_now(self, battery: bool = False) -> dict:
        """One cycle on demand -- the handle's way to close coverage drift."""
        return await asyncio.to_thread(self._run, battery)
```

---
*Woven from `zeta/agents/watcher.py` by `docs/weave.py`. The implementation is generated -- one member of the claim's equivalence class -- so this page is derived twice over: regenerate it, never edit it.*
