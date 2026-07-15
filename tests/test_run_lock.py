"""Single-writer lock — M7-04 / M7-06 (decision docs/decisions/2026-07-14-single-writer-lock-and-deploy-
coordination.md; build note docs/notes/2026-07-14-single-writer-lock-m7-04-06-build-note.md).

Tests ATTEMPT THE VIOLATION (the class-3 discipline: the invariant was prose/assumption; these make it
un-violatable and prove it). Offline; the crash-release test spawns a real subprocess of THIS interpreter
(no network). The load-bearing invariants:

  - a second acquirer on the same store is REFUSED (non-blocking) while the first holds it, and a `pros run`
    that hits a held lock exits nonzero and writes NOTHING (no registry, no run event, no page);
  - a crashed/killed holder leaves NO stale lock — a subsequent acquire succeeds immediately (the
    flock-not-PID-file property, the reason `kickstart -k` stays safe);
  - the `busy_timeout` belt is set on the registry writer connection;
  - `pros store lock-run` (the macOS-portable deploy coordinator) refuses under a held lock and does not run
    its command; runs and propagates the exit code when free.
"""

import subprocess
import sys
import time

import pytest
from click.testing import CliRunner

from prospector.cli.main import cli
from prospector.store.run_lock import RunLockHeld, acquire, run_lock_path


# -- the lock itself: refuse while held, release on drop -----------------------------------------------

def test_a_second_acquire_is_refused_while_the_first_is_held(tmp_path):
    first = acquire(tmp_path)
    with pytest.raises(RunLockHeld) as ei:
        acquire(tmp_path)                       # same store, second acquirer -> refused (non-blocking)
    assert str(run_lock_path(tmp_path)) in str(ei.value)
    first.release()
    acquire(tmp_path).release()                 # once freed, the next acquirer gets it


def test_a_killed_holder_leaves_no_stale_lock(tmp_path):
    # Attempt the violation the flock design exists to survive: the holder DIES without releasing. A PID
    # file would strand the lock here; flock is released by the kernel on process death, so the next
    # acquire succeeds with no recovery step (this is what keeps the `kickstart -k` escape hatch safe).
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import sys; from prospector.store.run_lock import acquire; "
         "l = acquire(sys.argv[1]); print('ACQUIRED', flush=True); "
         "import time; time.sleep(60)",
         str(tmp_path)],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ACQUIRED"   # it holds the lock now
        with pytest.raises(RunLockHeld):
            acquire(tmp_path)                                    # ...so we're refused while it lives
        holder.kill()                                           # SIGKILL — no chance to release
        holder.wait(timeout=10)
    finally:
        if holder.poll() is None:
            holder.kill(); holder.wait(timeout=10)
    acquire(tmp_path).release()                                 # the kill released it — no stale lock


# -- the belt: busy_timeout on the registry writer connection ------------------------------------------

def test_busy_timeout_is_set_on_the_registry_writer_connection(registry):
    assert registry.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


# -- `pros run` refuses under a held lock and writes nothing -------------------------------------------

def test_pros_run_refuses_when_the_lock_is_held_and_writes_nothing(tmp_path, monkeypatch):
    # A minimal VALID config so `pros run` passes fail-fast validation and actually REACHES the writer lock
    # (yahoo primary needs no token; no email -> NullNotifier). The lock sits after config validation, so a
    # misconfigured run still fails fast untouched — this proves the *duplicate-tick* refusal specifically.
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "prospector.yaml").write_text(
        'edgar:\n  user_agent: "Test/1.0 (t@e.com)"\nprices:\n  primary: yahoo\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    store = tmp_path / "store"
    held = acquire(store)                        # a tick is "in flight" (this process holds store/run.lock)
    try:
        result = CliRunner().invoke(cli, ["run", "--store", str(store)])
    finally:
        held.release()
    assert result.exit_code != 0                                 # refused loudly
    assert "in flight" in result.output.lower() or "run.lock" in result.output
    # ...and it refused BEFORE opening the registry: no fossils written — the duplicate did nothing.
    assert not (store / "registry.sqlite").exists()
    assert not (store / "runs").exists()


# -- `pros store lock-run` (the deploy coordinator) ----------------------------------------------------

def test_lock_run_runs_the_command_and_propagates_its_exit_code_when_free(tmp_path):
    ok = CliRunner().invoke(cli, ["store", "lock-run", "--store", str(tmp_path), "--", "sh", "-c", "exit 0"])
    assert ok.exit_code == 0
    bad = CliRunner().invoke(cli, ["store", "lock-run", "--store", str(tmp_path), "--", "sh", "-c", "exit 3"])
    assert bad.exit_code == 3                                    # COMMAND's own exit code propagates


def test_lock_run_refuses_under_a_held_lock_and_does_not_run_the_command(tmp_path):
    marker = tmp_path / "ran.marker"
    held = acquire(tmp_path)
    try:
        result = CliRunner().invoke(
            cli, ["store", "lock-run", "--store", str(tmp_path), "--", "touch", str(marker)])
    finally:
        held.release()
    assert result.exit_code == 75                               # EX_TEMPFAIL — 'a tick is in flight'
    assert "REFUSED" in result.output
    assert not marker.exists()                                  # the command never ran


def test_lock_path_prints_run_lock_under_the_store_root(tmp_path):
    result = CliRunner().invoke(cli, ["store", "lock-path", "--store", str(tmp_path)])
    assert result.exit_code == 0
    assert result.output.strip() == str(run_lock_path(tmp_path))
