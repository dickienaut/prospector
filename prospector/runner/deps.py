"""RunnerDeps — the injected seam bundle for one tick (spec §9, §9a).

Everything the runner touches beyond the pure sensors is injected here, so the whole tick runs
offline under the network guard: the store handles, the EDGAR client (its `fetch` closed over
fixtures in tests, real httpx in production; its `persist` pre-wired to `layout.edgar_path` so
every pull is frozen before parse, §3/§9a), the notifier, the already-loaded config + its hash,
the single `now`, and a monotonic clock used only for elapsed. `pros run` builds the live bundle;
tests build a fixture one. The runner holds nothing across ticks — statelessness is the whole
point (§9), so there is no state here that outlives the call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from prospector.ingest.edgar import EdgarClient
from prospector.runner.notify import Notifier
from prospector.store.event_store import EventStore
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry


@dataclass
class RunnerDeps:
    layout: StoreLayout
    registry: Registry
    event_store: EventStore          # the base store; the runner wraps it to tally event types (§9g)
    edgar_client: EdgarClient        # persist pre-wired to layout.edgar_path (freeze-before-parse, §3)
    notifier: Notifier
    cfg: dict                        # loaded by the caller; the runner checks its honesty first (§9)
    cfg_hash: str                    # sha256 of canonical_json(cfg) — the config-honesty comparand
    now: str                         # ISO-8601 UTC; ALL events this tick share it (determinism, §9)
    run_id: str
    monotonic: Callable[[], float]   # elapsed only — NEVER a record time (record times are `now`)
