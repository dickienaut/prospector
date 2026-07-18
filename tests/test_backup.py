"""Fossil-store backup — the dual-HDD durability layer (spec §7; build note
docs/notes/2026-07-11-store-durability-backup.md). Tests are OFFLINE: temp dirs stand in for the HDD
mount points, blessed with the marker file the operator would create once per drive.

The load-bearing invariants:
  - the append-only fossils (events/ snapshots/ ingest/ baselines/ runs/ registry/) mirror to a target,
    and the registry goes via the WAL-safe `.backup` API — never a raw copy (no -wal/-shm at the target);
  - incremental: a second backup copies nothing; a new fossil copies just itself;
  - FAIL-LOUD: an unmounted/unblessed target FAULTS (recorded in report.failures) — and is NEVER created
    (the footgun: silently writing the "backup" onto the internal disk) — while a healthy target on the
    same run still receives the data (best-effort-but-loud);
  - the restore PROVES out: reindex rebuilds the lead record from the backed-up fossils ALONE (even with
    the registry copy deleted), and the counts match the live store.
"""

import sqlite3

import pytest
from click.testing import CliRunner

import prospector.store.backup as backup_module
from prospector.cli.main import cli
from prospector.fold.fold import fold
from prospector.fold.snapshots import write_snapshot
from prospector.primitives.atomic import write_json_atomic
from prospector.store.backup import (DEFAULT_MARKER, SUCCESS_MARKER, BackupError, backup_store,
                                     last_backup_ts, verify_restore)
from prospector.store.event_store import EventStore

LEAD = "ld_x"


def _ev(lead, ts, type_, payload):
    return {"ts": ts, "lead": lead, "type": type_, "payload": payload, "schema": 1}


def _seed(layout, registry):
    """A realistic small store: a spawned lead (2 events) + a _system event, one materialized
    snapshot, and one fund-identity object under registry/funds/ (the tree the note omitted)."""
    store = EventStore(layout, registry)
    store.append(_ev(LEAD, "2026-07-01T00:00:00Z", "lead.spawned",
                     {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}))
    store.append(_ev(LEAD, "2026-07-02T00:00:00Z", "xcorr.tick", {"z": 2.9}))
    store.append(_ev("_system", "2026-07-02T00:00:00Z", "config.changed", {"diff": {}}))
    write_snapshot(layout, registry, LEAD, fold(registry.events_for_lead(LEAD)),
                   "state_change", "2026-07-02T00:00:00Z")
    write_json_atomic(layout.fund_path("S000001"),
                      {"series_id": "S000001", "ticker_current": "XLK", "name": "Tech", "issuer": "SSGA"})
    return store


def _bless(target, marker=DEFAULT_MARKER):
    target.mkdir(parents=True, exist_ok=True)
    (target / marker).write_text("blessed")
    return target


# -- mirror: fossils + WAL-safe registry -----------------------------------------------------------

def test_backup_mirrors_fossils_and_registry_to_target(layout, registry, tmp_path):
    _seed(layout, registry)
    target = _bless(tmp_path / "hd1")

    report = backup_store(layout, [target])

    assert len(report.targets) == 1 and report.failures == []
    r = report.targets[0]
    assert r.files_copied > 0 and r.registry_backed_up
    assert (target / "registry" / "funds" / "S000001.json").is_file()   # the irreplaceable fund object
    assert (target / "snapshots" / LEAD).is_dir()
    assert any((target / "events" / LEAD).glob("*.json"))
    # registry.sqlite arrived via the .backup API — a healthy db, and NO raw WAL sidecars copied.
    assert (target / "registry.sqlite").is_file()
    assert not (target / "registry.sqlite-wal").exists() and not (target / "registry.sqlite-shm").exists()
    conn = sqlite3.connect(str(target / "registry.sqlite"))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3
    finally:
        conn.close()


def test_second_backup_is_incremental(layout, registry, tmp_path):
    store = _seed(layout, registry)
    target = _bless(tmp_path / "hd1")

    backup_store(layout, [target])
    second = backup_store(layout, [target])
    assert second.targets[0].files_copied == 0            # append-only -> nothing new to copy
    assert second.targets[0].files_skipped > 0

    store.append(_ev(LEAD, "2026-07-03T00:00:00Z", "xcorr.tick", {"z": 3.1}))  # one new fossil
    third = backup_store(layout, [target])
    assert third.targets[0].files_copied == 1             # exactly the new event file


