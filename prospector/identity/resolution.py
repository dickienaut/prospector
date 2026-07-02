"""Failed-resolution state machine — retry, then the manual queue (spec §2 CONTRACT; §4c).

EDGAR's ticker→series mapping is messy, disproportionately for the brand-new and weird funds —
exactly the targets. A failed resolution must never silently drop the fund: the failure lands
in the fossil record (`resolution.failed` on `_system`), auto-retries run daily for
`identity.retry_days`, and an unresolved ticker then enters the manual queue — surfaced on the
dashboard and in the heartbeat, resolved by a human via `pros identity resolve` (spec §8c).

The `resolution_queue` table is a WORKING INDEX owned here on the shared registry connection
(registry.py's DDL is frozen — vendored provenance, CLAUDE.md); the EVENTS are the truth. Every
transition that matters is an event: the first failure, the escalation to the manual queue, the
resolution (`identity.resolved`, method auto|manual), and the completing `launch` whose payload
carries the ORIGINAL `detected_at` plus the `launch.unverified` back-reference.

Lag integrity (CONTRACT §4c): all lag math uses the launch payload's `detected_at`, never
resolution time — a fund that takes nine days to resolve must not get a launch timestamp nine
days late. `launch_lag` reads ONLY that field and raises KeyError rather than fall back.

Routing the completing `launch` onto overlapping live leads is milestone 4; emitting it onto
`_system` here keeps the record whole in the meantime.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from prospector.ingest.edgar import (PROSPECTUS_FORMS, EdgarClient, Resolution,
                                     resolve_ticker)
from prospector.store.envelope import SYSTEM_LEAD, parse_ts
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import (SERIES_ID_RE, FundEntry, FundRegistry,
                                            IdentityError)
from prospector.store.registry import Registry

__all__ = ["VerificationError", "ResolutionMachine", "launch_lag"]

_DDL = """
CREATE TABLE IF NOT EXISTS resolution_queue (
    ticker              TEXT PRIMARY KEY,
    status              TEXT NOT NULL CHECK(status IN ('retrying','manual','resolved')),
    first_failed_at     TEXT NOT NULL,
    last_attempt_at     TEXT NOT NULL,
    attempts            INTEGER NOT NULL DEFAULT 1,
    detected_at         TEXT,
    unverified_event_id TEXT,
    resolved_series_id  TEXT,
    note                TEXT
);
"""


def _utc_now() -> str:
    """Default clock — all record times are UTC (spec §9)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class VerificationError(ValueError):
    """Raised when a manual resolution fails its EDGAR verify — the series is absent from the
    MF ticker map, the registrant lacks a prospectus-family filing, or EDGAR errored. There is
    no bypass flag in v1 (spec §2 CONTRACT): an unverifiable identity never reaches the
    registry."""


def launch_lag(structural_ts: str, launch_payload: Mapping) -> timedelta:
    """Cross-stream lag T(structural) → T(launch): the launch's `detected_at` MINUS the
    structural event's ts (spec §4c, §10 test 5 bonus datum) — positive when the launch was
    detected after the structural firing, the packaging-follows-structure direction.

    Reads ONLY `launch_payload['detected_at']` (lag-integrity CONTRACT §4c): a missing key
    raises KeyError rather than falling back to any other timestamp, because resolution time
    must never masquerade as the launch datum.
    """
    return parse_ts(launch_payload["detected_at"]) - parse_ts(structural_ts)


