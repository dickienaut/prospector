"""The frozen five-field event envelope (spec §5, CONTRACT).

    { "ts": "2026-07-14T13:00:00Z", "lead": "<lead_id>", "type": "<string>",
      "payload": { }, "schema": 1 }

The envelope is the storage schema. `type` is an open vocabulary by design — never an enum,
never checked against a list of known types: an unforeseen event type is the system's whole
premise, and v2's writers plug into exactly this gap. Extension happens inside `payload`;
the five top-level fields never change.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timezone, datetime

FIELDS = ("ts", "lead", "type", "payload", "schema")

SYSTEM_LEAD = "_system"

# Leads become directory components under events/ and snapshots/ — keep them path-safe.
_LEAD_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")


class EnvelopeError(ValueError):
    """Raised when a raw event fails envelope validation. Malformed events are rejected at
    write time (spec test 4) — they never reach the record."""


@dataclass(frozen=True)
class Envelope:
    ts: str
    lead: str
    type: str
    payload: dict
    schema: int = 1

    def to_dict(self) -> dict:
        return {"ts": self.ts, "lead": self.lead, "type": self.type,
                "payload": self.payload, "schema": self.schema}


def canonical_json(obj) -> str:
    """Canonical serialization: stable bytes -> stable SHA-256 across processes and runs."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def parse_ts(ts: str) -> datetime:
    """Parse an envelope timestamp; must be ISO-8601 and explicitly UTC."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        raise EnvelopeError(f"ts is not ISO-8601: {ts!r}") from e
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(None):
        raise EnvelopeError(f"ts must be UTC (all record times are UTC): {ts!r}")
    return dt


def validate(raw: dict) -> Envelope:
    """Validate a raw dict against the frozen envelope. Exactly the five fields — a missing or
    extra top-level key is rejected (extension belongs inside payload)."""
    if not isinstance(raw, dict):
        raise EnvelopeError(f"event must be a dict, got {type(raw).__name__}")
    keys = set(raw)
    missing, extra = set(FIELDS) - keys, keys - set(FIELDS)
    if missing or extra:
        raise EnvelopeError(f"envelope is five fields exactly; missing={sorted(missing)} "
                            f"extra={sorted(extra)}")

    parse_ts(raw["ts"])

    lead = raw["lead"]
    if not isinstance(lead, str) or not (lead == SYSTEM_LEAD or _LEAD_RE.match(lead)):
        raise EnvelopeError(f"lead must be '_system' or a path-safe id, got {lead!r}")

    type_ = raw["type"]
    if not isinstance(type_, str) or not type_.strip():
        raise EnvelopeError(f"type must be a non-empty string, got {type_!r}")

    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise EnvelopeError(f"payload must be a JSON object, got {type(payload).__name__}")
    try:
        canonical_json(payload)
    except (TypeError, ValueError) as e:
        raise EnvelopeError(f"payload is not JSON-serializable: {e}") from e

    schema = raw["schema"]
    if not isinstance(schema, int) or isinstance(schema, bool) or schema < 1:
        raise EnvelopeError(f"schema must be a positive int, got {schema!r}")

    return Envelope(ts=raw["ts"], lead=lead, type=type_, payload=payload, schema=schema)