def test_needs_copy_tolerates_coarse_mtime_destination(tmp_path):
    """Regression (real-drive bug): external backup drives are usually exFAT/FAT, whose mtime is TRUNCATED
    (~2 s) — `shutil.copy2` writes the src mtime, the drive rounds it DOWN, and an unchanged file then looks
    'newer' every run, re-copying a 160 MB store in full each time. The same-FS temp-dir incremental test
    above cannot reproduce that (green-on-synthetic); this drives `_needs_copy` against a truncated dst.
    A same-size dst within the modify-window must SKIP; a genuinely-newer src (or a size change) still copies."""
    import os
    src = tmp_path / "src.json"; src.write_text("x" * 100)
    dst = tmp_path / "dst.json"; dst.write_text("x" * 100)
    m = src.stat().st_mtime

    os.utime(dst, (m, m - 1.5))                               # exFAT-style truncation, within the 2s window
    assert backup_module._needs_copy(src, dst) is False      # ...must SKIP (before the fix: re-copied)

    os.utime(dst, (m, m - 3600))                             # a genuine same-day re-pull is hours newer
    assert backup_module._needs_copy(src, dst) is True       # ...still copies

    dst.write_text("x" * 101); os.utime(dst, (m, m))         # a size change always copies
    assert backup_module._needs_copy(src, dst) is True
    assert backup_module._needs_copy(src, tmp_path / "gone.json") is True   # missing dst copies


def test_a_same_size_ingest_re_pull_within_the_mtime_window_still_re_copies(layout, registry, tmp_path):
    """BK-2 (deep-review finding): the `_MTIME_WINDOW_S` window that absorbs exFAT mtime truncation can
    ALIAS a real change. A same-day re-pull that OVERWRITES an `ingest/` file with DIFFERENT content of
    the EXACT SAME size, landing within the window, reads as 'unchanged' by the size+mtime quick-check and
    is silently skipped — leaving a STALE copy on the HDD that never self-corrects (the source mtime never
    advances past dst+window again). `ingest/` is the documented overwrite-in-place tree (holdings
    same-day re-pull / SOI same-accession re-freeze); append-only trees can't alias (never rewritten). The
    same-FS incremental test above cannot catch it — this forces the aliasing condition deterministically.
    RED on branch: the stale copy persists. GREEN: the rewritten-in-place tree is content-verified."""
    import os
    _seed(layout, registry)
    target = _bless(tmp_path / "hd1")
    ing = layout.root / "ingest" / "holdings" / "S000001" / "2026-07-01" / "XLK.csv"
    ing.parent.mkdir(parents=True, exist_ok=True)
    ing.write_bytes(b"weight,cusip\n0.50,AAA\n")             # content C1

    backup_store(layout, [target])                            # first backup -> dst has C1
    dst = target / "ingest" / "holdings" / "S000001" / "2026-07-01" / "XLK.csv"
    assert dst.read_bytes() == b"weight,cusip\n0.50,AAA\n"

    # a same-day re-pull overwrites the ingest file with DIFFERENT bytes of the EXACT same length...
    ing.write_bytes(b"weight,cusip\n0.90,AAA\n")             # content C2, one digit changed, same size
    assert ing.stat().st_size == dst.stat().st_size          # size identical -> the quick-check is blind
    m = dst.stat().st_mtime
    os.utime(ing, (m, m))                                    # ...and landing within the window (delta 0)

    backup_store(layout, [target])                            # second backup

    assert dst.read_bytes() == b"weight,cusip\n0.90,AAA\n"    # RED: still C1 (stale); GREEN: refreshed to C2


def test_registry_goes_through_the_backup_api_not_a_raw_copy(layout, registry, tmp_path, monkeypatch):
    _seed(layout, registry)
    target = _bless(tmp_path / "hd1")
    calls = []
    real = backup_module.backup_sqlite

    def recording(src, dest):
        calls.append((str(src), str(dest)))
        return real(src, dest)

    monkeypatch.setattr(backup_module, "backup_sqlite", recording)
    backup_store(layout, [target])
    assert calls == [(str(layout.registry_path()), str(target / "registry.sqlite"))]  # never a raw cp


# -- fail-loud: an unmounted/unblessed target faults, is never created, and never blocks a good one ---

def test_unblessed_target_faults_but_a_blessed_target_still_gets_the_data(layout, registry, tmp_path):
    _seed(layout, registry)
    good = _bless(tmp_path / "hd1")
    bad = tmp_path / "hd2"                                 # exists but carries NO marker
    bad.mkdir()

    report = backup_store(layout, [good, bad])

    assert [t.target for t in report.targets] == [str(good)]      # the healthy drive still got it
    assert (good / "registry.sqlite").is_file()
    assert len(report.failures) == 1 and report.failures[0][0] == str(bad)
    assert not (bad / "events").exists()                          # nothing written to the faulted drive


