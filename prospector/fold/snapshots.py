"""Reactive snapshot policy — when to materialize a fold (spec §5, adaptive-snapshot CONTRACT).

Shape from prophit_skunkworks/ltee_archive/snapshot_policy.py (AdaptiveSnapshotPolicy's
three-tier density), archive snapshot dated 2026-03-29, vendored 2026-07-02. No commit hash
available (archive copy).

Critical inversion from the source (spec §5): Prophit authored its training curriculum, so its
snapshot density keys on scheduled epoch boundaries. The Prospector cannot know when a fracture
is coming — that is the premise — so the trigger is inverted from scheduled to lead-reactive:
dense while a lead is active (DEFAULT daily), sparse when quiet (DEFAULT weekly floor), plus an
immediate snapshot on any state change — the reactive analog of the apex tier. The
epoch-boundary triggers (480–620, 1400–1600) deliberately did NOT port; they are meaningless
without a training schedule.

`should_snapshot` is a pure function of its arguments (clock injected): same state, same
last-snapshot timestamp, same clock -> same decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from prospector.primitives.atomic import sha256_file, write_json_atomic
from prospector.store.envelope import parse_ts
from prospector.store.layout import StoreLayout, ts_compact
from prospector.store.registry import Registry


class SnapshotDivergenceError(RuntimeError):
    """A rewrite of an existing (lead, ts) snapshot carried a DIFFERENT fold state (beyond the
    reason field). First-write-wins on the file is correct only while two invariants hold:
    (a) events are monotonic — never backdated before an existing snapshot's ts — so the event
    set folded up to any past T is frozen once T passes; and (b) the fold is deterministic.
    A divergence means one of those broke: a backdated event (breaks a) or a nondeterministic
    fold (breaks b, a bug). Rather than silently keep the old bytes and never learn the fold
    diverged, we surface it — audit = detection."""

_NAMED_INTERVALS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}


def _parse_interval(value) -> timedelta:
    """'hourly' / 'daily' / 'weekly', or an integer number of days."""
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 1:
            raise ValueError(f"snapshot interval must be >= 1 day, got {value}")
        return timedelta(days=value)
    if isinstance(value, str) and value.lower() in _NAMED_INTERVALS:
        return _NAMED_INTERVALS[value.lower()]
    raise ValueError(
        f"unrecognized snapshot interval {value!r} (use 'hourly'/'daily'/'weekly' or integer days)")


@dataclass(frozen=True)
class SnapshotConfig:
    active_interval: timedelta
    quiet_floor: timedelta

    @classmethod
    def from_cfg(cls, d: dict) -> "SnapshotConfig":
        """Parse the `snapshots:` config section, e.g. {'active': 'daily', 'quiet': 'weekly'}.
        Missing keys fall back to the spec DEFAULTs (active daily, quiet weekly)."""
        return cls(active_interval=_parse_interval(d.get("active", "daily")),
                   quiet_floor=_parse_interval(d.get("quiet", "weekly")))


@dataclass(frozen=True)
class SnapshotDecision:
    save: bool
    reason: str | None = None  # 'state_change' | 'active_daily' | 'quiet_weekly'


def should_snapshot(state: dict, last_snapshot_ts: str | None, changed: list[str],
                    now: datetime, cfg: SnapshotConfig) -> SnapshotDecision:
    """Decide whether a lead's fold gets materialized now. Pure — the clock is `now`.

    Priority (spec §5): any state change snapshots immediately (the apex tier's reactive
    analog); an active lead snapshots on the active interval; every lead snapshots on the
    quiet floor; a never-snapshotted lead always saves.
    """
    if changed:
        return SnapshotDecision(save=True, reason="state_change")
    elapsed = None if last_snapshot_ts is None else now - parse_ts(last_snapshot_ts)
    if state.get("status") == "active" and (elapsed is None or elapsed >= cfg.active_interval):
        return SnapshotDecision(save=True, reason="active_daily")
    if elapsed is None or elapsed >= cfg.quiet_floor:
        return SnapshotDecision(save=True, reason="quiet_weekly")
    return SnapshotDecision(save=False, reason=None)


def write_snapshot(layout: StoreLayout, registry: Registry, lead: str, state: dict,
                   reason: str, ts: str,
                   fault_sink: Callable[[dict], None] | None = None) -> Path:
    """Materialize a fold to snapshots/{lead}/{ts}.json and index it in the registry.

    The written JSON is the state dict extended with a top-level "reason" key, so the
    file alone carries why it was materialized and `pros store reindex` recovers the
    true reason from the fossil record instead of degrading to 'reindexed' (spec §7:
    the trees are the truth, the registry only the index).

    The snapshot_id is deterministic ('{lead}:{compact ts}'), so re-writing the same
    (lead, ts) is idempotent first-write-wins on both surfaces: the registry insert is
    INSERT OR IGNORE, and an existing file is left untouched (its hash is reused) so
    the indexed sha256 always matches the bytes on disk even when a replay carries a
    different reason. The indexed file_path is store-root-relative — like event rows,
    it doubles as the S3 key unchanged (spec §7).

    Divergence guard (defense in depth): if an existing file carries a DIFFERENT state
    (ignoring the reason field), first-write-wins would silently mask a broken invariant
    (see SnapshotDivergenceError). Instead we make it loud: emit a `fault` on _system via
    `fault_sink` if provided (keeping the old bytes so the record stays consistent), else
    raise. The runner passes its EventStore.append as the sink, so the divergence reaches
    the fault-email surface; a pure caller with no sink gets the exception.
    """
    path = layout.snapshot_path(lead, ts)
    if path.exists():
        sha256 = sha256_file(path)
        existing = json.loads(path.read_bytes())
        existing.pop("reason", None)
        if existing != dict(state):
            msg = (f"snapshot rewrite for ({lead}, {ts}) diverged from the materialized "
                   f"state — a backdated event or a nondeterministic fold (invariant break)")
            if fault_sink is not None:
                fault_sink({"ts": ts, "lead": "_system", "type": "fault",
                            "payload": {"subsystem": "snapshot", "message": msg, "lead": lead},
                            "schema": 1})
            else:
                raise SnapshotDivergenceError(msg)
    else:
        sha256 = write_json_atomic(path, dict(state, reason=reason))
    registry.insert_snapshot(snapshot_id=f"{lead}:{ts_compact(ts)}", lead=lead, ts=ts,
                             reason=reason,
                             file_path=path.relative_to(layout.root).as_posix(),
                             sha256=sha256)
    return path
