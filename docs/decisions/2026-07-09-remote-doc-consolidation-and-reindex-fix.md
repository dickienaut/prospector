# Remote session — doc consolidation, drift correction, and the reindex sub-second fix (2026-07-09)

*Session log for the design/review thread, worked **entirely remotely from the phone** (`/remote-control`
driving the local Mac) between QA checks. Six merged PRs (#17–#22). One-line summary: **the map now matches
the territory** — the documentation debt the 2026-07-08 handoff named as "still owed" is closed, and one
latent repair-path data-loss bug is fixed. **No behavioral change to the live path except that one fix.**
The canonical docs (state rev5, spec rev14) remain the source of truth; this is a point-in-time record.*

---

## Where this sits

The 2026-07-08 handoff (`docs/prospector-thread-handoff-2026-07-08.md`) closed the last stretch — M5 runner
built, first `pros run` fired 5 live xcorr leads, Yahoo→Tiingo pivot, the N1–N10 QA fix batch — and named
one code-side item **still owed**: the **C.2 doc drift** (`ARCHITECTURE.md` + runner docstrings needing
regeneration from the *actual wired* set; the inline docstrings were corrected in the QA batch, the
systematic pass was not). It also listed as *immediate*: "drop in rev 5 / rev 14."

Today did exactly those two things and swept the rest of the drift with them. This was deliberately
low-risk work — docs plus one contained fix — which is the correct shape for a remote/on-the-move session
where **Claude Science QA is desktop-only** and we go a stretch between cold-mount checks. Nothing here
opened a CONTRACT question; nothing here needs a QA pass to be safe to have merged (though PRs #17–#22 are
of course still in the record for the next cold review).

## What landed today (in order)

1. **PR #18 — `ARCHITECTURE.md` refreshed to ground truth + rev5/rev14 dropped in.** Regenerated
   `ARCHITECTURE.md` (227 lines changed) to the live-runner reality, and committed the design thread's
   canonical cut: **state-of-project rev5**, **spec rev14** (§5 regenerated into the built/queued/deferred/
   aspirational three-register structure; the two DRIFT spots closed), and the **thread-handoff snapshot**.
   *This closes C.2* — the doc-drift the 07-08 handoff flagged as owed.

2. **PR #17 — `CLAUDE.md` branch rule.** Made explicit what had been convention: **always work on a new
   branch off `main`, never commit directly to `main`, graduate by PR.** A three-line constitution addition;
   it's the discipline that makes fragmented remote sessions safe (every slice is a durable, reviewable
   branch, not a dirty working tree on `main`).

3. **PR #19 — corrected stale "deferred to M5" markers for SOI-fetch and `mandate.changed`.** The M5 arc
   actually *wired* two things that four docstrings + one config **comment** still described as deferred:
   - **Live EDGAR SOI fetch** — performed by the runner's `_run_soi_corroboration` (`classify_soi_target`
     → `EdgarClient.filing_text`, bytes fed through `ingest/soi.py`'s `freeze`).
   - **`mandate.changed`** — its named unblock (EDGAR prospectus-text fetch + `ingest/prospectus/`
     blob-per-accession storage + strategy-section text diff) shipped as `ingest/prospectus.py` +
     `sensors/mandate.py`, wired live in `_run_mandate`.

   Comments/config-only, **no behavior change** (the config edit is inside a `#` comment, so the parsed-dict
   config hash is unaffected — config-honesty preserved). **Preserved as genuinely-still-deferred** (did not
   overclaim): the rebalance sensor's *own* runner wiring (needs the holdings/constituent vertical), the
   quarterly NPORT-P cross-check (`parse_nport_holdings`, the labeled §3b stub), and the **N9 SOI cadence
   gate** (M7; its test stays `xfail(strict=True)`).

4. **PR #20 — README suite.** Rewrote the root `README.md` and added a **per-package README** to each
   `prospector/` subfolder (backtest, cli, dashboard, fold, identity, ingest, primitives, runner, sensors,
   store). Orientation for a cold reader; no code touched.

5. **PR #22 — docstring drift cleanup.** Corrected stale docstrings across `cli/main.py`,
   `identity/resolution.py`, `ingest/holdings.py`, `sensors/launch.py`, `sensors/launch_corroboration.py`
   that still described a pre-runner / pre-xlsx world. Comments only.

6. **PR #21 — the one real code fix: `reindex` parses sub-second snapshot stems** (see next section).

## The one behavioral change — reindex sub-second snapshot stems (PR #21)

This is the only code change today and it fixes a **latent, silent, unrecoverable data-loss bug** — but
strictly on the **repair path**, never the live write path.