def test_a_blessed_target_failing_mid_copy_records_a_failure_and_still_backs_up_the_healthy_drive(
        layout, registry, tmp_path, monkeypatch):
    """BK-1 (deep-review finding): the fail-loud tests above cover only the UNBLESSED case — a target that
    fails the blessing check BEFORE any copy. A BLESSED target can still fail PARTWAY through the copy: the
    drive fills (ENOSPC), is unplugged mid-mirror, or `.backup` errors. Before the fix that OSError
    propagated straight out of backup_store, so (a) every LATER target was skipped — the healthy second
    drive got NOTHING — and (b) no failure was recorded, so the CLI raised a raw traceback instead of the
    designed FAULT line. 'best-effort-but-loud' was violated exactly when a drive degrades. Synthetic
    temp-dir targets never fill up on their own, so this INJECTS the mid-copy failure to reproduce the
    'both HDDs present, one degrades' scenario the design promises to survive."""
    _seed(layout, registry)
    degrading = _bless(tmp_path / "hd_fills_up")   # processed first; fails partway through the copy
    healthy = _bless(tmp_path / "hd_ok")           # processed second; MUST still receive the full backup

    real_copy2 = backup_module.shutil.copy2
    def flaky_copy2(src, dst, *a, **k):
        if str(dst).startswith(str(degrading)):
            raise OSError(28, "No space left on device")   # ENOSPC partway into the degrading drive
        return real_copy2(src, dst, *a, **k)
    monkeypatch.setattr(backup_module.shutil, "copy2", flaky_copy2)

    report = backup_store(layout, [degrading, healthy])   # must NOT propagate the OSError

    # the degrading drive is recorded as a loud, NAMED failure (the CLI turns report.failures into a
    # non-zero exit + a FAULT line) — never a silent skip and never a raw traceback
    assert len(report.failures) == 1 and report.failures[0][0] == str(degrading)
    # and the healthy drive still got the WHOLE backup — a degrading sibling never skips it
    assert [t.target for t in report.targets] == [str(healthy)]
    assert report.targets[0].files_copied > 0 and report.targets[0].registry_backed_up
    assert any((healthy / "events" / LEAD).glob("*.json"))
    assert (healthy / "registry.sqlite").is_file()


def test_a_non_drive_midcopy_fault_does_not_get_the_drive_health_hint(layout, registry, tmp_path, monkeypatch):
    """BK-MSG-01: the broad mid-copy `except` is deliberate (fall through to the healthy drive), but the
    operator hint must match the cause. A NON-OSError fault (a code bug in the copy path, not a degraded
    drive) must NOT be labelled 'retry once the drive is healthy' — retrying won't fix a bug; it must
    surface as an unexpected error to investigate, carrying the real exception class."""
    _seed(layout, registry)
    target = _bless(tmp_path / "hd1")

    def boom_copy2(src, dst, *a, **k):
        raise KeyError("not a drive fault — a programming error in the copy path")
    monkeypatch.setattr(backup_module.shutil, "copy2", boom_copy2)

    report = backup_store(layout, [target])

    assert len(report.failures) == 1
    _, reason = report.failures[0]
    assert "KeyError" in reason                              # the real cause is surfaced ...
    assert "retry once the drive is healthy" not in reason  # ... not the misleading drive hint
    assert "unexpected error" in reason


# -- M7-02: the last-success marker (the runner's backup-health input) --------------------------------

def test_success_marker_is_stamped_on_a_verified_target_and_read_back(layout, registry, tmp_path):
    """M7-02: on a VERIFIED backup, the target gets a `SUCCESS_MARKER` carrying that backup's UTC ts, and
    `last_backup_ts` reads it back. This marker (distinct from the operator's blessing marker) is the honest
    'there is a fresh successful backup here' fact the runner folds into the §8a heartbeat's health channel.
    Written only when `now` is supplied — the CLI always supplies it."""
    _seed(layout, registry)
    good = _bless(tmp_path / "hd1")
    now = "2026-07-14T22:31:00Z"

    report = backup_store(layout, [good], now=now)

    assert [t.target for t in report.targets] == [str(good)]
    assert (good / SUCCESS_MARKER).read_text(encoding="utf-8") == now   # stamped with the backup time
    assert last_backup_ts(good) == now                                   # and reads back through the API
    assert last_backup_ts(tmp_path / "never") is None                    # a target with no marker → None


def test_no_success_marker_on_a_target_that_failed_mid_copy(layout, registry, tmp_path, monkeypatch):
    """The marker is written INSIDE the per-target try, AFTER the copy + registry land — so a target that
    fails partway through the copy (BK-1's mid-copy failure) gets NO fresh marker, and the runner will fold
    `backup.stale` for it. Never-on-attempt, same discipline as `heartbeat.sent`: a backup we cannot attest
    is not a success. The healthy sibling still gets its marker (best-effort-but-loud)."""
    _seed(layout, registry)
    degrading = _bless(tmp_path / "hd_fills_up")   # fails partway through the copy
    healthy = _bless(tmp_path / "hd_ok")           # completes — MUST still get its marker
    now = "2026-07-14T22:31:00Z"

    real_copy2 = backup_module.shutil.copy2
    def flaky_copy2(src, dst, *a, **k):
        if str(dst).startswith(str(degrading)):
            raise OSError(28, "No space left on device")
        return real_copy2(src, dst, *a, **k)
    monkeypatch.setattr(backup_module.shutil, "copy2", flaky_copy2)

    backup_store(layout, [degrading, healthy], now=now)

    assert last_backup_ts(degrading) is None       # no marker on the drive that failed mid-copy
    assert last_backup_ts(healthy) == now          # the healthy drive attests success