class ResolutionMachine:
    def __init__(self, registry: Registry, event_store: EventStore,
                 fund_registry: FundRegistry | None, edgar_client: EdgarClient | None,
                 retry_days: int = 10, clock: Callable[[], str] | None = None):
        """`retry_days` is DEFAULT `identity.retry_days` (spec §2). `clock` is a zero-arg
        callable returning the current ISO-8601 UTC string. `fund_registry`/`edgar_client` may
        be None for read-only surfaces (manual_queue); the write paths require both."""
        self.registry = registry
        self.event_store = event_store
        self.fund_registry = fund_registry
        self.edgar_client = edgar_client
        self.retry_days = retry_days
        self._clock = clock if clock is not None else _utc_now
        # Owns its table on the shared connection; registry.py's DDL stays frozen.
        registry.conn.executescript(_DDL)
        registry.conn.commit()

    # -- failure intake -----------------------------------------------------

    def record_failure(self, ticker: str, reason: str, detail: str,
                       detected_at: str | None = None,
                       unverified_event_id: str | None = None) -> None:
        """A failed resolution enters the record and the queue — countable, never silent
        (spec §2 CONTRACT): `resolution.failed` onto `_system`, then the queue row goes (back)
        to 'retrying'. The first failure's `first_failed_at` is kept — the retry window counts
        from it — and so are the original `detected_at`/`unverified_event_id`, the two-phase
        launch's lag datum and back-reference (§4c)."""
        ticker = ticker.upper()
        now = self._clock()
        self.event_store.append({
            "ts": now, "lead": SYSTEM_LEAD, "type": "resolution.failed",
            "payload": {"ticker": ticker, "reason": reason, "detail": detail},
            "schema": 1})
        self.registry.conn.execute(
            """INSERT INTO resolution_queue
                 (ticker, status, first_failed_at, last_attempt_at, attempts,
                  detected_at, unverified_event_id)
               VALUES (?, 'retrying', ?, ?, 1, ?, ?)
               ON CONFLICT(ticker) DO UPDATE SET
                 status = 'retrying',
                 last_attempt_at = excluded.last_attempt_at,
                 attempts = attempts + 1,
                 detected_at = COALESCE(resolution_queue.detected_at, excluded.detected_at),
                 unverified_event_id = COALESCE(resolution_queue.unverified_event_id,
                                                excluded.unverified_event_id)""",
            (ticker, now, now, detected_at, unverified_event_id))
        self.registry.conn.commit()

    # -- daily retries ------------------------------------------------------

    def run_retries(self) -> dict[str, list[str]]:
        """One retry pass over every 'retrying' row (the runner calls this daily, spec §9) —
        EDGAR series indexing lags new funds, so most failures self-heal (§2). Success
        resolves the row (entry + events + completing launch); failure bumps the attempt
        count, and past `retry_days` days since `first_failed_at` the ticker escalates to the
        manual queue — the escalation is itself in the record (`resolution.failed`, stage
        'manual_queue'). Returns {'resolved', 'retrying', 'escalated'} ticker lists."""
        out: dict[str, list[str]] = {"resolved": [], "retrying": [], "escalated": []}
        rows = self.registry.conn.execute(
            "SELECT * FROM resolution_queue WHERE status = 'retrying' "
            "ORDER BY first_failed_at, ticker").fetchall()
        for row in rows:
            result = resolve_ticker(row["ticker"], self.edgar_client)
            now = self._clock()
            if isinstance(result, Resolution):
                self._complete(row, result, method="auto", now=now)
                out["resolved"].append(row["ticker"])
                continue
            overdue = (parse_ts(now) - parse_ts(row["first_failed_at"])
                       > timedelta(days=self.retry_days))
            self.registry.conn.execute(
                "UPDATE resolution_queue SET status = ?, attempts = attempts + 1, "
                "last_attempt_at = ? WHERE ticker = ?",
                ("manual" if overdue else "retrying", now, row["ticker"]))
            self.registry.conn.commit()
            if overdue:
                self.event_store.append({
                    "ts": now, "lead": SYSTEM_LEAD, "type": "resolution.failed",
                    "payload": {"ticker": row["ticker"], "stage": "manual_queue"},
                    "schema": 1})
                out["escalated"].append(row["ticker"])
            else:
                out["retrying"].append(row["ticker"])
        return out

    # -- manual resolution (the human path, spec §8c) -------------------------

    def resolve_manual(self, ticker: str, series_id: str, note: str | None = None) -> FundEntry:
        """`pros identity resolve <ticker> --series-id S######`: validate the id's format,
        VERIFY it against EDGAR (the series must exist in the MF ticker map and its registrant
        must have a prospectus-family filing — no bypass flag in v1), then complete exactly as
        an auto-resolution would, with `method: 'manual'` in `identity.resolved`."""
        ticker = ticker.upper()
        if not isinstance(series_id, str) or not SERIES_ID_RE.match(series_id):
            raise IdentityError(
                f"manual resolution requires a well-formed series id (S######), "
                f"got {series_id!r} — a bare ticker is rejected at the write path")
        resolution = self._resolve_series(series_id, ticker)
        row = self.queue_row(ticker)
        return self._complete(row, resolution, method="manual", now=self._clock(), note=note)

    def _resolve_series(self, series_id: str, ticker: str) -> Resolution:
        """Resolve-by-series: the §2 flow keyed on series id instead of symbol, for the manual
        path's EDGAR verify. Raises VerificationError on any failure — unlike resolve_ticker's
        typed values, a manual resolve has a human on the line to hand the error to."""
        try:
            mf = self.edgar_client.mf_tickers()
            idx = {f: i for i, f in enumerate(mf["fields"])}
            rows = [r for r in mf["data"] if str(r[idx["seriesId"]]) == series_id]
        except Exception as e:
            raise VerificationError(f"EDGAR verify of {series_id}: mf ticker map: {e}") from e
        if not rows:
            raise VerificationError(
                f"{series_id} absent from the EDGAR MF ticker map — cannot verify "
                "(no bypass in v1)")
        cik = int(rows[0][idx["cik"]])
        class_ids: list[str] = []
        for r in rows:
            class_id = str(r[idx["classId"]])
            if class_id not in class_ids:
                class_ids.append(class_id)
        try:
            subs = self.edgar_client.submissions(cik)
            name = str(subs["name"])
            recent = subs["filings"]["recent"]
            forms, dates = recent["form"], recent["filingDate"]
            # Most recent prospectus-family filing (same rule as resolve_ticker).
            best: int | None = None
            for i, form in enumerate(forms):
                if form in PROSPECTUS_FORMS and (best is None or dates[i] > dates[best]):
                    best = i
        except Exception as e:
            raise VerificationError(
                f"EDGAR verify of {series_id}: submissions CIK{cik:010d}: {e}") from e
        if best is None:
            raise VerificationError(
                f"CIK{cik:010d} has no {'/'.join(PROSPECTUS_FORMS)} filing — "
                f"cannot verify {series_id}")
        return Resolution(series_id=series_id, class_ids=class_ids, cik=cik, name=name,
                          prospectus_accession=str(recent["accessionNumber"][best]),
                          ticker=ticker)

    # -- completion (shared by auto and manual) --------------------------------

    def build_entry(self, resolution: Resolution, *,
                    detected_at: str | None = None,
                    category_draft: str | None = None,
                    name: str | None = None,
                    now: str | None = None) -> FundEntry:
        """A FundEntry from a successful §2 resolution. `concentration_industries` is empty at
        this stage — the prospectus parse that fills it is v-later; `holdings_source` is
        'issuer_daily' (§3). `first_seen` is the ORIGINAL `detected_at` when the two-phase
        launch supplied one (§4c), else now; `verified_at` is now. `name` defaults to the
        registrant/trust name off the wire — callers holding a better display name pass it.
        `category_draft` rides through verbatim: etfdb's steering label, stored, never read
        back by this module (spec §10 test 1)."""
        now = now if now is not None else self._clock()
        return FundEntry(
            series_id=resolution.series_id,
            class_ids=list(resolution.class_ids),
            cik=resolution.cik,
            ticker_current=resolution.ticker.upper(),
            name=name if name is not None else resolution.name,
            issuer=resolution.name,
            category_draft=category_draft,
            concentration_industries=[],
            prospectus_accession=resolution.prospectus_accession,
            holdings_source="issuer_daily",
            first_seen=detected_at if detected_at is not None else now,
            verified_at=now)

    def _complete(self, row: sqlite3.Row | None, resolution: Resolution, *,
                  method: str, now: str, note: str | None = None) -> FundEntry:
        """Registry entry -> `identity.resolved` -> the completing `launch` (when the two-phase
        launch left a datum to complete) -> queue row 'resolved'. The launch payload carries
        the ORIGINAL `detected_at` and the `launch.unverified` back-reference (lag integrity,
        CONTRACT §4c); it lands on `_system` — lead routing is milestone 4."""
        detected_at = row["detected_at"] if row is not None else None
        unverified_ref = row["unverified_event_id"] if row is not None else None
        entry = self.build_entry(resolution, detected_at=detected_at, now=now)
        self.fund_registry.upsert(entry)
        self.event_store.append({
            "ts": now, "lead": SYSTEM_LEAD, "type": "identity.resolved",
            "payload": {"ticker": entry.ticker_current, "series_id": entry.series_id,
                        "method": method},
            "schema": 1})
        if detected_at is not None or unverified_ref is not None:
            self.event_store.append({
                "ts": now, "lead": SYSTEM_LEAD, "type": "launch",
                "payload": {"series_id": entry.series_id, "ticker": entry.ticker_current,
                            "name": entry.name,
                            "category_draft": None,  # steering label unknown here, never trusted
                            "concentration_industries": [],  # prospectus parse is v-later
                            "detected_at": detected_at,
                            "unverified_ref": unverified_ref},
                "schema": 1})
        if row is not None:
            self.registry.conn.execute(
                "UPDATE resolution_queue SET status = 'resolved', last_attempt_at = ?, "
                "resolved_series_id = ?, note = COALESCE(?, note) WHERE ticker = ?",
                (now, entry.series_id, note, row["ticker"]))
            self.registry.conn.commit()
        return entry

    # -- read surfaces ---------------------------------------------------------

    def manual_queue(self) -> list[sqlite3.Row]:
        """Rows awaiting a human — the dashboard panel and the heartbeat line (spec §2, §8)."""
        return self.registry.conn.execute(
            "SELECT * FROM resolution_queue WHERE status = 'manual' "
            "ORDER BY first_failed_at, ticker").fetchall()

    def queue_row(self, ticker: str) -> sqlite3.Row | None:
        return self.registry.conn.execute(
            "SELECT * FROM resolution_queue WHERE ticker = ?", (ticker.upper(),)).fetchone()
