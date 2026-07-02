"""Store layout — the §7 tree, shared by the local root and the S3 mirror (spec §7, CONTRACT).

    events/{lead}/{ts}_{type}_{uuid}.json      append-only fossil record — live observations ONLY
    snapshots/{lead}/{ts}.json                 materialized folds
    captures/{lead}/{ts}/...                   raw discourse (milestone 6)
    ingest/prices/{source}/{date}/...          frozen substrate
    ingest/holdings/{series_id}/{date}/...
    ingest/edgar/{date}/...
    ingest/etfdb/{date}/...                    (milestone 4)
    registry/funds/{series_id}.json            versioned fund registry objects
    baselines/{date}/...
    registry.sqlite                            WAL index — uploaded only via .backup snapshot
    backtest/                                  synthetic history — NEVER under events/ (CONTRACT)
"""

from __future__ import annotations

from pathlib import Path

from prospector.store.envelope import parse_ts


def ts_compact(ts: str) -> str:
    """ISO-8601 UTC -> filename-safe compact form: 2026-07-14T13:00:00Z -> 20260714T130000Z.
    (Colons are legal in S3 keys but hostile everywhere else; the envelope `ts` field itself
    stays full ISO.)"""
    dt = parse_ts(ts)
    return dt.strftime("%Y%m%dT%H%M%S") + "Z"


class StoreLayout:
    def __init__(self, root: Path, kind: str = "live"):
        """kind: 'live' or 'backtest'. Backtest separation is structural (spec §7):
        a live store may not sit under backtest/, and a backtest store must."""
        self.root = Path(root)
        self.kind = kind
        under_backtest = "backtest" in self.root.parts
        if kind == "live" and under_backtest:
            raise ValueError(
                f"live store root may not sit under backtest/: {self.root} "
                "(use backtest_run_root() + kind='backtest')")
        if kind == "backtest" and not under_backtest:
            raise ValueError(f"backtest store root must sit under backtest/: {self.root}")
        if kind not in ("live", "backtest"):
            raise ValueError(f"unknown store kind: {kind!r}")

    def registry_path(self) -> Path:
        return self.root / "registry.sqlite"

    def event_path(self, lead: str, ts: str, type: str, event_id: str) -> Path:
        return self.root / "events" / lead / f"{ts_compact(ts)}_{type}_{event_id}.json"

    def snapshot_path(self, lead: str, ts: str) -> Path:
        return self.root / "snapshots" / lead / f"{ts_compact(ts)}.json"

    def prices_path(self, source: str, date: str, name: str) -> Path:
        return self.root / "ingest" / "prices" / source / date / name

    def holdings_path(self, series_id: str, date: str, name: str) -> Path:
        return self.root / "ingest" / "holdings" / series_id / date / name

    def edgar_path(self, date: str, name: str) -> Path:
        return self.root / "ingest" / "edgar" / date / name

    def fund_path(self, series_id: str) -> Path:
        return self.root / "registry" / "funds" / f"{series_id}.json"

    def baselines_path(self, date: str, name: str) -> Path:
        return self.root / "baselines" / date / name

    def events_root(self) -> Path:
        return self.root / "events"

    def snapshots_root(self) -> Path:
        return self.root / "snapshots"


def backtest_run_root(live_root: Path, run_stamp: str) -> Path:
    """Root for a backtest run's own store: {live_root}/backtest/run_{stamp}/ — a whole separate
    tree (own events/, own registry.sqlite). Writing synthetic history under the live events/
    is impossible by construction, not by convention."""
    return Path(live_root) / "backtest" / f"run_{run_stamp}"
