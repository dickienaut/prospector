"""Single-writer lock for the fossil store — closing M7-04 / M7-06 (build note
docs/notes/2026-07-14-single-writer-lock-m7-04-06-build-note.md; decision
docs/decisions/2026-07-14-single-writer-lock-and-deploy-coordination.md).

One writer per store, enforced by MECHANISM instead of the prose/assumption invariant it was before (a
class-3 invariant-in-prose waiting to produce its bug). `fcntl.flock(LOCK_EX | LOCK_NB)` on
`<store.root>/run.lock`: a second tick — the scheduled fire OR a manual `pros run` from another shell —
refuses loudly and writes nothing; `deploy.sh` takes the SAME lock (through `pros store lock-run`) so a
deploy never swaps code/deps under an in-flight tick.

Why `flock`, not a PID file: the kernel releases a flock when the holding process dies, so a crashed or
killed tick can NEVER leave a stale lock — which keeps the documented `launchctl kickstart -k` escape hatch
safe by construction (the kill releases; the restart re-acquires). A PID file would reintroduce the
stale-lock failure mode and need a liveness check; flock needs nothing.

Portability: `fcntl.flock` works on macOS (the Mini's OS) as well as Linux. The shell `flock(1)` utility the
build note first reached for does NOT exist on macOS — which is exactly why deploy.sh reuses THIS mechanism
through the CLI (`pros store lock-run`) rather than a shell flock: one lockfile, one code path, both sides
deriving the path from config the runtime's way.

The lock guards the store (the writer domain), so it is scoped to `store.root`: two runs pointed at
DIFFERENT stores may overlap (correct); two runs pointed at the SAME store may not.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

LOCK_NAME = "run.lock"


class RunLockHeld(Exception):
    """Another process holds the store's single-writer lock — a run is in flight. Raised non-blocking; the
    caller refuses loudly and exits WITHOUT writing (never waits, never pages — the legitimate tick is
    running, the refused duplicate is prevented noise, not an emergency)."""

    def __init__(self, path):
        self.path = Path(path)
        super().__init__(
            f"another tick holds {self.path} — a run is in flight; refusing to start a second writer")


def run_lock_path(store_root) -> Path:
    """The single-writer lockfile path — the one path the runner and the deploy coordination both use,
    derived from `store.root` (never hardcoded)."""
    return Path(store_root) / LOCK_NAME


class WriterLock:
    """A held flock. Keep the object referenced for the lock's lifetime; `release()` frees it, and so does
    process death (the flock-not-PID-file property). NEVER delete the lockfile — the lock lives on the open
    file descriptor, not the file content, and unlinking it races a concurrent acquirer."""

    def __init__(self, fd: int, path: Path):
        self._fd: int | None = fd
        self.path = path

    def release(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def __del__(self):
        # Belt-and-braces release: `pros run` holds the lock in a local for the whole tick, so on CPython
        # the WriterLock is refcount-collected the moment `run` returns (or unwinds on an exception) and
        # this frees the fd promptly — no reliance on process exit, and no cross-invocation fd leak under
        # an in-process caller like CliRunner. Process death still releases the flock regardless.
        try:
            self.release()
        except Exception:
            pass


def acquire(store_root) -> WriterLock:
    """Acquire the single-writer lock, non-blocking. Returns a `WriterLock` (call `.release()`, or let the
    process exit); raises `RunLockHeld` if another process already holds it. Creates the store root + the
    lockfile if absent (`O_CREAT`, no truncate — the lock is on the fd, so the file's content is irrelevant
    and a concurrent holder's fd must not be disturbed)."""
    path = run_lock_path(store_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:  # BlockingIOError / EWOULDBLOCK when another fd (any process) holds it
        os.close(fd)
        raise RunLockHeld(path)
    return WriterLock(fd, path)
