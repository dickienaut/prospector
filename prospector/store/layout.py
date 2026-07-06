"""Store layout — the §7 tree, shared by the local root and the S3 mirror (spec §7, CONTRACT).

    events/{lead}/{ts}_{type}_{uuid}.json      append-only fossil record — live observations ONLY
    snapshots/{lead}/{ts}.json                 materialized folds
    captures/{lead}/{ts}/...                   raw discourse (milestone 6)
    ingest/prices/{source}/{date}/...          frozen substrate
    ingest/holdings/{series_id}/{date}/...
    ingest/prospectus/{series_id}/{accession}/...   frozen mandate text per filing (milestone 4)
    ingest/soi/{series_id}/{accession}/...          frozen industry-grouped Schedule of Investments (§4c resolver)
    ingest/edgar/{date}/...
    ingest/etfdb/{date}/...                    (milestone 4)
    registry/funds/{series_id}.json            versioned fund registry objects
    baselines/{date}/...
    runs/{date}_{run_id}.json                  per-tick operational run-log (milestone 5, §9g)
    registry.sqlite                            WAL index — uploaded only via .backup snapshot
    backtest/                                  synthetic history — NEVER under events/ (CONTRACT)
"""

from __future__ import annotations

from pathlib import Path

from prospector.store.envelope import parse_ts


def ts_compact(ts: str) -> str:
    """ISO-8601 UTC -> filename-safe compact form: 2026-07-14T13:00:00Z -> 20260714T130000Z.
    (Colons are legal in S3 keys but hostile everywhere else; the envelope `ts` field itself
    stays full ISO.)

    Sub-second precision is preserved (S2): a whole-second ts stays `…130000Z` (backward-compatible),
    but a ts carrying microseconds appends them (`…130000_123456Z`), so two instants in the SAME
    wall-clock second produce DISTINCT compact forms. Without this the runner's reactive policy could
    snapshot one lead twice in the same second (a state change), both would map to
    `snapshots/{lead}/{ts}.json`, and the second write would hit write_snapshot's divergence check ->
    SnapshotDivergenceError aborts the run. The form stays filename-safe (digits + `T`/`_`/`Z`, no colon)
    and one-way (never parsed back), so appending is lossless without changing the whole-second form."""
    dt = parse_ts(ts)
    base = dt.strftime("%Y%m%dT%H%M%S")
    if dt.microsecond:
        base += f"_{dt.microsecond:06d}"
    return base + "Z"


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

    def prospectus_path(self, series_id: str, accession: str, name: str) -> Path:
        # Keyed on the filing ACCESSION, not a pull-date (§7, rev9): the mandate-diff needs every
        # version kept immutably so it can diff the stated strategy across accessions — a blob per
        # accession is append-only by construction, never a mutable FundEntry field.
        return self.root / "ingest" / "prospectus" / series_id / accession / name

    def soi_path(self, series_id: str, accession: str, name: str) -> Path:
        # Keyed on the filing ACCESSION, like prospectus_path (§7): the industry-grouped Schedule of
        # Investments is frozen per accession so the derived sector concentration is a pure function of
        # the frozen bytes (extract-on-read, re-derivable by a later parser). The live fetch that writes
        # here is the M5 EDGAR-SOI-fetch slice (fetch-on-cadence); the read side is exercised now via the
        # hand-frozen fixtures. Test fixtures are NEVER refreshed by that fetch (offline-determinism).
        return self.root / "ingest" / "soi" / series_id / accession / name

    def edgar_path(self, date: str, name: str) -> Path:
        return self.root / "ingest" / "edgar" / date / name

    def fund_path(self, series_id: str) -> Path:
        return self.root / "registry" / "funds" / f"{series_id}.json"

    def baselines_path(self, date: str, name: str) -> Path:
        return self.root / "baselines" / date / name

    def runs_path(self, date: str, run_id: str) -> Path:
        # One run-log object per tick (spec §9g): operational telemetry, NOT a lead event. The
        # date prefix keeps a day's runs adjacent; the run_id makes the name unique within a day.
        # The runs/ tree is the truth; the `runs` index table (runner/runlog.py) is queryable over it.
        return self.root / "runs" / f"{date}_{run_id}.json"

    def events_root(self) -> Path:
        return self.root / "events"

    def runs_root(self) -> Path:
        return self.root / "runs"

    def snapshots_root(self) -> Path:
        return self.root / "snapshots"


def backtest_run_root(live_root: Path, run_stamp: str) -> Path:
    """Root for a backtest run's own store: {live_root}/backtest/run_{stamp}/ — a whole separate
    tree (own events/, own registry.sqlite). Writing synthetic history under the live events/
    is impossible by construction, not by convention."""
    return Path(live_root) / "backtest" / f"run_{run_stamp}"
