"""Registry repair — rebuild the index from the fossil record (spec §5/§7).

The events/ and snapshots/ trees are the durable truth; registry.sqlite is only the queryable
index over them. `pros store reindex` re-scans both trees, re-validates each event against the
frozen envelope, recomputes every SHA-256, and INSERT OR IGNOREs the rows — it computes nothing
new, so it is repair, not run-now (CLAUDE.md). Scans ignore `*.tmp` (atomic.py's crashed-writer
leftovers, invisible by contract) and dotfiles; those are expected artifacts, not corrupt
records, so they do not count as skipped.

Reindex RECOMPUTES; it cannot verify: `ingested_at` is operational bookkeeping the event files
do not carry, so a rebuilt row gets the file's mtime (or now, if stat fails) — the original
ingest time is unrecoverable from the fossil record alone. A snapshot row's `reason` is read
back from the file's top-level 'reason' key (write_snapshot embeds it exactly so repair can
recover it); a file without one (foreign or pre-embedding) gets 'reindexed'. `uploaded_at`
starts NULL, so the next sync re-uploads (idempotent: same keys, same bytes).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from prospector.primitives.atomic import sha256_file
from prospector.store.envelope import canonical_json, validate
from prospector.store.layout import StoreLayout, ts_from_compact
from prospector.store.registry import Registry


def rebuild_registry(layout: StoreLayout, registry: Registry) -> dict:
    """Scan events/ and snapshots/ and rebuild the index rows from the files.

    Deterministic repair: record columns (event_id, ts, lead, type, schema, payload, sha256,
    file_path) come from the files alone; INSERT OR IGNORE means reindexing into a live
    registry never clobbers existing rows (first ingest's bookkeeping survives). Counts are
    files: `events_indexed`/`snapshots_indexed` are the valid files now present in the index
    (whether this call inserted them or they were already there), `skipped` is anything in
    either tree that failed to parse as its record type.
    """
    counts = {"events_indexed": 0, "snapshots_indexed": 0, "skipped": 0}
    for path in _scan(layout.events_root()):
        counts["events_indexed" if _index_event(layout, registry, path)
               else "skipped"] += 1
    for path in _scan(layout.snapshots_root()):
        counts["snapshots_indexed" if _index_snapshot(layout, registry, path)
               else "skipped"] += 1
    return counts


def _scan(root: Path) -> Iterator[Path]:
    """Every regular file under root, sorted for a deterministic walk, minus *.tmp and
    anything under a dot-named component."""
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in parts) or path.name.endswith(".tmp"):
            continue
        yield path


def _index_event(layout: StoreLayout, registry: Registry, path: Path) -> bool:
    """One events/{lead}/{ts}_{type}_{event_id}.json file -> one row. The envelope inside the
    file is the truth for ts/lead/type/schema; only event_id comes from the filename (the
    layout's trailing component — types may themselves contain underscores, ids may not)."""
    if path.suffix != ".json" or "_" not in path.stem:
        return False
    event_id = path.stem.rsplit("_", 1)[1]
    if not event_id:
        return False
    try:
        env = validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):  # unreadable, not JSON, or envelope-invalid
        return False
    registry.insert_event(
        event_id=event_id, ts=env.ts, lead=env.lead, type=env.type, schema=env.schema,
        payload_json=canonical_json(env.payload), sha256=sha256_file(path),
        file_path=path.relative_to(layout.root).as_posix(),
        ingested_at=_mtime_or_now(path))
    return True


def _index_snapshot(layout: StoreLayout, registry: Registry, path: Path) -> bool:
    """One snapshots/{lead}/{compact ts}.json file -> one row, with the deterministic
    snapshot_id '{lead}:{compact ts}' that write_snapshot uses."""
    if path.suffix != ".json" or path.parent == layout.snapshots_root():
        return False  # a snapshot lives one level down: its parent directory is the lead
    try:
        # The stem is the ONLY carrier of a snapshot's ts (the file holds the fold state, no ts) —
        # recover it via layout.ts_from_compact, which parses BOTH the whole-second and sub-second
        # forms (a garbage/foreign stem raises ValueError -> skipped, never a crash).
        ts = ts_from_compact(path.stem)
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    reason = content.get("reason") if isinstance(content, dict) else None
    lead = path.parent.name
    registry.insert_snapshot(
        snapshot_id=f"{lead}:{path.stem}", lead=lead, ts=ts,
        reason=reason if isinstance(reason, str) else "reindexed",
        file_path=path.relative_to(layout.root).as_posix(), sha256=sha256_file(path))
    return True


def _mtime_or_now(path: Path) -> str:
    try:
        return _iso_utc(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))
    except OSError:
        return _iso_utc(datetime.now(timezone.utc))


def _iso_utc(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