- **The bug.** `layout.ts_compact` grew a **sub-second form** (`…130000_123456Z`) so two snapshots written
  in the same wall-clock second get distinct filenames (needed because the runner's reactive policy can
  snapshot one lead twice in a second — a real state change — and colliding filenames would trip
  `SnapshotDivergenceError` and abort the run). But `reindex._index_snapshot` still parsed the stem as
  **whole-second-only** (`%Y%m%dT%H%M%SZ`). A sub-second stem threw `ValueError`, which the `except`
  swallowed → the snapshot was silently counted `skipped` and **dropped from a rebuilt index**.
- **Why it's unrecoverable.** The filename stem is the **only** carrier of a snapshot's `ts` —
  `write_snapshot` stores the fold state *inside* the file, never the ts. So a skipped sub-second snapshot
  can't be reconstructed. (**Events are unaffected** — their ts comes from inside the file.)
- **Root cause.** `ts_compact` documented itself as "one-way (never parsed back)," so its inverse was never
  written — and reindex hand-rolled a whole-second-only parser that silently fell behind when the
  sub-second form was added.
- **The fix.** Added `ts_from_compact` as the **documented inverse, colocated with `ts_compact`** so they
  can't drift again; `reindex` uses it (parses both whole-second and sub-second forms; a genuine
  garbage/foreign stem still raises → counted `skipped`, never a crash). Regression test writes a
  sub-second snapshot, drops the registry, rebuilds, and asserts the snapshot is indexed with microseconds
  preserved through the round-trip. **500 passed, 1 xfailed** (was 499 + this test).
- **Blast-radius note for the thread:** `pros store reindex` is repair, not run-now (it recomputes nothing
  — it rebuilds the index from the fossil record). This never touched the live runner. The exposure was: a
  rebuild *after* a same-second double-snapshot would have quietly lost the second one. Low probability,
  high-consequence-if-hit (silent), so worth the fix even mid-remote-session.

## Where the queue stands now (unchanged in order; unblocked of doc debt)

The 07-08 handoff's *immediate* items are done and **C.2 is closed**, so the build queue is clean of
documentation debt. **Order is unchanged** — nothing today re-ranked it:

1. **§9e — dispersion + the holdings/constituent-price vertical** (the next real build; the bigger lift).
   Wire dispersion into the runner in **shadow** (silent, non-paging, excluded from the ceiling) — which
   starts its **90-day burn-in clock** and pulls in **constituent-price ingest**, forcing
   **holdings-intake coverage** as its own slice. Prices flowing through Tiingo (done) was its precondition;
   that's now true. **Carry the standing rule in:** *prove the spawner fires on real seed data, not merely
   that it's wired* (the lesson from xcorr's near-permanent inertness over an empty registry) gets its first
   post-xcorr test here.
2. **§10 — the email sender.** Weekly heartbeat/dead-man + state-change push, with **nuisance-alarm
   suppression built in** (push once on a *new* fault, then fall to heartbeat until it clears/changes) —
   still `NullNotifier` today; verified inert (`pros run` faults=0 → pushed=False).
3. **M6** (discourse capture + budget guard) → **M7** (infra-as-code + scheduled deploy; M7 owns the
   deferred **N9 SOI-corroboration cadence gate** and the read-only-media **WAL-checkpoint-out** step).

## For the design thread to weigh (the "next steps" ask)

Genuine open items, smallest first. None is a CONTRACT change; the first two are scope/sequencing calls
the build seat wants settled before starting §9e.

- **Confirm §9e is next, shadow-first, burn-in-starts-on-wire.** Nothing today changed the case for it, but
  it's the first big lift since going live — worth an explicit green-light rather than assumed.
- **Holdings-intake coverage — how far to widen, and named.** §9e's constituent-price vertical is the point
  where **SPDR-only holdings intake** stops being sufficient (dispersion needs constituents for its
  cluster, and the launch-corroboration lag is already *structurally unmeasurable* outside the SPDR family —
  an existence proof, not a rate). Apply the governing rule from the QA arc: **does widening close a gap on
  something that's LIVE, or build for a case that isn't live yet?** Recommend deciding the *named* target
  set (which families / which intake surface) up front so §9e doesn't silently widen ad hoc.
- **No CONTRACT question is open from today** (flagging this explicitly so it's not read as an omission).
  The stale-marker corrections (#19) only re-described already-shipped behavior; the reindex fix (#21) added
  an inverse function and a test.

## Workflow note (for the "can I work on the move?" thread)

Everything above was done from the phone via `/remote-control`, between QA checks, with each slice landed
as its own branch + PR for later cold review. That's the natural shape of remote work: **doc consolidation,
drift correction, and contained, well-tested fixes** — low blast radius, no need for a live end-to-end
`pros run` or a desktop QA mount to be safe to merge. The heavier §9e vertical (new ingest surface, a
spawner that must be *proven* to fire on real data, a live twice-a-day run to verify) is better batched for
a desktop session where Science can cold-review it. The branch-rule addition (#17) is what makes the
fragmented remote cadence safe: nothing accretes on a dirty `main`.
