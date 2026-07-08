"""Run-log — operational telemetry for one tick (spec §9g).

Every run writes ONE run-log object under `runs/{date}_{run_id}.json` and indexes it in the `runs`
table. It records what ran, what changed, and how long it took. It is emphatically NOT an event on
a lead: it never folds into lead state, never drives a push, and is excluded from the statelessness
property (two cold runs produce identical EVENTS; their run-logs differ by run_id/elapsed). §9g:
"operational telemetry — not an event on a lead."

The `runs` table is owned HERE on the shared registry connection — exactly like `resolution_queue`
(resolution.py) and `funds` (fund_registry.py) — because registry.py's vendored DDL is frozen
(CLAUDE.md: keep the provenance, do not edit the ported schema). The run-log FILES under runs/ are
the truth; this table is the queryable index the dashboard reads (build-order step 5). A
`pros store reindex` does not rebuild it — like the other module-owned working tables, the files
survive and the index is disposable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from prospector.primitives.atomic import write_json_atomic
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    date         TEXT NOT NULL,
    config_hash  TEXT,
    pushed       INTEGER NOT NULL,
    fault_count  INTEGER NOT NULL,
    file_path    TEXT NOT NULL,
    sha256       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(date, run_id);
"""


def _ensure_table(registry: Registry) -> None:
    """Create the runs table on the shared connection (idempotent). Kept out of registry.py so its
    vendored DDL stays frozen — the resolution_queue / funds precedent."""
    if getattr(registry, "readonly", False):
        return  # N1: a read-only viewer (recent_runs on the dashboard) never issues DDL/commit
    registry.conn.executescript(_DDL)
    registry.conn.commit()


@dataclass
class RunLog:
    """One tick's telemetry. Plain JSON-serializable fields only — it is written by
    `write_json_atomic` (canonical JSON) and read back by the dashboard verbatim."""

    run_id: str
    ts: str                                     # the tick's single `now` (ISO-8601 UTC)
    date: str
    config_hash: str | None = None
    config_changed: bool = False
    elapsed_seconds: float | None = None
    ingests: dict = field(default_factory=dict)        # source -> 'ran' | 'skipped' | 'fault'
    sensors: dict = field(default_factory=dict)        # name   -> 'ran' | 'seeded' | 'slot' | 'fault'
    event_counts: dict = field(default_factory=dict)   # event type -> count emitted this tick
    faults: list = field(default_factory=list)         # [{subsystem, message}]
    changed_leads: dict = field(default_factory=dict)  # lead -> [changed {status,shadow,verdict} fields]
    pushed: bool = False
    fatal: bool = False                                # a run-fatal exception still wrote this log + pushed

    def to_dict(self) -> dict:
        return asdict(self)


def write_run_log(layout: StoreLayout, registry: Registry, runlog: RunLog) -> Path:
    """Freeze the run-log under runs/ and index it in the `runs` table (INSERT OR IGNORE — a
    re-run with the same run_id is idempotent on the index; the file is the truth)."""
    _ensure_table(registry)
    path = layout.runs_path(runlog.date, runlog.run_id)
    sha256 = write_json_atomic(path, runlog.to_dict())
    registry.conn.execute(
        "INSERT OR IGNORE INTO runs "
        "(run_id, ts, date, config_hash, pushed, fault_count, file_path, sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (runlog.run_id, runlog.ts, runlog.date, runlog.config_hash, int(runlog.pushed),
         len(runlog.faults), path.relative_to(layout.root).as_posix(), sha256))
    registry.conn.commit()
    return path


def recent_runs(registry: Registry, limit: int = 20) -> list:
    """Most-recent runs first — the dashboard's run-history panel (build-order step 5)."""
    _ensure_table(registry)
    return registry.conn.execute(
        "SELECT * FROM runs ORDER BY ts DESC, run_id DESC LIMIT ?", (limit,)).fetchall()
