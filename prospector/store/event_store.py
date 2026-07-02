"""Append-only event store — atomic blob per event + registry index row (spec §5/§7, CONTRACT).

An append is: validate the envelope -> write the five-field JSON dict atomically under
events/{lead}/ -> insert the index row. The events/ tree is the truth and the registry is the
queryable index over it (reads go through the registry; `pros store reindex` rebuilds rows from
files). There is no update, delete, or mutation surface — append-only by construction, not by
convention: corrections are new events, a changed mind is a new `verdict` that supersedes.

File paths carried in WrittenEvent and the registry are RELATIVE to the store root, so the same
strings double as S3 keys unchanged (§7: the S3 tree is the durable substrate).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from prospector.primitives.atomic import write_json_atomic
from prospector.store.envelope import SYSTEM_LEAD, Envelope, canonical_json, validate
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

__all__ = ["WrittenEvent", "EventStore", "envelope_from_row"]


def _utc_now() -> str:
    """Default clock — all record times are UTC (spec §9)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class WrittenEvent:
    event_id: str
    file_path: str  # relative to the store root — portable to an S3 key as-is
    sha256: str
    envelope: Envelope


def envelope_from_row(row: sqlite3.Row) -> Envelope:
    """Rebuild an Envelope from a registry `events` row (the fold and CLI read these)."""
    return Envelope(ts=row["ts"], lead=row["lead"], type=row["type"],
                    payload=json.loads(row["payload"]), schema=row["schema"])


class EventStore:
    def __init__(self, layout: StoreLayout, registry: Registry,
                 clock: Callable[[], str] | None = None):
        """`clock` is a zero-arg callable returning the current ISO-8601 UTC string, used only
        for the `ingested_at` bookkeeping column (never for the envelope `ts`)."""
        self.layout = layout
        self.registry = registry
        self._clock = clock if clock is not None else _utc_now

    def append(self, raw: dict | Envelope) -> WrittenEvent:
        """Validate, write the blob atomically, index it. Malformed events raise EnvelopeError
        before anything is written — they never reach the record (file or row)."""
        env = validate(raw.to_dict() if isinstance(raw, Envelope) else raw)
        event_id = uuid4().hex
        path = self.layout.event_path(env.lead, env.ts, env.type, event_id)
        sha256 = write_json_atomic(path, env.to_dict())
        rel_path = path.relative_to(self.layout.root).as_posix()
        self.registry.insert_event(
            event_id=event_id, ts=env.ts, lead=env.lead, type=env.type, schema=env.schema,
            payload_json=canonical_json(env.payload), sha256=sha256, file_path=rel_path,
            ingested_at=self._clock())
        return WrittenEvent(event_id=event_id, file_path=rel_path, sha256=sha256, envelope=env)

    def read_lead(self, lead: str, type: str | None = None) -> list[Envelope]:
        """A lead's events in the fold's total order (ts, event_id)."""
        return [envelope_from_row(r) for r in self.registry.events_for_lead(lead, type)]

    def read_system(self, type: str | None = None) -> list[Envelope]:
        return self.read_lead(SYSTEM_LEAD, type)
