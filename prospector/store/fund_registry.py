"""Fund registry — the write-path enforcement point of the HECO rule (spec §2, CONTRACT).

The registry key is the SEC series ID (S######) with CIK and class IDs attached; tickers are
display-only attributes. The write path REQUIRES a well-formed series id: a bare ticker — the
HECO case, ticker reuse in the wild — raises IdentityError before anything is written, so
nothing downstream (no lead, no baseline) can ever anchor to a ticker.

Registry objects are versioned files under registry/funds/{series_id}.json (S3 versioning
preserves the history once mirrored, spec §7); the `funds` SQLite table is the queryable index
over them, owned HERE on the shared connection because registry.py's DDL is frozen (vendored
provenance, CLAUDE.md). Every upsert also emits `registry.updated` onto `_system` with a change
summary, so the fossil record carries the registry's evolution (spec §2/§5).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable

from prospector.primitives.atomic import write_json_atomic
from prospector.store.envelope import SYSTEM_LEAD, canonical_json
from prospector.store.event_store import EventStore
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

__all__ = ["SERIES_ID_RE", "CLASS_ID_RE", "IdentityError", "FundEntry", "FundRegistry"]

SERIES_ID_RE = re.compile(r"^S\d{6,10}$")
CLASS_ID_RE = re.compile(r"^C\d{6,10}$")

_DDL = """
CREATE TABLE IF NOT EXISTS funds (
    series_id      TEXT PRIMARY KEY,
    ticker_current TEXT,
    name           TEXT,
    issuer         TEXT,
    entry_json     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
-- Ticker index serves by_ticker() DISPLAY LOOKUP ONLY; nothing keys on a ticker (spec §2).
CREATE INDEX IF NOT EXISTS idx_funds_ticker ON funds(ticker_current);
"""


def _utc_now() -> str:
    """Default clock — all record times are UTC (spec §9)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class IdentityError(ValueError):
    """Raised when a registry write carries a malformed identity — a bare ticker, a truncated
    series id, a bad class id. Rejection happens before any write (spec §2 CONTRACT)."""


@dataclass(frozen=True)
class FundEntry:
    """Spec §2's registry entry — exactly its field list, nothing more.

    `category_draft` is etfdb's label, STEERING ONLY and never trusted: no identity or baseline
    code path may read it. It rides in the entry as recorded context (HECO's stale ESG label is
    the canonical example, spec test 1) and decides nothing — FundRegistry stores and returns
    it inside the entry but never branches on it.
    """

    series_id: str
    class_ids: list[str]
    cik: int
    ticker_current: str
    name: str
    issuer: str
    category_draft: str | None
    concentration_industries: list[str]
    prospectus_accession: str
    holdings_source: str
    first_seen: str
    verified_at: str


def _validate_identity(entry: FundEntry) -> None:
    """THE write-path enforcement (spec §2 CONTRACT): schema validation rejects a bare ticker.
    Raises before the caller writes anything — no file, no row, no event."""
    sid = entry.series_id
    if not isinstance(sid, str) or not SERIES_ID_RE.match(sid):
        raise IdentityError(
            f"registry key must be an SEC series id (S######), got {sid!r} — "
            "a bare ticker is rejected at the write path (the HECO rule)")
    if not isinstance(entry.class_ids, list):
        raise IdentityError(
            f"class_ids must be a list of SEC class ids (C######), got {entry.class_ids!r}")
    for cid in entry.class_ids:
        if not isinstance(cid, str) or not CLASS_ID_RE.match(cid):
            raise IdentityError(
                f"malformed class id {cid!r} on {sid} (want C######)")


def _entry_from_json(text: str) -> FundEntry:
    return FundEntry(**json.loads(text))


class FundRegistry:
    def __init__(self, layout: StoreLayout, registry: Registry, event_store: EventStore,
                 clock: Callable[[], str] | None = None):
        """`clock` is a zero-arg callable returning the current ISO-8601 UTC string, used for
        the row's `updated_at` and the `registry.updated` envelope ts."""
        self.layout = layout
        self.registry = registry
        self.event_store = event_store
        self._clock = clock if clock is not None else _utc_now
        # Owns its table on the shared connection; registry.py's DDL stays frozen.
        registry.conn.executescript(_DDL)
        registry.conn.commit()

    def upsert(self, entry: FundEntry) -> None:
        """Validate -> versioned object file -> funds row -> `registry.updated` on `_system`.

        IdentityError fires before any write. The object file at fund_path(series_id) is the
        truth (S3 versioning preserves its history later); the row is the index; the event is
        the change summary, `fields_changed` diffed against the prior entry_json on update.
        """
        _validate_identity(entry)
        new = asdict(entry)
        old_row = self.registry.conn.execute(
            "SELECT entry_json FROM funds WHERE series_id = ?", (entry.series_id,)).fetchone()
        if old_row is None:
            change, fields_changed = "created", []
        else:
            old = json.loads(old_row["entry_json"])
            change = "updated"
            fields_changed = sorted(k for k in new if old.get(k) != new[k])

        write_json_atomic(self.layout.fund_path(entry.series_id), new)
        now = self._clock()
        self.registry.conn.execute(
            """INSERT INTO funds (series_id, ticker_current, name, issuer, entry_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(series_id) DO UPDATE SET
                 ticker_current = excluded.ticker_current,
                 name           = excluded.name,
                 issuer         = excluded.issuer,
                 entry_json     = excluded.entry_json,
                 updated_at     = excluded.updated_at""",
            (entry.series_id, entry.ticker_current, entry.name, entry.issuer,
             canonical_json(new), now))
        self.registry.conn.commit()
        self.event_store.append({
            "ts": now, "lead": SYSTEM_LEAD, "type": "registry.updated",
            "payload": {"series_id": entry.series_id, "ticker": entry.ticker_current,
                        "change": change, "fields_changed": fields_changed},
            "schema": 1})

    def get(self, series_id: str) -> FundEntry | None:
        row = self.registry.conn.execute(
            "SELECT entry_json FROM funds WHERE series_id = ?", (series_id,)).fetchone()
        return None if row is None else _entry_from_json(row["entry_json"])

    def by_ticker(self, ticker: str) -> FundEntry | None:
        """Display lookup ONLY (spec §2: tickers are display-only attributes). Never used to
        key a lead or baseline; under ticker reuse the most recently updated holder wins."""
        row = self.registry.conn.execute(
            "SELECT entry_json FROM funds WHERE ticker_current = ? "
            "ORDER BY updated_at DESC, series_id DESC LIMIT 1", (ticker,)).fetchone()
        return None if row is None else _entry_from_json(row["entry_json"])

    def all_funds(self) -> list[FundEntry]:
        rows = self.registry.conn.execute(
            "SELECT entry_json FROM funds ORDER BY series_id").fetchall()
        return [_entry_from_json(r["entry_json"]) for r in rows]
