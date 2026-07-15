# Single-writer lock + deploy coordination — one lock, two acquirers (M7-04 / M7-06)

*Decision record, 2026-07-14. Ratifies the design-thread ruling captured in
`docs/notes/2026-07-14-single-writer-lock-m7-04-06-build-note.md`, closing the two open concurrency
judgments in `docs/bugs/INDEX.md`: **M7-04** (a deploy can swap code/deps under an in-flight scheduled tick)
and **M7-06** (no single-instance lock / no `busy_timeout`; concurrency rested on launchd serialization +
atomic appends). Governing: spec §7 (store durability), §9 (the runner), the M7 autonomy core. The
single-writer invariant existed in **prose/assumption only** — a class-3 (invariant-in-prose) waiting to
produce its bug; this converts it to **mechanism** at minimal size.*

## The decision — one lock, two acquirers

**Lockfile:** `<store.root>/run.lock`, scoped to the store because the store is the writer domain the lock
guards. Two runs pointed at *different* stores may overlap (correct); two runs, from any checkout, pointed at
the *same* store may not.

1. **The runner (in-process).** `pros run` acquires `fcntl.flock(LOCK_EX | LOCK_NB)` on the lockfile —
   **after** config fail-fast validation (so a misconfigured run still fails fast and touches nothing) and
   **before** the registry opens or any fossil is written. In the runner, not `run.sh`: an in-runner lock
   covers **every** entry point — the scheduled tick *and* a manual `pros run` from a second shell (the
   realistic collision) — where a wrapper-level lock would cover only scheduled invocations. On contention it
   **refuses loudly and exits nonzero** (a one-line message naming the lock path and the cause), **writing no
   fossils and paging no one.** The legitimate tick is running; the refused duplicate is prevented noise, not
   an emergency. A scheduled-instance refusal is caught in the launchd `StandardErrorPath` log for forensics.

2. **`deploy.sh` (same lockfile).** Before mutating the prod worktree (the checkout + `uv sync`), it takes the
   **same** lock and, on contention, refuses with *"a tick is in flight — retry in a few minutes"* and exits
   nonzero. No waiting mode: a blocked-then-proceeding deploy is silent behavior; a refusal is legible and the
   retry costs two minutes, once.

## Why `flock`, not a PID file

The kernel releases a flock when the holding process dies, so a crashed or killed tick can **never** leave a
stale lock — which keeps the documented `launchctl kickstart -k` escape hatch safe **by construction** (the
kill releases; the restart re-acquires). A PID file reintroduces the stale-lock failure mode and needs a
liveness check; flock needs nothing. Pinned by a test that SIGKILLs a holder and acquires immediately after.

## Deviation from the build note — macOS has no shell `flock(1)`

The build note reached for a shell `flock -n` in `deploy.sh`. **macOS (the Mini's OS) has no `flock(1)`
utility** (it is util-linux, Linux-only). So `deploy.sh` instead reuses the runtime's OWN lock through a new
`pros store lock-run -- <command>` (acquire the flock, run the command under it, release; exit 75 =
EX_TEMPFAIL on contention). This is not a compromise — it is **truer to the note's own requirement** that
"one lockfile both sides derive identically": one code path (`prospector.store.run_lock`, `fcntl.flock`, which
*does* work on macOS), one config-derived path, used by both the runner and the deploy. `deploy.sh` runs
`lock-run` from the **dev** repo (this release's code + its venv, so the command exists even on the first
deploy of this feature); on the Mini dev and prod share the one external store, so the dev-derived lock path
matches the prod runner's. A `pros store lock-path` prints the derived path for on-Mini verification.

## The belt — `busy_timeout`

`PRAGMA busy_timeout=5000` on the registry **writer** connection at open. With the single-writer lock as the
primary, writer-vs-writer contention is structurally gone; the residual is the brief lock the SQLite
`.backup` API takes if a **manual** `pros backup` overlaps a tick — the timeout turns that from an immediate
`SQLITE_BUSY` into a short wait. Hardcoded (a commented constant); promote to config only if it ever actually
needs tuning (the config-under-real-pain rule). The read-only (`mode=ro`) dashboard connection stays a pure
reader, untouched.

## Deliberately NOT built (named so it stays not-built)

- **No blue-green / worktree-per-release symlink flip.** Zero-downtime deploy machinery for a system with one
  ~2-minute tick per day and rare manual deploys is over-engineering; the lock gives the same safety at a
  fraction of the surface. Revisit only if deploys become frequent or ticks long.
- **No queueing of refused runs.** A duplicate tick is a mistake or a race; it should be *seen* (refused
  loudly), not absorbed silently.
- **No daemon / no coordination service.** launchd remains the scheduler; the lock is the only new mechanism.

## Acceptance (tests attempt the violation)

`tests/test_run_lock.py`: a second acquirer is refused while the first holds it; a `pros run` that hits a held
lock exits nonzero **and writes no fossils** (proven RED by disabling the refusal — the duplicate tick then
actually runs); a SIGKILLed holder leaves no stale lock (next acquire succeeds immediately); `busy_timeout` is
set on the writer connection; `pros store lock-run` refuses under a held lock (exit 75, command never runs)
and otherwise propagates its command's exit code. The `deploy.sh` refusal is a scripted **on-Mini** check
(shell-level, Phase-3 style) — prove the refusal once, don't assume it. Full suite green through the CI gate;
owner reviews and merges.

## On-Mini verification (owner, after merge + deploy) — two things only the real machine can prove

1. **The refusal fires.** Hold the lock manually, confirm a manual `pros run` refuses loudly and the next
   scheduled tick runs clean; one deliberate `deploy.sh` attempt during a held lock to see its refusal.
2. **The shared-store assumption the dev-side lock rests on.** Run `pros store lock-path` from **both** the dev
   and prod checkouts and assert the two paths are **identical.** `deploy.sh` takes the lock from the *dev*
   checkout on the premise that dev and prod resolve `store.root` to the *same* external store — but the
   overlay (`config/prospector.local.yaml`) is per-checkout and untracked, so if it ever drifted, a deploy
   would lock the **wrong** store and could proceed **during a live tick, silently** — the bad direction (a
   lock that guards nothing is worse than a visibly-broken one). Pinning the two `lock-path` outputs equal,
   once, on the real machine closes the one gap the mechanism cannot verify from inside itself.

## Record-keeping

Closes **M7-04** and **M7-06** in `docs/bugs/INDEX.md` (→ ✅, linking this record + the tests). Rides along: a
**vocabulary fix** from the design-thread INDEX review — `concurrency` becomes a first-class term in the
controlled Shape vocabulary (`README.md` §5), replacing the `— (concurrency)` parenthetical those two rows
carried, which was synonym-coining against the register's own controlled-vocab rule.
