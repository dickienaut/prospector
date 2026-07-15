# Single-writer lock + deploy coordination — closing M7-04 / M7-06 (2026-07-14)

*Build note for Claude Code. Closes the two open concurrency judgments in `docs/bugs/INDEX.md` — **M7-04**
(deploy can swap code/deps under an in-flight tick) and **M7-06** (no single-instance lock / no
`busy_timeout`; concurrency rests on launchd serialization + atomic appends) — as **one design**. Framing:
the single-writer invariant currently exists in prose/assumption only, which is a class-3
(invariant-in-prose) waiting to produce its bug; this converts it to mechanism at minimal size. Design ruled
by the design thread; a decision record ratifies it (§6).*

## 1. The design — one lock, two acquirers

**Lockfile:** `<store.root>/run.lock` — scoped to the store because the store is the writer domain the lock
guards. Two runs pointed at *different* stores may overlap (correct); two runs, from any checkout, pointed at
the *same* store may not.

**Acquirer 1 — the runner, in-process.** At tick start (before any store write, before the notifier exists),
acquire via `fcntl.flock(LOCK_EX | LOCK_NB)` on the lockfile. **In the runner, not in `run.sh`** — an
in-runner lock covers every entry point (the scheduled tick *and* a manual `pros run` from a second shell,
which is the realistic collision); a wrapper-level lock covers only scheduled invocations. On contention:
**refuse loudly and exit** — a clear one-line message to stderr naming the lock path and the likely cause
("another tick holds <path>; a run is in flight"), nonzero exit code, **no store write, no fault event, no
page.** The legitimate tick is running; the refused duplicate is prevented noise, not an emergency. The
launchd `StandardErrorPath` log catches a scheduled-instance refusal for forensics.

**Acquirer 2 — `deploy.sh`, same file.** Before any mutation of the prod worktree (the checkout, the
`uv sync`), take the same lockfile with shell `flock -n`. On contention: refuse with *"a tick is in flight —
retry in a few minutes"* and exit nonzero. No waiting mode (a blocked-then-proceeding deploy is silent
behavior; a refusal is legible and the retry costs the operator two minutes, once). deploy.sh must resolve
`store.root` **from the merged config the same way the runtime does** — not a hardcoded path; if that needs a
tiny helper (`pros`-level print of the lock path), build it, but the requirement is one lockfile both sides
derive identically.

**Why `flock`, not a PID file:** the kernel releases a flock on process death, so a crashed or killed tick
cannot leave a stale lock — which also keeps the documented `launchctl kickstart -k` escape hatch safe by
construction (the kill releases; the restart acquires). PID files reintroduce the stale-lock failure mode and
need liveness checks; flock needs nothing.

## 2. The belt — `busy_timeout`

Set `PRAGMA busy_timeout` (constant, ~5000 ms, with a comment) on registry connections at open. With the
single-writer lock, writer-vs-writer contention is structurally gone; the residual is the brief lock the
SQLite `.backup` API takes if a **manual** `pros backup` overlaps a tick — the timeout turns that from an
immediate `SQLITE_BUSY` error into a short wait. Hardcode the constant; promote to config only if it ever
actually needs tuning (the config-under-real-pain rule).

## 3. Deliberately not built (named so it stays not-built)

- **No blue-green / worktree-per-release symlink flip.** Zero-downtime deploy machinery for a system with one
  ~2-minute tick per day and rare manual deploys is over-engineering; the lock gives the same safety at 1/20th
  the surface. Revisit only if deploys ever become frequent or ticks long.
- **No queueing of refused runs.** A duplicate tick is a mistake or a race; it should be *seen* (refused
  loudly), not absorbed silently.
- **No daemon / no coordination service.** launchd remains the scheduler; the lock is the only new mechanism.

## 4. Acceptance — tests attempt the violation

- **Second tick refused:** with the lock held (subprocess or test-held flock), a `pros run` exits nonzero with
  the refusal message and the store shows **no** new run event — the refused instance wrote nothing.
- **Crash releases the lock:** a subprocess acquires the lock and is SIGKILLed; a subsequent acquisition
  succeeds immediately (no stale-lock recovery needed — this is the flock-not-PID-file property, pinned).
- **`busy_timeout` present:** assert the PRAGMA is set on opened registry connections.
- **deploy.sh refusal:** shell-level if the harness allows (hold the lock with `flock <path> sleep 100 &`,
  run `deploy.sh`, assert refusal + nonzero); otherwise a scripted on-Mini acceptance step, Phase-3 style —
  prove the refusal once, don't assume it.
- Full suite green through the CI gate; owner reviews and merges.

## 5. On-Mini verification (owner, after merge + deploy)

Once deployed: hold the lock manually, confirm a manual `pros run` refuses loudly; release; confirm the next
scheduled tick runs clean. One deliberate `deploy.sh` attempt during a held lock to see the refusal message.
**Then pin the shared-store assumption the dev-side deploy lock stands on:** run `pros store lock-path` from
**both** the dev and prod checkouts and assert the two paths are **identical**. deploy.sh takes the lock from
the dev checkout because dev and prod resolve `store.root` to the same external store — but the overlay is
per-checkout and untracked, so a drifted dev overlay would lock the *wrong* store and let a deploy proceed
during a live tick, silently (the bad direction). Two minutes, and the invariant is proven live, not assumed.
(Ratified addition, design seat 2026-07-15 — see the decision record's on-Mini section.)

## 6. Record-keeping (the archive discipline — this closes two register rows)

- **Decision record:** `docs/decisions/2026-07-14-single-writer-lock-and-deploy-coordination.md` — ratifies
  the one-lock/two-acquirers design, the refuse-loudly semantics, the flock-over-PID-file rationale, and the
  named not-built alternatives.
- **INDEX flips:** M7-04 → ✅ and M7-06 → ✅, both linking the decision record and the guarding tests; fix-site
  column updated from "not yet designed" / "escape hatch documented" to the real mechanism.
- **Vocabulary fix riding along (from the design-thread INDEX review):** add `concurrency` to the controlled
  shape vocabulary in `README.md` §5 and tag M7-04/M7-06 with it properly — replacing the "— (concurrency)"
  parenthetical, which was synonym-coining against the register's own rule. Same PR; the rows are being
  edited anyway.