def test_no_marker_written_when_now_is_omitted(layout, registry, tmp_path):
    # Backward-compatible: a caller that only mirrors (no `now`) writes no marker — the mirror is unchanged.
    _seed(layout, registry)
    good = _bless(tmp_path / "hd1")
    backup_store(layout, [good])
    assert not (good / SUCCESS_MARKER).exists()
    assert last_backup_ts(good) is None


def test_unmounted_target_is_never_created(layout, registry, tmp_path):
    # The footgun this guards: if the drive is unplugged its path is ABSENT; we must fault, never
    # mkdir it (that would write the "backup" onto the internal disk and silently succeed).
    _seed(layout, registry)
    missing = tmp_path / "unplugged-drive"                 # does not exist, no marker

    report = backup_store(layout, [missing])

    assert report.targets == [] and len(report.failures) == 1
    assert not missing.exists()                            # NEVER created


def test_no_targets_configured_raises(layout, registry):
    _seed(layout, registry)
    with pytest.raises(BackupError, match="no backup targets"):
        backup_store(layout, [])


# -- restore proof: rebuild from the fossils alone, counts match ------------------------------------

def test_verify_restore_rebuilds_and_counts(layout, registry, tmp_path):
    _seed(layout, registry)
    target = _bless(tmp_path / "hd1")
    backup_store(layout, [target])

    counts = verify_restore(target)

    assert counts["events_indexed"] == 3 and counts["snapshots_indexed"] == 1
    assert counts["fund_objects"] == 1 and counts["skipped"] == 0
    assert counts["leads"] == 2                            # ld_x + _system


def test_verify_restore_works_from_fossils_even_with_the_registry_copy_deleted(layout, registry, tmp_path):
    # The note's core claim: the fossils are self-sufficient — reindex rebuilds the lead record even if
    # the registry.sqlite backup were lost. Delete it, then prove the restore still stands up.
    _seed(layout, registry)
    target = _bless(tmp_path / "hd1")
    backup_store(layout, [target])
    (target / "registry.sqlite").unlink()

    counts = verify_restore(target)
    assert counts["events_indexed"] == 3 and counts["snapshots_indexed"] == 1


# -- CLI surfaces ----------------------------------------------------------------------------------

def test_pros_backup_faults_nonzero_when_no_targets_configured(layout, registry, store_root,
                                                               monkeypatch, tmp_path):
    # The repo config ships backup.targets: [] — so `pros backup` must fault loudly (non-zero) until
    # the Mini's drive paths are set. (Proves the CLI wiring + the fail-loud posture; the copy logic
    # itself is covered by the library tests above.)
    #
    # Hermeticity (item 4, docs/notes/2026-07-18-mandate-noise-cut-next-steps.md): load the TRACKED config
    # in ISOLATION. A dev checkout's gitignored config/prospector.local.yaml overlay injects real
    # backup.targets (the Mini's drive paths), which load_config deep-merges over the tracked base — that
    # would make this assertion pass only on CI (no overlay) and fail on a live machine. Copy the committed
    # base into an overlay-free tmp dir (no sibling prospector.local.yaml) and point the CLI at it, so only
    # the shipped defaults are read regardless of the checkout's machine config.
    import prospector.cli.main as cli_main
    _seed(layout, registry)
    iso = tmp_path / "prospector.yaml"
    iso.write_bytes(cli_main._CONFIG_PATH.read_bytes())      # the tracked base, sans its machine overlay
    monkeypatch.setattr(cli_main, "_CONFIG_PATH", iso)
    result = CliRunner().invoke(cli, ["backup", "--store", str(store_root)])
    assert result.exit_code != 0
    assert "no backup targets" in result.output.lower() or "no backup targets" in str(result.exception)


def test_pros_store_verify_restore_reads_a_backup_and_prints_counts(layout, registry, tmp_path):
    _seed(layout, registry)
    target = _bless(tmp_path / "hd1")
    backup_store(layout, [target])

    result = CliRunner().invoke(cli, ["store", "verify-restore", str(target)])
    assert result.exit_code == 0
    assert "leads=2" in result.output and "events=3" in result.output and "fund_objects=1" in result.output
