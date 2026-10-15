"""Run the root watcher.

    python3 -m agents --once             # one cycle, no middleware, print JSON
    python3 -m agents                    # standing watcher, Ctrl-C to stop
    python3 -m agents --battery          # standing watcher that also runs the
                                         # mutant battery when coverage drifts

Run from the zeta directory (or with zeta on sys.path). --once is the
no-dependency path: it exercises every decision the agent makes, which is
why it exists -- the middleware must stay removable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents import reconcile


async def _standing(repo, interval, battery):
    from concurrent.futures import ThreadPoolExecutor

    from academy.exchange.local import LocalExchangeFactory
    from academy.manager import Manager
    from agents.watcher import RootWatcher

    async with await Manager.from_exchange_factory(
            factory=LocalExchangeFactory(),
            executors=ThreadPoolExecutor(max_workers=2)) as manager:
        handle = await manager.launch(
            RootWatcher,
            kwargs={"repo": repo, "interval": interval, "battery": battery})
        print(f"root watcher up: repo={repo} interval={interval}s "
              f"battery={battery} (Ctrl-C stops it)", flush=True)
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            status = await handle.status()
            print(f"stopping after {status['cycles']} cycle(s)", flush=True)
            await manager.shutdown(handle, blocking=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--once", action="store_true",
                    help="one cycle, no middleware, print the report")
    ap.add_argument("--interval", type=float, default=300.0)
    ap.add_argument("--battery", action="store_true",
                    help="also run the mutant battery when coverage drifts")
    ap.add_argument("--no-battery", dest="battery", action="store_false")
    ap.set_defaults(battery=False)
    args = ap.parse_args()
    if args.once:
        report = reconcile.cycle(args.repo, battery=args.battery)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    try:
        asyncio.run(_standing(args.repo, args.interval, args.battery))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
